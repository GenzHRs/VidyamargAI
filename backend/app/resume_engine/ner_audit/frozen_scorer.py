"""Exact source-label scoring. Runtime extraction never imports this module."""
from pathlib import Path
from collections import Counter,defaultdict
import json,re,unicodedata,argparse,hashlib
ROOT=Path(__file__).resolve().parents[1]
def labels():
 return json.loads((ROOT/'audit/source_labels.json').read_text())


def norm(v,key=''):
 if isinstance(v,str):
  v=' '.join(unicodedata.normalize('NFKC',v).split()).strip().rstrip(':')
  if key=='phones':v=re.sub(r'\D','',v)
  if key=='links':v=re.sub(r'^https?://(?:www\.)?|^www\.','',v,flags=re.I).rstrip('/')
 return v


def facts(data):
 out=defaultdict(list)
 def put(group,path,val,kind=''):
  if val is not None and val!='':out[group].append([path,norm(val,kind)])
 c=data['contact'];put('contact','name',c['name'])
 for key in ['emails','phones','locations','links']:
  for value in c[key]:put('contact',key,value,key)
 for section,keys in [('experience',['title','company','location','start','end','bullet_count']),('education',['degree','institution','start','end','graduation','location','gpa_score','gpa_scale']),('projects',['name','start','end','bullet_count'])]:
  for i,record in enumerate(data[section]):
   for k in keys:put(section,f'{i}.{k}',record.get(k))
   if section=='projects':
    for t in record.get('technologies',[]):put('project_technologies',str(i),t)
 for value in data['certifications']:put('certifications','entry',value)
 for record in data['skills']:
  for value in record['items']:put('skills',record['category'] or '(uncategorized)',value)
 for h in data['headings']:put('headings','heading',h['text'])
 return out


def prediction(r):
 s=r['structured'];c=s['contact']
 v=lambda f:f.get('value') if isinstance(f,dict) else f
 contact={'name':v(c['name']),**{k:[v(x) for x in c[k]] for k in ['emails','phones','locations','links']}}
 out={'contact':contact,'experience':[],'education':[],'projects':[],'certifications':[v(x['name']) for x in s['certifications']],'skills':s['skills'],'headings':[{'text':x['original_heading']} for x in r['sections'] if x['original_heading']]}
 for j in s['experience']:
  dates=v(j['dates']) or {};out['experience'].append({**{k:v(j[k]) for k in ['title','company','location']},'start':dates.get('start'),'end':dates.get('end'),'bullet_count':len(j['bullets'])})
 for e in s['education']:
  dates=v(e['dates']) or {};gpa=v(e['gpa']) or {}
  out['education'].append({**{k:v(e[k]) for k in ['degree','institution','graduation','location']},'start':dates.get('start'),'end':dates.get('end'),'gpa_score':gpa.get('score'),'gpa_scale':gpa.get('scale')})
 for p in s['projects']:out['projects'].append({'name':v(p['name']),'start':(v(p.get('dates')) or {}).get('start'),'end':(v(p.get('dates')) or {}).get('end'),'technologies':[v(x) for x in p.get('technologies',[])],'bullet_count':len(p['bullets'])})
 return out


def compare(e,a):
 e=Counter(json.dumps(v,ensure_ascii=False) for v in e);a=Counter(json.dumps(v,ensure_ascii=False) for v in a)
 tp=sum((e&a).values());fp=sum((a-e).values());fn=sum((e-a).values())
 return {'tp':tp,'fp':fp,'fn':fn,'missing':[json.loads(x) for x in (e-a).elements()],'extra':[json.loads(x) for x in (a-e).elements()]}


