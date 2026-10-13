"""Evaluate independently annotated saved artifacts without changing labels.

Required labels: {annotation_method: 'manual_source_review', documents:
[{artifact: 'relative/path/resume.json', source_sha256: '...', gold: {...}}]}.
The gold object uses source_labels.json's contact/experience/education/projects/
skills/certifications/headings schema. Optional entity_spans provides a COMPLETE
annotation for every listed label type: {labels: [...], spans: [{label,
source_line_id,start,end,text,source_kind}]}.

Self-declared manual annotation is recorded, not independently certified here.
No evaluation result alone establishes generalization to the resume population.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from resume_extract.understanding import understand_artifact
from resume_extract.pipeline import write_outputs
spec=importlib.util.spec_from_file_location('frozen_scorer',ROOT/'frozen_scorer.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('labels',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();blob=args.labels.read_bytes();labels=json.loads(blob.decode('utf-8'))
    if labels.get('annotation_method')!='manual_source_review':parser.error('Manual source review declaration is required')
    forbidden={x['sha256'] for x in json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))}
    seen=set();prepared=[]
    for row in labels.get('documents',[]):
        sha=row['source_sha256']
        if sha in forbidden or sha in seen:parser.error('Known regression document or duplicate in unseen set: '+sha)
        seen.add(sha);artifact=(args.labels.parent/row['artifact']).resolve()
        out=args.out.resolve()
        if out==artifact.parent or out.is_relative_to(artifact.parent) or artifact.parent.is_relative_to(out):parser.error('Output must be separate from input artifacts')
        if args.labels.resolve().is_relative_to(out):parser.error('Output cannot contain the annotation file')
        data=json.loads(artifact.read_text(encoding='utf-8-sig'))
        if data.get('source',{}).get('sha256')!=sha:parser.error('Source SHA mismatch')
        gold=row['gold']
        for key in ('contact','experience','education','projects','skills','certifications','headings'):
            if key not in gold:parser.error('Missing gold section '+key)
        prepared.append((row,artifact))
    if not prepared:parser.error('No annotated unseen documents supplied')
    # Freeze exact incoming annotations before any prediction.
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'frozen_annotations.json').write_bytes(blob)
    totals=Counter(tp=0,fp=0,fn=0);spans=Counter(tp=0,fp=0,fn=0);rows=[]
    for row,artifact in prepared:
        result,rich=understand_artifact(artifact);sha=row['source_sha256']
        write_outputs(result,args.out/sha[:16]);(args.out/sha[:16]/'understanding.json').write_text(json.dumps(rich,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        gold=s.facts(row['gold']);pred=s.facts(s.prediction(result));counts=Counter(tp=0,fp=0,fn=0)
        for group in set(gold)|set(pred):
            if group=='headings':continue
            d=s.compare(gold[group],pred[group]);counts.update({k:d[k] for k in counts})
        totals.update(counts);sr=None
        if row.get('entity_spans'):
            annotation=row['entity_spans'];allowed=set(annotation['labels'])
            fields=('label','source_line_id','start','end','text','source_kind')
            expected=[[e.get(k) for k in fields] for e in annotation['spans']]
            actual=[[e.get(k) for k in fields] for e in rich['entities'] if e['label'] in allowed]
            sr=s.scores(s.compare(expected,actual));spans.update({k:sr[k] for k in spans})
        rows.append({'sha256':sha,'field_mapping':s.scores(counts),'entity_spans':sr,
                     'completeness':result['quality']['completeness'],'review_status':rich['review_status']})
    report={'documents':len(rows),'annotation_sha256':hashlib.sha256(blob).hexdigest(),
            'annotation_provenance':'self-declared manual source review; independence must be verified by dataset owner',
            'regression_sha_overlap':False,'field_mapping':s.scores(totals),
            'entity_span_metrics':s.scores(spans) if any(r['entity_spans'] for r in rows) else None,
            'per_document':rows,'population_accuracy_claim':False}
    (args.out/'unseen_metrics.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
