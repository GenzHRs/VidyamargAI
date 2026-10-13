"""Font-aware PDF words, cell ownership, recursive whitespace cuts and OCR."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import subprocess
import shutil
import re
import pdfplumber
from .models import Document, Line, Run


def gaps(items: list[dict[str, Any]], low: str, high: str) -> list[tuple[float, float]]:
    """Return whitespace gaps between interval unions."""
    intervals = sorted((w[low], w[high]) for w in items)
    out: list[tuple[float, float]] = []
    end = intervals[0][1]
    for start, finish in intervals[1:]:
        if start > end: out.append((end, start))
        end = max(end, finish)
    return out


def xy_cut(items: list[dict[str, Any]], cfg: dict[str, Any], flow: str = 'page', depth: int = 0) -> list[tuple[str, list[dict[str, Any]]]]:
    """Cut horizontal bands around spanning content, then independent columns.

    Prefer a valid full-height gutter before horizontal gaps inside columns.
    Otherwise choose the widest horizontal band; recurse into its columns.
    """
    if not items: return []
    if depth >= cfg['max_depth']: return [(flow, items)]
    vertical = []
    for left, right in gaps(items, 'x0', 'x1'):
        if right-left < cfg['column_gap']: continue
        a = [w for w in items if w['x1'] <= left]
        b = [w for w in items if w['x0'] >= right]
        if min(len(a), len(b)) >= cfg['min_column_words']:
            vertical.append((right-left,left,right,a,b))
    if vertical:
        _,left,right,a,b = max(vertical,key=lambda v:(v[0],-v[1]))
        return xy_cut(a,cfg,flow+'L',depth+1)+xy_cut(b,cfg,flow+'R',depth+1)
    horizontal = [(bottom-top,top,bottom) for top,bottom in gaps(items,'top','bottom') if bottom-top >= cfg['band_gap']]
    if horizontal:
        _,top,bottom = max(horizontal,key=lambda v:(v[0],-v[1]))
        a = [w for w in items if w['bottom'] <= top]
        b = [w for w in items if w['top'] >= bottom]
        return xy_cut(a,cfg,flow+'T',depth+1)+xy_cut(b,cfg,flow+'B',depth+1)
    return [(flow,items)]


def word_lines(words: list[dict[str, Any]], config: dict[str, Any], context: dict[str, Any]) -> list[Line]:
    """Cluster word baselines inside one column/cell; retain every word once."""
    groups: list[list[dict[str, Any]]] = []
    for word in sorted(words,key=lambda w:(w['top'],w['x0'])):
        target = next((g for g in reversed(groups) if abs(g[0]['top']-word['top']) <= config['pdf']['line_tolerance']), None)
        if target is None: groups.append([word])
        else: target.append(word)
    lines=[]
    for group in groups:
        group.sort(key=lambda w:w['x0'])
        runs=[]
        for i,w in enumerate(group):
            font=w.get('fontname','')
            color=w.get('non_stroking_color')
            decoded=re.sub(r'\(cid:\d+\)', '•', w['text'])
            runs.append(Run((' ' if i else '')+decoded,original_text=w['text'],bold=(any(x in font.lower() for x in ('bold','black','semibold')) or bool(re.search(r'(?:^|\+)(?:CMBX|CMB|CMSSBX|LMRoman\d+-Bold)',font,re.I))),hyperlink=w.get('hyperlink'),
                            size=float(w.get('size',w['bottom']-w['top'])),color=str(color) if color is not None else None,font=font))
        bbox=(min(w['x0'] for w in group),min(w['top'] for w in group),max(w['x1'] for w in group),max(w['bottom'] for w in group))
        lines.append(Line('', ''.join(r.text for r in runs),runs,bbox=bbox,**context))
    return lines


def ocr_words(path: Path, page: int, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Local Tesseract only. Return boxes in PDF points with estimated sizes."""
    from pdf2image import convert_from_path
    import pytesseract
    c=config['pdf']
    image=convert_from_path(str(path),dpi=c['ocr_dpi'],first_page=page,last_page=page,thread_count=1)[0]
    data=pytesseract.image_to_data(image,lang=c['ocr_language'],config=f"--psm {c['ocr_psm']}",output_type=pytesseract.Output.DICT)
    scale=72/c['ocr_dpi']
    words=[]
    for i,text in enumerate(data['text']):
        if not text.strip(): continue
        x,y,w,h=[data[k][i]*scale for k in ('left','top','width','height')]
        words.append({'text':text,'x0':x,'x1':x+w,'top':y,'bottom':y+h,'fontname':'OCR','size':h})
    return words


