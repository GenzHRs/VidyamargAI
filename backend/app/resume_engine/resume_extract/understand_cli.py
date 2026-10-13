"""Batch source selection and offline understanding. Input trees are read-only."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from .understanding import understand_artifact
from .pipeline import write_outputs


def dump(path,data):
    """Atomic UTF-8 output replacement; no partially written JSON on failure."""
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=path.parent,delete=False) as handle:
        temp=Path(handle.name);json.dump(data,handle,ensure_ascii=False,indent=2);handle.write('\n')
    temp.replace(path)


def inventory(source):
    """Read every artifact, rank evidence quality, select one source per folder.

    Full extraction JSON is preferred to text because it retains typography,
    geometry and embedded hyperlink targets. A saved structured JSON is never
    selected as source. No filenames or candidate names receive corrections.
    """
    source=Path(source);paths=[source] if source.is_file() else sorted(p for p in source.rglob('*') if p.is_file())
    rows=[];candidates={}
    for path in paths:
        blob=path.read_bytes();row={'path':str(path),'sha256':hashlib.sha256(blob).hexdigest(),'bytes':len(blob),'eligible':False}
        score=0;document=None
        if path.suffix.lower()=='.json':
            try:
                data=json.loads(blob.decode('utf-8-sig'));row['json_valid']=True
                if isinstance(data,dict) and data.get('raw_lines') and all(isinstance(l.get('text'),str) and l.get('id') for l in data['raw_lines']):
                    # Ignore the understanding sidecar: it is an output, not reader evidence.
                    if 'understanding_schema_version' not in data:
                        score=100+bool(data.get('source_text'))*10+bool(data.get('source'))*5
                        score+=min(5,sum(bool(l.get('bbox') or l.get('runs')) for l in data['raw_lines']))
                        document=data.get('source',{}).get('sha256')
                        if path.name=='resume.json':score+=1
                        row['raw_line_count']=len(data['raw_lines'])
                else:row['reason']='Comparison/metadata JSON or no raw-line evidence'
            except (ValueError,UnicodeError,TypeError,AttributeError):row['reason']='Invalid or unsupported JSON';row['json_valid']=False
        elif path.suffix.lower() in ('.txt','.md'):
            try:
                txt=blob.decode('utf-8-sig');row['characters']=len(txt)
                if source.is_file() or path.stem.lower() in ('raw','natural','natural_text','extracted','extracted_text','source','normalized'):
                    score={'raw':65,'natural':60,'natural_text':60,'source':55,'normalized':40}.get(path.stem.lower(),50)
                else:row['reason']='Generated presentation or unrecognized text role; retained in inventory'
            except UnicodeError:row['reason']='Not UTF-8 text'
        if score:
            row.update(eligible=True,score=score,document_sha256=document)
            candidates.setdefault(path.parent,[]).append((score,path,row))
        rows.append(row)
    selected=[]
    for folder,items in sorted(candidates.items(),key=lambda x:str(x[0])):
        full=[x for x in items if x[0]>=100]
        groups={}
        if full:
            for item in full:groups.setdefault(item[2]['document_sha256'] or item[2]['sha256'],[]).append(item)
        else:groups['text_fallback']=items
        for group in groups.values():
            best=sorted(group,key=lambda x:(-x[0],str(x[1])))[0]
            selected.append({'path':str(best[1]),'artifact_sha256':best[2]['sha256'],'document_sha256':best[2]['document_sha256'],
                             'reason':'Highest evidence rank for source identity within folder; structured content is comparison only',
                             'alternatives':[str(x[1]) for x in group if x[1]!=best[1]]})
    return rows,selected


def store(conn,result,rich):
    """Reuse the supplied mapper's four tables; add a versioned NER sidecar table."""
    from .application_mapping import map_result,save_database
    mapped=map_result(result)
    conn.executescript(Path(__file__).with_name('storage_schema.sql').read_text(encoding='utf-8'))
    conn.execute('CREATE TABLE IF NOT EXISTS resume_understandings (understanding_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(profile_id), schema_version TEXT NOT NULL, artifact_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS resume_understanding_heads (profile_id TEXT PRIMARY KEY REFERENCES profiles(profile_id), understanding_id TEXT NOT NULL REFERENCES resume_understandings(understanding_id))')
    payload=json.dumps(rich,ensure_ascii=False,sort_keys=True);uid=hashlib.sha256(payload.encode('utf-8')).hexdigest()
    save_database(conn,mapped,result)
    with conn:
        conn.execute('INSERT INTO resume_understandings VALUES (?,?,?,?,?) ON CONFLICT DO NOTHING',
                     (uid,mapped['record_id'],rich['understanding_schema_version'],rich['artifact_sha256'],payload))
        conn.execute('INSERT INTO resume_understanding_heads VALUES (?,?) ON CONFLICT(profile_id) DO UPDATE SET understanding_id=excluded.understanding_id',
                     (mapped['record_id'],uid))
    return mapped


