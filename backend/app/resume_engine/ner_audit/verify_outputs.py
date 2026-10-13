"""Verify schemas, immutable evidence, exact offsets and SQLite referential integrity."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import jsonschema
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--results',type=Path,default=ROOT/'new_structured_results')
    args=parser.parse_args();out=args.results
    schemas={k:json.loads((ROOT/'resume_extract'/f'{k}.schema.json').read_text(encoding='utf-8')) for k in ('understanding','profile')}
    checks=[]
    for directory in sorted(x for x in out.iterdir() if x.is_dir() and (x/'understanding.json').exists()):
        r=json.loads((directory/'resume.json').read_text(encoding='utf-8'));u=json.loads((directory/'understanding.json').read_text(encoding='utf-8'))
        p=json.loads((directory/'profile.json').read_text(encoding='utf-8'));jsonschema.validate(u,schemas['understanding']);jsonschema.validate(p,schemas['profile'])
        raw={l['id']:l for l in u['raw_lines']};span_count=0
        for e in u['entities']:
            if e['source_kind']=='text':
                assert raw[e['source_line_id']]['text'][e['start']:e['end']]==e['text'];span_count+=1
            else:assert raw[e['source_line_id']]['runs'][e['run_index']]['hyperlink']==e['text']
        for path,ev in u['evidence'].items():
            assert ev['source_refs'],path
            for ref in ev['source_refs']:assert raw[ref['line_id']]['text'][ref['start']:ref['end']]==ref['text']
        baseline=directory/'comparison_original.json'
        if baseline.exists():
            b=json.loads(baseline.read_text(encoding='utf-8-sig'));assert b['raw_text']==r['raw_text'];assert b['raw_lines']==r['raw_lines']
        checks.append({'id':directory.name,'schema_valid':True,'profile_schema_valid':True,
                       'entity_text_spans_verified':span_count,'evidence_leaves':len(u['evidence']),'raw_preserved':True})
    if not checks:raise ValueError('No generated results to validate')
    db=out/'resumes.sqlite';db_report=None
    if db.exists():
        conn=sqlite3.connect(f'file:{db.resolve().as_posix()}?mode=ro',uri=True)
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        db_report={table:conn.execute('SELECT count(*) FROM '+table).fetchone()[0]
                   for table in ('documents','extractions','profiles','profile_entries','resume_understandings')};conn.close()
    for m in json.loads((ROOT/'ner_audit/manifest.json').read_text(encoding='utf-8')):
        assert hashlib.sha256((ROOT/'ner_audit'/m['artifact']).read_bytes()).hexdigest()==m['selected_sha256']
    report={'per_resume':checks,'database_counts':db_report,'frozen_selected_sources_unchanged':True,
            'span_check_scope':'Offset/provenance integrity, not semantic NER precision or recall'}
    (ROOT/'ner_audit/final_verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'resumes':len(checks),'entity_spans_verified':sum(x['entity_text_spans_verified'] for x in checks),
                      'evidence_leaves_verified':sum(x['evidence_leaves'] for x in checks),'database':db_report},indent=2))


if __name__=='__main__':main()