def read_pdf(path: Path, config: dict[str, Any]) -> Document:
    """Read each digital or OCR page with an independent Poppler reference."""
    c=config['pdf']; lines=[]; warnings=[]; references=[]; ocr_pages=[]
    with pdfplumber.open(path) as pdf:
        for pi,page in enumerate(pdf.pages,1):
            words=page.extract_words(x_tolerance=c['x_tolerance'],y_tolerance=c['y_tolerance'],
                                      extra_attrs=['fontname','size','non_stroking_color'],keep_blank_chars=False)
            # URI annotations carry destinations that may be absent from displayed text.
            for w in words:
                links=[a.get('uri') for a in page.hyperlinks if a.get('uri') and
                       a['x0'] <= (w['x0']+w['x1'])/2 <= a['x1'] and
                       a['top'] <= (w['top']+w['bottom'])/2 <= a['bottom']]
                if links:w['hyperlink']=links[0]
            # pdffonts may be absent. A small digital text layer still triggers OCR.
            no_fonts=False
            if shutil.which('pdffonts'):
                result=subprocess.run(['pdffonts','-f',str(pi),'-l',str(pi),str(path)],capture_output=True,text=True,encoding='utf-8',check=True,timeout=c['subprocess_timeout_seconds'])
                no_fonts=not result.stdout.splitlines()[2:]
            use_ocr=no_fonts or len(words)<c['ocr_min_words']
            if use_ocr:
                words=ocr_words(path,pi,config);ocr_pages.append(pi)
                warnings.append(f'Page {pi}: OCR used; source completeness is not independently measurable')
            if shutil.which('pdftotext'):
                references.append(subprocess.run(['pdftotext','-f',str(pi),'-l',str(pi),'-raw',str(path),'-'],capture_output=True,text=True,encoding='utf-8',check=True,timeout=c['subprocess_timeout_seconds']).stdout)
            else:
                references.append('')
                warnings.append('pdftotext missing: independent completeness unavailable')
            owned:set[int]=set();atoms=[]
            tables=[] if use_ocr else page.find_tables(c['table_settings'])
            for ti,table in enumerate(tables):
                cell_lines=[]
                tid=f'p{pi}:t{ti}'
                for ri,row in enumerate(table.rows):
                    for ci,cell in enumerate(row.cells):
                        if cell is None: continue
                        x0,y0,x1,y1=cell
                        members=[]
                        for wi,w in enumerate(words):
                            if wi not in owned and x0 <= (w['x0']+w['x1'])/2 < x1 and y0 <= (w['top']+w['bottom'])/2 < y1:
                                members.append(w);owned.add(wi)
                        cell_lines.extend(word_lines(members,config,{'page':pi,'part':'body','flow':f'{tid}:r{ri}:c{ci}','table':tid,'row':ri,'cell':ci}))
                x0,y0,x1,y1=table.bbox
                atoms.append({'x0':x0,'x1':x1,'top':y0,'bottom':y1,'lines':cell_lines})
            atoms.extend(w for wi,w in enumerate(words) if wi not in owned)
            for flow,region in xy_cut(atoms,c,f'p{pi}'):
                pending=[]
                for atom in sorted(region,key=lambda w:(w['top'],w['x0'])):
                    if 'lines' in atom:
                        lines.extend(word_lines(pending,config,{'page':pi,'flow':flow}));pending=[]
                        lines.extend(atom['lines'])
                    else: pending.append(atom)
                lines.extend(word_lines(pending,config,{'page':pi,'flow':flow}))
            # Only margin text is eligible for exact-repeat suppression later.
            for line in lines:
                if line.page != pi or not line.bbox: continue
                if line.bbox[3] <= page.height*c['header_fraction']: line.part='header'
                elif line.bbox[1] >= page.height*(1-c['footer_fraction']): line.part='footer'
        page_count=len(pdf.pages)
    for i,line in enumerate(lines):
        line.id=f'l{i:05d}';line.source_ids=[line.id]
    return Document(lines,'\n'.join(references),'pdftotext_raw' if shutil.which('pdftotext') else 'unavailable',
                    bool(ocr_pages),warnings,page_count,ocr_pages)
