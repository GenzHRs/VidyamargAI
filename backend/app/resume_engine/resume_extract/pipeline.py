"""Deterministic orchestration, auditable artifacts and directory CLI."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
import logging
from pathlib import Path
import tempfile
from typing import Any
from .config import load_config
from .ingest import ingest, convert_doc, detect_type
from .docx_reader import read_docx
from .pdf_reader import read_pdf
from .models import Document, Line, Run
from .reading_order import repair_order, attach_bullets
from .structure import build_structured, structured_markdown
from .normalize import normalize
from .classify import classify
from .sections import build_sections
from .fields import extract_fields
from .validate import completeness, needs_review, validate_schema

log=logging.getLogger(__name__)


def extract(path: str | Path, config: dict[str, Any] | None = None, seen: dict[str,str] | None = None) -> dict[str, Any]:
    """Pure extraction result for one file, apart from optional duplicate registry."""
    path=Path(path);cfg=config or load_config();info=ingest(path,seen)
    if info.kind=='docx':doc=read_docx(path,cfg)
    elif info.kind=='pdf':doc=read_pdf(path,cfg)
    elif info.kind=='doc':
        with tempfile.TemporaryDirectory(prefix='resume-doc-') as directory:
            converted=convert_doc(path,Path(directory),cfg);doc=read_docx(converted,cfg)
        doc.warnings.append('Legacy conversion: completeness measured against converted OOXML, not original OLE')
    else:
        data=path.read_bytes();text=data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
        doc=Document([Line(f'l{i:05d}',line,source_ids=[f'l{i:05d}']) for i,line in enumerate(text.splitlines())],text,'decoded_text')
    return process_document(doc,asdict(info),path.name,cfg)


def process_document(doc, info, filename, cfg):
    ordered,order_review=repair_order(doc.lines,cfg)
    normalized=normalize(attach_bullets(ordered),cfg);classified=classify(normalized,cfg)
    if cfg.get('understanding'):
        from .understanding import refine_lines
        refine_lines(classified,cfg)
    sections=build_sections(classified,cfg);fields=extract_fields(classified,sections,cfg)
    if cfg.get('understanding'):
        from .understanding import refine_fields
        refine_fields(doc.lines,classified,sections,fields,cfg)
    structured=build_structured(classified,sections,fields,cfg)
    if cfg.get('understanding'):
        from .understanding import refine_structure
        refine_structure(structured,classified,sections,cfg)
    check=completeness(doc.source_text,doc.raw_text,cfg) if not doc.ocr and doc.source_method!='unavailable' else {'status':'unverifiable','reason':'OCR or independent reference unavailable'}
    if doc.ocr:
        def cap_ocr(value: Any) -> None:
            if isinstance(value,dict):
                if 'confidence' in value:value['confidence']=min(value['confidence'],cfg['fields']['ocr_confidence_cap'])
                for item in value.values():cap_ocr(item)
            elif isinstance(value,list):
                for item in value:cap_ocr(item)
        cap_ocr(fields);cap_ocr(sections);cap_ocr(structured)
    review=needs_review(fields,sections,cfg)+order_review+structured['review']
    for warning in doc.warnings:review.append({'path':'source','reason':warning,'confidence':0.0})
    if check['status']!='pass':review.append({'path':'raw_text','reason':'Completeness '+check['status'],'confidence':0.0})
    structured['review']=review
    result={'schema_version':'3.0.0','source':{'filename':filename,'sha256':info['sha256'],'type':info.get('kind',info.get('type')),
            'duplicate_of':info.get('duplicate_of'),'ocr':doc.ocr,'ocr_pages':doc.ocr_pages,'pages':doc.pages,'reference_method':doc.source_method},
            'config_sha256':hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest(),
            'raw_text':doc.raw_text,'source_text':doc.source_text,
            'normalized_text':'\n'.join(l.text for l in classified if not l.duplicate_of),
            'raw_lines':[l.to_dict() for l in doc.lines], 'lines':[l.to_dict() for l in classified],
            'sections':sections,'fields':fields,'structured':structured,'needs_review':review,
            'quality':{'completeness':check,'schema_errors':[],'warnings':doc.warnings,
                       'suppressed_exact_repeats':[{'id':l.id,'duplicate_of':l.duplicate_of} for l in classified if l.duplicate_of]}}
    result['quality']['schema_errors']=validate_schema(result)
    return result


def markdown(result: dict[str,Any]) -> str:
    """Human-readable heading hierarchy without dropping unknown sections."""
    prefix={'TITLE':'# ','SUBTITLE':'','H1':'## ','H2':'### ','TEXT':'','BULLET':''}
    return '\n\n'.join(prefix[l['tag']]+l['text'] for l in result['lines'] if not l['duplicate_of'])+'\n'


def write_outputs(result:dict[str,Any],directory:Path) -> None:
    """Write stable JSON, preserved text, normalized text and Markdown per file."""
    directory.mkdir(parents=True,exist_ok=True)
    for name,value in [('resume.json',result),('quality.json',result['quality']),('structured.json',result['structured'])]:
        (directory/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=False)+'\n',encoding='utf-8')
    for name,value in [('raw.txt',result['raw_text']),('source.txt',result['source_text']),('normalized.txt',result['normalized_text']),('resume.md',markdown(result)),('structured.md',structured_markdown(result['structured'])),('structured.txt',structured_markdown(result['structured']))]:
        (directory/name).write_text(value,encoding='utf-8')


def main(argv:list[str] | None = None) -> int:
    """Batch runner continues after errors and exits nonzero for failed gates."""
    parser=argparse.ArgumentParser(description='Offline deterministic resume extraction')
    parser.add_argument('path',type=Path);parser.add_argument('--out',type=Path,default=Path('out'))
    parser.add_argument('--config',type=Path);parser.add_argument('--include-txt',action='store_true')
    parser.add_argument('--from-result',action='store_true',help='Reprocess one saved resume.json using its raw lines and coordinates')
    parser.add_argument('--export-dir',type=Path,help='Directory to save resumes_one_row_per_candidate.xlsx and .csv')
    parser.add_argument('--db',type=Path,help='SQLite database to save normalized relational records')
    parser.add_argument('--verbose',action='store_true')
    args=parser.parse_args(argv);logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    cfg=load_config(args.config);source=args.path
    if not source.exists():parser.error('Input path does not exist')
    if args.from_result:
        result=reprocess_result(source,cfg)
        write_outputs(result,args.out)
        return 1 if result['quality']['schema_errors'] else 0
    paths=[source] if source.is_file() else sorted(p for p in source.rglob('*') if p.is_file() and not p.resolve().is_relative_to(args.out.resolve()))
    seen={};summary=[];failed=False
    for path in paths:
        try:
            kind=detect_type(path)
        except ValueError as exc:
            if source.is_file():summary.append({'file':str(path),'status':'error','error':str(exc)});failed=True
            continue
        if source.is_dir() and kind=='txt' and not args.include_txt:continue
        relative=str(path.relative_to(source)) if source.is_dir() else path.name
        try:
            result=extract(path,cfg,seen)
            # Relative path hashing prevents same-name/duplicate input overwrites.
            key=path.stem+'_'+hashlib.sha256(relative.encode()).hexdigest()[:12]
            write_outputs(result,args.out/key)
            status=result['quality']['completeness']['status']
            if status=='fail' or result['quality']['schema_errors']:failed=True
            summary.append({'file':relative,'output':key,'status':status,'sha256':result['source']['sha256'],'duplicate_of':result['source']['duplicate_of'],'needs_review':len(result['needs_review'])})
            log.info('%s: %s (%d review items)',relative,status,len(result['needs_review']))
        except Exception as exc:
            log.exception('Failed input %s',relative);summary.append({'file':relative,'status':'error','error':str(exc)});failed=True
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'batch_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    if args.export_dir:
        from .export import process_and_export
        process_and_export([args.out],args.export_dir,args.db)
    return 1 if failed or not summary else 0


def reprocess_result(path, config=None):
    """Reuse saved source evidence; never pretend this is a fresh PDF extraction."""
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    lines=[Line(**{**l,'runs':[Run(**r) for r in l['runs']]}) for l in data['raw_lines']]
    src=data['source']
    doc=Document(lines,data['source_text'],src['reference_method'],src['ocr'],
                 list(data['quality']['warnings']),src['pages'],src['ocr_pages'])
    return process_document(doc,src,src['filename'],config or load_config())
