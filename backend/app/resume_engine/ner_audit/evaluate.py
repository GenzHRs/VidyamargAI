"""Frozen-reference before/after evaluation. Never imported by runtime extraction.

Entity values are scored on the annotated field subset (not all NER spans).
Grouping is scored using record identity, metadata, counts, and full bullets
where source-reviewed bullet annotations exist. Unannotated sections are excluded.
"""
from collections import Counter
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unicodedata

ROOT=Path(__file__).resolve().parent
FROZEN={'source_labels.json':'8f7542578c16a35de07a2860a2667630dc6770f4375fe4df0774ae52bdd702af',
        'source_bullets.json':'16e99ae406f3957d17fe94704bd7916c5e2551e6f2b6da1e090e564f5bc087b9'}
spec=importlib.util.spec_from_file_location('frozen_scorer',ROOT/'frozen_scorer.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


def clean(text):
    return ' '.join(re.sub(r'^[•–−*-]\s*','',unicodedata.normalize('NFKC',text).strip()).split())


def tokens(text):
    return re.findall(r'\w+',unicodedata.normalize('NFKC',text).casefold())


def entity_values(facts):
    out=[]
    for kind,items in facts.items():
        if kind=='headings':continue
        for path,val in items:
            key=path.split('.')[-1]
            if key=='bullet_count':continue
            # Remove record ownership and skill category; retain semantic type.
            if kind in ('skills','project_technologies'):label='SKILL'
            elif kind=='certifications':label='CERTIFICATION'
            else:label={'name':'PERSON' if kind=='contact' else 'PROJECT','company':'ORG','institution':'INSTITUTION',
                        'title':'JOB_TITLE','degree':'DEGREE','emails':'EMAIL','phones':'PHONE','links':'URL',
                        'locations':'LOCATION','location':'LOCATION','start':'DATE','end':'DATE','graduation':'DATE',
                        'gpa_score':'GPA_SCORE','gpa_scale':'GPA_SCALE'}.get(key,key)
            out.append([label,val])
    return out


def record_identity(kind,item):
    if kind=='certifications':return item
    if kind=='experience':return item.get('title')
    if kind=='education':return item.get('degree')
    return item.get('name')


def grouping(g,p,r,bullets):
    counts=Counter(expected=0,predicted=0,exact=0,missing_records=0,extra_records=0,false_merges=0,false_splits=0)
    errors=[]
    for kind in ('experience','education','projects','certifications'):
        expected=g[kind];actual=p[kind];records=r['structured'][kind]
        counts['expected']+=len(expected);counts['predicted']+=len(actual)
        for i,ex in enumerate(expected):
            same=i<len(actual) and ex==actual[i]
            # Gold may omit optional empty technology lists; compare frozen facts instead.
            if kind!='certifications' and i<len(actual):
                same=all(s.norm(actual[i].get(k))==s.norm(v) for k,v in ex.items())
            if kind in bullets and i<len(bullets[kind]):
                same=same and i<len(records) and [clean(x) for x in records[i]['bullets']]==[clean(x) for x in bullets[kind][i]]
            counts['exact']+=int(same)
            if not same:errors.append({'section':kind,'ordinal':i,'reason':'Record metadata, ownership/count, or annotated full bullet differs'})
        # Identity-level alignment detects absent/extra records separately from wrong fields.
        # Credential training-detail overrun is a field error, not an extra credential.
        expected_anchors=[tokens(record_identity(kind,x) or '') for x in expected]
        memberships=[]
        for j,rec in enumerate(records):
            # Same source line may contain two separate certifications. Assign
            # its explicit primary value, not the whole shared source block.
            rt=tokens(record_identity(kind,actual[j]) or '');members=[]
            for i,anchor in enumerate(expected_anchors):
                if anchor and (rt==anchor or kind=='certifications' and rt[:len(anchor)]==anchor):members.append(i)
            memberships.append(set(members))
        seen=set().union(*memberships) if memberships else set()
        counts['missing_records']+=len(expected)-len(seen)
        # Use expected bullet/source-line intersections to detect splits even when
        # only the first fragment contains the record title.
        for i,expected_bullets in enumerate(bullets.get(kind,[])):
            for bullet in expected_bullets:
                bt=tokens(bullet)
                for j,rec in enumerate(records):
                    for lid in rec['source_line_ids']:
                        raw=next((x for x in r['raw_lines'] if x['id']==lid),None)
                        if not raw:continue
                        lt=tokens(raw['text'])
                        if len(lt)>=2 and any(bt[k:k+len(lt)]==lt for k in range(len(bt)-len(lt)+1)):
                            memberships[j].add(i)
        counts['false_splits']+=sum(sum(i in mem for mem in memberships)>1 for i in range(len(expected)))
        counts['false_merges']+=sum(len(m)>1 for m in memberships)
        counts['extra_records']+=sum(not m for m in memberships)
    counts['precision']=counts['exact']/counts['predicted'] if counts['predicted'] else 1
    counts['recall']=counts['exact']/counts['expected'] if counts['expected'] else 1
    return dict(counts),errors


def evaluate(result_root=None):
    for filename,sha in FROZEN.items():
        if hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()!=sha:raise ValueError('Frozen labels changed: '+filename)
    gold=json.loads((ROOT/'source_labels.json').read_text(encoding='utf-8'))
    bullet_gold=json.loads((ROOT/'source_bullets.json').read_text(encoding='utf-8'))
    totals=Counter(tp=0,fp=0,fn=0);entities=Counter(tp=0,fp=0,fn=0);records=Counter();bs=Counter();rows=[]
    for m in json.loads((ROOT/'manifest.json').read_text(encoding='utf-8')):
        path=Path(result_root)/m['sha256'][:16]/'resume.json' if result_root else ROOT/m['artifact']
        r=json.loads(path.read_text(encoding='utf-8'));rid=m['id'];g=gold[rid]
        if r['source']['sha256']!=m['sha256']:raise ValueError('Source identity mismatch')
        if not result_root and hashlib.sha256(path.read_bytes()).hexdigest()!=m['selected_sha256']:raise ValueError('Baseline artifact changed')
        p=s.prediction(r);e=s.facts(g);a=s.facts(p);count=Counter(tp=0,fp=0,fn=0);errors={}
        for kind in set(e)|set(a):
            d=s.compare(e[kind],a[kind])
            if kind!='headings':count.update({k:d[k] for k in ('tp','fp','fn')})
            if d['fp'] or d['fn']:errors[kind]=d
        totals.update(count);ed=s.compare(entity_values(e),entity_values(a));entities.update({k:ed[k] for k in ('tp','fp','fn')})
        rc,record_errors=grouping(g,p,r,bullet_gold[rid]);records.update({k:v for k,v in rc.items() if k not in ('precision','recall')})
        bullet_ok=True
        for kind,entries in bullet_gold[rid].items():
            actual=r['structured'][kind]
            bs['expected']+=sum(len(x) for x in entries);bs['predicted']+=sum(len(x['bullets']) for x in actual)
            for i,b in enumerate(entries):
                for j,text in enumerate(b):
                    pred=actual[i]['bullets'][j] if i<len(actual) and j<len(actual[i]['bullets']) else ''
                    ok=clean(pred)==clean(text);bs['exact']+=int(ok);bullet_ok=bullet_ok and ok
        headings=[h['text'] for h in g['headings']]==[h['text'] for h in p['headings']]
        mapped_pass=not(count['fp'] or count['fn']) and bullet_ok and headings
        strict_pass=mapped_pass and r['quality']['completeness']['status']=='pass' and not r['quality']['schema_errors']
        rows.append({'id':rid,'filename':r['source']['filename'],'field_metrics':s.scores(count),'field_errors':errors,
                     'record_grouping':rc,'record_errors':record_errors,'annotated_mapping_pass':mapped_pass,
                     'strict_audited_document_pass':strict_pass,'completeness':r['quality']['completeness'],'schema_errors':r['quality']['schema_errors']})
    n=len(rows)
    return {'unique_resumes':n,'scope':'Frozen annotated fields and record metadata; full job bullets for every resume and full project bullets for U01/U02. Other sections lack complete manual gold.',
            'entity_metric_scope':'Typed entity VALUE extraction on annotated fields; not an exact-span NER benchmark',
            'reference_sha256':FROZEN,'field_mapping':s.scores(totals),'entity_value_extraction':s.scores(entities),
            'record_grouping':{**records,'precision':records['exact']/records['predicted'],'recall':records['exact']/records['expected']},
            'full_bullet_comparison':dict(bs),'annotated_mapping_pass_count':sum(x['annotated_mapping_pass'] for x in rows),
            'strict_audited_document_pass_count':sum(x['strict_audited_document_pass'] for x in rows),
            'strict_audited_document_pass_rate':sum(x['strict_audited_document_pass'] for x in rows)/n,
            'independent_unseen_real_resumes':0,'accuracy_95_claim':'NOT ESTABLISHED','per_resume':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--results',type=Path,default=ROOT.parent/'new_structured_results')
    args=parser.parse_args();out={'before':evaluate(),'after':evaluate(args.results)}
    (ROOT/'before_after_metrics.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:{x:y for x,y in v.items() if x!='per_resume'} for k,v in out.items()},indent=2))


if __name__=='__main__':main()