def load_profile(conn,profile_id):
    """Application adapter for a caller's existing API/frontend. No HTTP server."""
    row=conn.execute('SELECT payload_json FROM profiles WHERE profile_id=?',(profile_id,)).fetchone()
    if not row:return None
    result={'profile':json.loads(row[0]),'understanding':None}
    exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='resume_understanding_heads'").fetchone()
    if exists:
        row=conn.execute('SELECT u.payload_json FROM resume_understanding_heads h JOIN resume_understandings u ON u.understanding_id=h.understanding_id WHERE h.profile_id=?',(profile_id,)).fetchone()
        if row:result['understanding']=json.loads(row[0])
    return result


def run(source,out,db=None):
    source=Path(source).resolve();out=Path(out).resolve()
    if not source.exists():raise ValueError('Input does not exist')
    protected=source if source.is_dir() else source.parent
    if out==protected or out.is_relative_to(protected) or protected.is_relative_to(out):
        raise ValueError('Output must be a separate sibling tree, outside the input artifact tree')
    if db and Path(db).resolve().is_relative_to(protected):raise ValueError('Database cannot be written inside the input tree')
    rows,selected=inventory(source)
    if not selected:raise ValueError('No reusable raw-line JSON or natural-text artifact found')
    out.mkdir(parents=True,exist_ok=True);dump(out/'artifact_inventory.json',rows)
    dump(out/'source_selection.json',selected);summary=[];seen={};failed=False
    if db:Path(db).resolve().parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(db) if db else None
    try:
        for selected_source in selected:
            path=Path(selected_source['path'])
            try:
                if hashlib.sha256(path.read_bytes()).hexdigest()!=selected_source['artifact_sha256']:raise ValueError('Input changed after source selection')
                result,rich=understand_artifact(path)
                sha=result['source']['sha256'];key=sha[:16]
                if sha in seen:
                    summary.append({'input':str(path),'duplicate_of':seen[sha],'status':'duplicate','document_sha256':sha});continue
                seen[sha]=key;directory=out/key
                write_outputs(result,directory);dump(directory/'understanding.json',rich)
                # Render the full typed profile, including all unclassified content.
                text=[]
                for section in rich['section_order']:
                    text.extend([section.upper(),json.dumps(rich['profile'][section],ensure_ascii=False,indent=2),''])
                text.extend(['UNCLASSIFIED',json.dumps(rich['unclassified'],ensure_ascii=False,indent=2)])
                (directory/'understanding.txt').write_text('\n'.join(text)+'\n',encoding='utf-8')
                if conn:mapped=store(conn,result,rich)
                else:
                    from .application_mapping import map_result
                    mapped=map_result(result)
                dump(directory/'profile.json',mapped)
                # Keep baseline separate; it is never interpreted as truth.
                if path.suffix.lower()=='.json':(directory/'comparison_original.json').write_bytes(path.read_bytes())
                dump(directory/'source_selection.json',selected_source)
                summary.append({'input':str(path),'output':key,'document_sha256':sha,'status':rich['review_status'],
                                'completeness':result['quality']['completeness']['status'],
                                'entities':len(rich['entities']),'records':len(rich['records']),
                                'issues':len(rich['validation']['issues']),'unclassified_lines':len(rich['unclassified'])})
                if result['quality']['schema_errors'] or any(x['code']=='missing_evidence' for x in rich['validation']['issues']):failed=True
            except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as exc:
                summary.append({'input':str(path),'status':'error','error':str(exc)});failed=True
    finally:
        if conn:conn.close()
    dump(out/'batch_summary.json',summary)
    return summary,failed


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--out',type=Path,default=Path('new_structured_results'))
    parser.add_argument('--db',type=Path);parser.add_argument('--strict',action='store_true',help='Exit 2 when human review is required')
    args=parser.parse_args(argv)
    try:rows,failed=run(args.source,args.out,args.db)
    except (ValueError,OSError) as exc:parser.error(str(exc))
    print(json.dumps(rows,ensure_ascii=False,indent=2))
    if failed:return 1
    return 2 if args.strict and any(r['status']=='needs_review' for r in rows) else 0


if __name__=='__main__':raise SystemExit(main())