def scores(d):
 t,p,n=d['tp'],d['fp'],d['fn'];return {**d,'precision':t/(t+p) if t+p else 1.,'recall':t/(t+n) if t+n else 1.,'f1':2*t/(2*t+p+n) if 2*t+p+n else 1.}


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--predictions',type=Path,default=ROOT.parent/'results')
 parser.add_argument('--report',type=Path,default=ROOT/'audit/metrics.json')
 parser.add_argument('--min-f1',type=float,default=0.)
 args=parser.parse_args()
 gold=labels();rows=[];totals=defaultdict(Counter);unique=defaultdict(Counter);seen=set();word=Counter();uword=Counter()
 for id,g in gold.items():
  r=json.loads((args.predictions/id/'resume.json').read_text());pred=prediction(r)
  assert r['source']['sha256']==g['source']['sha256'],f'Source mismatch: {id}'
  e=facts(g);a=facts(pred);checks={k:scores(compare(e[k],a[k])) for k in sorted(set(e)|set(a))}
  fresh=g['source']['sha256'] not in seen;seen.add(g['source']['sha256'])
  micro=Counter(tp=0,fp=0,fn=0)
  for k,v in checks.items():
   c=Counter({n:v[n] for n in ['tp','fp','fn']});totals[k].update(c)
   if fresh:unique[k].update(c)
   if k!='headings':micro.update(c)
  completeness=r['quality']['completeness']
  wc=Counter({k:completeness[k] for k in ['reference_words','extracted_words','matched_words']});word.update(wc)
  if fresh:uword.update(wc)
  rows.append({'id':id,'file':g['source']['file'],'sha256':g['source']['sha256'],'duplicate_of':next((x['id'] for x in rows if x['sha256']==g['source']['sha256']),None),'source_words':completeness,'schema_errors':r['quality']['schema_errors'],'ocr':r['source']['ocr'],'review_flags':r['needs_review'],'heading_order_exact':[x['text'] for x in pred['headings']]==[x['text'] for x in g['headings']],'metrics':checks,'field_micro':scores(micro)})
 def agg(c):
  micro=Counter(tp=0,fp=0,fn=0)
  for k,v in c.items():
   if k!='headings':micro.update(v)
  return {'field_micro':scores(micro),'by_group':{k:scores(v) for k,v in c.items()}}
 report={'engine_version':r['schema_version'],'audit_date':'2026-10-12','file_count':len(rows),'unique_files':len(seen),'all_files':agg(totals),'unique_only':agg(unique),'word_counts':dict(word),'unique_word_counts':dict(uword),'per_file':rows,
 'methodology':{'labels':'Assistant-reviewed originals and source XML/PDF annotations; not blinded or independently adjudicated. Labels frozen before version 3 changes. Version 3 rules were developed against this set; this is development-set accuracy. Machine predictions were not manually corrected.','normalization':'NFKC, whitespace and trailing label colon. Phone punctuation ignored. URL http(s), www prefix and trailing slash ignored. No synonym expansion.','matching':'Non-null exact scalar claims, with entry ordinal for jobs, education and projects. Wrong value = one FP plus one FN. Null/null is not counted. Skills matched as (category, full source phrase), keeping parentheses and ampersand phrases intact.','scope':'Contact, job identity/location/dates/bullet counts, education identity/location/dates/GPA, project identity/dates/bullet counts/explicit technology lists, certification record labels and explicit skill groups. Headings measured separately. Not every prose assertion or award/publication metadata field is scored.'}}
 report['labels_sha256']=hashlib.sha256((ROOT/'audit/source_labels.json').read_bytes()).hexdigest()
 args.report.parent.mkdir(parents=True,exist_ok=True)
 args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ['per_file','methodology']},indent=2))
 for row in rows:print(row['id'],round(row['field_micro']['f1']*100,2),[(k,v['fp'],v['fn']) for k,v in row['metrics'].items() if v['fp'] or v['fn']])
 return 0 if all(report[k]['field_micro']['f1']>=args.min_f1 for k in ['all_files','unique_only']) and all(not row['schema_errors'] for row in rows) else 1
if __name__=='__main__':raise SystemExit(main())
