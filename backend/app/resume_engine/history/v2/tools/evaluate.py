"""Reproducible micro and per-field metrics against explicit gold, including errors."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import sys
import hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from resume_extract.pipeline import extract
from resume_extract.config import load_config


def key(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False)


def compare(expected,actual):
    e=Counter(map(key,expected));a=Counter(map(key,actual))
    return {'tp':sum((e&a).values()),'fp':sum((a-e).values()),'fn':sum((e-a).values()),
            'missing':[json.loads(x) for x in (e-a).elements()],'extra':[json.loads(x) for x in (a-e).elements()]}


def scores(counts):
    t,p,n=counts['tp'],counts['fp'],counts['fn'];precision=t/(t+p) if t+p else 1.;recall=t/(t+n) if t+n else 1.
    return {**counts,'precision':precision,'recall':recall,'f1':2*t/(2*t+p+n) if 2*t+p+n else 1.}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('inputs',type=Path);parser.add_argument('--gold',type=Path,default=Path('tests/gold'));parser.add_argument('--out',type=Path,default=Path('reports/accuracy.json'));args=parser.parse_args()
    totals=defaultdict(lambda:Counter(tp=0,fp=0,fn=0));rows=[];seen=set();unique_totals=defaultdict(lambda:Counter(tp=0,fp=0,fn=0))
    for goldpath in sorted(args.gold.glob('*.json')):
        gold=json.loads(goldpath.read_text());path=args.inputs/gold['file'];digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=gold['sha256']:raise ValueError('Gold/source SHA mismatch: '+str(path))
        result=extract(path);checks={}
        headings=[{'text':s['original_heading'],'canonical':s['canonical']} for s in result['sections'] if s['original_heading']]
        checks['headings']=compare(gold['headings'],headings)
        checks['heading_detection']=compare([h['text'] for h in gold['headings']],[h['text'] for h in headings])
        for field,expected in gold['fields'].items():
            actual=result['fields'][field]
            checks[field]=compare([expected] if field=='name' else expected,[actual['value']] if field=='name' and actual else [] if field=='name' else [v['value'] for v in actual])
        actualjobs=[{'title':j['title']['value'],'company':j['company']['value'],'start':(j['dates']['value'] or {}).get('start'),'end':(j['dates']['value'] or {}).get('end'),'bullet_count':len(j['bullets'])} for j in result['fields']['experience']]
        checks['experience_entries']=compare(gold['experience'],actualjobs)
        # Atomic job fields are indexed by entry order; wrong assignment is penalized.
        for field in ('title','company','start','end','bullet_count'):
            checks['experience_'+field]=compare([[i,j[field]] for i,j in enumerate(gold['experience'])],[[i,j[field]] for i,j in enumerate(actualjobs)])
        is_unique=gold['persona'] not in seen;seen.add(gold['persona'])
        for metric,values in checks.items():
            totals[metric].update({k:values[k] for k in ('tp','fp','fn')})
            if is_unique:unique_totals[metric].update({k:values[k] for k in ('tp','fp','fn')})
        rows.append({'file':gold['file'],'persona':gold['persona'],'completeness':result['quality']['completeness'],'checks':{k:scores(v) for k,v in checks.items()},'review_count':len(result['needs_review'])})
    atomic=Counter(tp=0,fp=0,fn=0);unique_atomic=Counter(tp=0,fp=0,fn=0)
    for k,v in totals.items():
        if k not in ('headings','heading_detection','experience_entries'):atomic.update(v);unique_atomic.update(unique_totals[k])
    report={'label_origin':'Task-authored development annotations; no original user gold supplied. Not a held-out score.','files':len(rows),'unique_personas':len(seen),
            'field_micro':scores(atomic),'unique_persona_field_micro':scores(unique_atomic),'per_metric':{k:scores(v) for k,v in totals.items()},'unique_persona_per_metric':{k:scores(v) for k,v in unique_totals.items()},'per_file':rows}
    targets=load_config()['validate']
    report['targets']={'strict_completeness':all(row['completeness']['status']=='pass' for row in rows),'word_recall':all(row['completeness'].get('recall',0)>=targets['target_word_recall'] for row in rows),'heading_f1':report['per_metric']['headings']['f1']>=targets['target_heading_f1'],'field_f1':report['field_micro']['f1']>=targets['target_field_f1']}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('per_file','unique_persona_per_metric')},indent=2))
    for row in rows:
        errors={k:{'missing':v['missing'],'extra':v['extra']} for k,v in row['checks'].items() if v['fp'] or v['fn']}
        if errors:print(row['file'],json.dumps(errors,ensure_ascii=False))
    if not all(report['targets'].values()):raise SystemExit(1)
if __name__=='__main__':main()
