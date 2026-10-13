"""Offline, evidence-preserving mapping of extraction JSON to versioned profiles.

Python standard library only. Input must be a full v3 resume extraction result.
This mapper does not parse PDFs and does not establish factual accuracy.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sqlite3

VERSION = '1.0.0'
ROOT = Path(__file__).resolve().parent
ORDER = ['contact','summary','experience','education','projects','skills',
         'certifications','publications','awards','metrics','other_sections']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def value(item):
    return item.get('value') if isinstance(item,dict) and 'value' in item else item


def clean_bullet(text):
    return re.sub(r'^[•–−*-]\s+', '', text.strip())


def date_value(raw):
    """Preserve source precision. Do not invent month/day or today's end date."""
    out={'raw':raw,'normalized':None,'precision':None}
    if raw is None:return out
    if re.fullmatch(r'Present|Current|Now|Ongoing',raw,re.I):
        out['precision']='open';return out
    if re.fullmatch(r'(?:19|20)\d{2}',raw):
        out.update(normalized=raw,precision='year');return out
    months={name:i for i,name in enumerate(['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'],1)}
    match=re.fullmatch(r'([A-Za-z]+)\s+((?:19|20)\d{2})',raw.strip())
    if match and match[1][:3].lower() in months:
        out.update(normalized=f'{match[2]}-{months[match[1][:3].lower()]:02d}',precision='month')
    else:
        match=re.fullmatch(r'(0?[1-9]|1[0-2])/((?:19|20)\d{2})',raw.strip())
        if match:out.update(normalized=f'{match[2]}-{int(match[1]):02d}',precision='month')
    return out


def date_range(item):
    dates=value(item) or {}
    return {'start':date_value(dates.get('start')),'end':date_value(dates.get('end')),
            'ongoing_as_reported':bool(re.fullmatch(r'Present|Current|Now|Ongoing',dates.get('end',''),re.I))}


def map_result(data, extraction_id=None):
    if not isinstance(data,dict) or 'structured' not in data or 'source' not in data:
        raise ValueError('Expected full resume.json with source and structured fields; do not pass structured.json or quality.json')
    if data.get('schema_version')!='3.0.0':raise ValueError('This mapper supports extraction schema 3.0.0 only')
    doc_id=data['source'].get('sha256','')
    if not re.fullmatch(r'[0-9a-f]{64}',doc_id):raise ValueError('Missing/invalid source SHA-256')
    s=data['structured'];raw={l['id']:l for l in data['raw_lines']}
    extraction_id=extraction_id or digest(json.dumps(data,ensure_ascii=False,sort_keys=True).encode('utf-8'))
    mapper_hash=digest(Path(__file__).read_bytes())
    record_id=digest((extraction_id+VERSION+mapper_hash).encode('ascii'))
    evidence={};changes=[];issues=[]

    def ev(path,item,fallback=None):
        item=item if isinstance(item,dict) else {}
        ids=item.get('source_line_ids',fallback or [])
        if not set(ids)<=set(raw):raise ValueError('Unknown source line in '+path)
        evidence[path]={'source_line_ids':list(dict.fromkeys(ids)),
                        'confidence':item.get('confidence'),
                        'confidence_kind':'uncalibrated_rule_score'}

    def field(path,item):
        ev(path,item);return value(item)

    def record(path,item):
        ev(path,item)
        return {'source_text':item.get('text',''),'source_line_ids':item.get('source_line_ids',[])}

    def change(path,before,after,reason,ids):
        if before!=after:changes.append({'path':path,'before':before,'after':after,'reason':reason,'source_line_ids':ids})

    c=s['contact']
    profile={'contact':{'full_name':field('contact.full_name',c['name']),
                        'headline':None,'emails':[],'phones':[],'locations':[], 'links':[]},
             **{k:[] for k in ORDER if k!='contact'}}
    # Only a preamble subtitle can be a headline; do not use a past job title.
    preamble_ids={i for section in data['sections'] if section['canonical'] in ('preamble','contact') for i in section['line_ids']}
    headline=next((l for l in data['lines'] if l['id'] in preamble_ids and l['tag']=='SUBTITLE'),None)
    if headline:
        profile['contact']['headline']=headline['text'];ev('contact.headline',{'source_line_ids':headline['source_ids']})
    for key in ['emails','phones','locations']:
        for i,item in enumerate(c[key]):
            text=field(f'contact.{key}[{i}]',item)
            profile['contact'][key].append({'raw':text,'normalized':item.get('normalized'),
                'valid':item.get('valid')} if key=='phones' else text)
    profile['summary']=[field(f'summary[{i}]',p) for i,p in enumerate(s['summary'])]

    for section,title in [('experience','title'),('education','degree'),('projects','name')]:
        for i,item in enumerate(s[section]):
            path=f'{section}[{i}]';entry={**record(path,item),'ordinal':i}
            names={'experience':['title','company','location'],'education':['degree','institution','location'],'projects':['name']}[section]
            for key in names:entry[key]=field(path+'.'+key,item[key])
            entry['dates']=date_range(item['dates']);ev(path+'.dates',item['dates'])
            if section in ('experience','projects'):
                entry['bullets']=[clean_bullet(b) for b in item['bullets']]
                entry['links']=[]
                for j in range(len(entry['bullets'])):
                    ev(path+f'.bullets[{j}]',{'source_line_ids':item.get('source_line_ids',[])})
            if section=='experience':
                # Preserve explicit Remote/Hybrid/On-site qualifiers discarded by the location field.
                header_text='\n'.join(l['text'] for l in data['lines'] if l['tag']!='BULLET' and set(l.get('source_ids',[])) & set(item.get('source_line_ids',[])))
                mode=re.search(r'\b(Remote|Hybrid|On[- ]site)\b',header_text,re.I)
                entry['work_mode']=mode[1] if mode else None
                if mode:ev(path+'.work_mode',item)
            elif section=='education':
                entry['graduation']=date_value(field(path+'.graduation',item['graduation']))
                entry['gpa']=field(path+'.gpa',item['gpa'])
                dissertation=re.search(r'(?:Dissertation|Thesis):\s*([^\n]+)',item.get('text',''),re.I)
                entry['dissertation_or_thesis']=dissertation[1] if dissertation else None
                if dissertation:ev(path+'.dissertation_or_thesis',item)
            else:
                entry['description']=item['description'];entry['technologies']=[field(path+f'.technologies[{j}]',t) for j,t in enumerate(item['technologies'])]
                if entry['name'] and (entry['name'][0].islower() or entry['name'].rstrip().endswith('.')):
                    issues.append({'path':path+'.name','reason':'Possible bullet continuation used as a project name; compare source','confidence':0.0})
            profile[section].append(entry)

    # Preserve categories; combine multiple table rows with the same category.
    for item in s['skills']:
        category=item['category'];group=next((g for g in profile['skills'] if g['category']==category),None)
        if group is None:
            group={'category':category,'items':[],'source_records':[]};profile['skills'].append(group)
        group['source_records'].append(copy.deepcopy(item))
        for skill in item['items']:
            if skill not in group['items']:group['items'].append(skill)
    for i,g in enumerate(profile['skills']):
        ev(f'skills[{i}]',{'source_line_ids':[sid for r in g['source_records'] for sid in r['source_line_ids']]})

    for i,item in enumerate(s['certifications']):
        path=f'certifications[{i}]';name=value(item['name']);details=item['details'];issuer=None
        ids=item.get('source_line_ids',[])
        # Use explicitly marked prose boundaries, not arbitrary commas in titles.
        split=re.split(r'\s+(?=(?:Trained in|Completed hands-on|Completed training|Course covered)\b)',name or '',maxsplit=1,flags=re.I)
        if len(split)==2:
            name=split[0];details=' '.join(x for x in [split[1],details] if x)
        # Separate title/issuer only when the source shows an organization + locality.
        parts=re.split(r'\s+[–—-]\s+',name or '',maxsplit=1)
        if len(parts)==2 and ',' in parts[1]:name=parts[0];issuer=parts[1].rstrip('.')
        prefix,sep,body=details.partition(': ')
        if issuer is None and sep and ',' in prefix:
            issuer=prefix;details=body
        # Real table cell layout is strong issuer evidence.
        lines=[raw[sid] for sid in ids]
        title_cells={l.get('cell') for l in lines if name and name in l['text']}
        issuer_lines=[l for l in lines if l.get('table') and l.get('cell') not in title_cells
                      and not re.search(r'\b(?:License|Active|Expired|Graduat)\b',l['text'],re.I)]
        if issuer is None and issuer_lines:issuer=' '.join(l['text'] for l in issuer_lines)
        license_match=re.search(r'\bLicense\s*#\s*([\w-]+)',item.get('text',''),re.I)
        status_match=re.search(r'\((Active|Expired|Inactive)\)',item.get('text',''),re.I)
        entry={**record(path,item),'ordinal':i,'name':name,'issuer':issuer,'details':details,
               'license_id':license_match[1] if license_match else None,
               'status_as_reported':status_match[1] if status_match else None,'links':[]}
        profile['certifications'].append(entry)
        ev(path+'.name',item['name']);ev(path+'.issuer',item);ev(path+'.details',item)
        change(path,{'name':value(item['name']),'issuer':None,'details':item['details']},
               {'name':name,'issuer':issuer,'details':details},'Separate explicitly indicated credential title, issuer and training details',ids)

    for item in s['other_sections']:
        section=item['canonical'] if item['canonical'] in ('awards','publications','metrics') else 'other_sections'
        i=len(profile[section]);entry={**copy.deepcopy(item),'ordinal':i,'links':[]}
        profile[section].append(entry);ev(f'{section}[{i}]',item)

    # Match links to their source record. Never treat every document URI as contact.
    owned_link_candidates=list(c['links'])
    # The understanding engine already filters contact links. Recover record
    # hyperlinks from immutable runs so compatibility profiles retain them too.
    for line in data['raw_lines']:
        for run in line.get('runs',[]):
            url=run.get('hyperlink')
            if url and not url.startswith('mailto:') and not any(value(x)==url for x in owned_link_candidates):
                owned_link_candidates.append({'value':url,'source_line_ids':[line['id']]})
        for match in re.finditer(r'(?:https?://|www\.)[^\s<>|]+',line['text']):
            url=match.group().rstrip('.,;)')
            if not any(value(x)==url for x in owned_link_candidates):
                owned_link_candidates.append({'value':url,'source_line_ids':[line['id']]})
    for item in owned_link_candidates:
        ids=set(item.get('source_line_ids',[]));owners=[]
        for section in ['certifications','experience','education','projects','awards','publications','metrics','other_sections']:
            for i,entry in enumerate(profile[section]):
                if ids and ids<=set(entry.get('source_line_ids',[])):owners.append((section,i,entry))
        if len(owners)==1:
            section,i,entry=owners[0];entry.setdefault('links',[]).append(value(item));path=f'{section}[{i}].links'
            ev(path,item);change(path,'contact.links',value(item),'Move URI to the record containing its source evidence',sorted(ids))
        elif owners:
            profile.setdefault('unassigned_links',[]).append(value(item));ev('unassigned_links',item)
            issues.append({'path':'unassigned_links','reason':'Multiple record owners; URL retained without guessing','confidence':0.0})
        else:
            # Check actual contact-section raw provenance, including normalized line IDs.
            contact_raw={sid for l in data['lines'] if l['id'] in preamble_ids for sid in l['source_ids']}
            if ids and ids<=contact_raw:
                profile['contact']['links'].append(value(item));ev(f"contact.links[{len(profile['contact']['links'])-1}]",item)
            else:
                profile.setdefault('unassigned_links',[]).append(value(item));ev('unassigned_links',item)
                issues.append({'path':'unassigned_links','reason':'URL has no unambiguous contact/record ownership','confidence':0.0})

    reviews=copy.deepcopy(data.get('needs_review',[]))+issues
    out={'mapping_schema_version':VERSION,'record_id':record_id,'document_id':doc_id,
         'candidate_id':None,'extraction_id':extraction_id,'mapper_sha256':mapper_hash,
         'source':copy.deepcopy(data['source']),'section_order':ORDER,'entry_order':'source',
         'profile':profile,'evidence':evidence,'source_sections':copy.deepcopy(data['sections']),
         'quality':copy.deepcopy(data['quality']),'review_status':'needs_review' if reviews or data['quality']['completeness']['status']!='pass' else 'mapped_unverified',
         'review':reviews,'mapping_changes':changes}
    return out


def save_database(conn,mapped,original):
    p=mapped['profile'];dump=lambda x:json.dumps(x,ensure_ascii=False)
    with conn:
        conn.execute('INSERT INTO documents VALUES (?,?,?) ON CONFLICT DO NOTHING',
                     (mapped['document_id'],mapped['source']['filename'],mapped['source']['type']))
        conn.execute('INSERT INTO extractions VALUES (?,?,?,?) ON CONFLICT DO NOTHING',
                     (mapped['extraction_id'],mapped['document_id'],original['schema_version'],dump(original)))
        conn.execute('INSERT INTO profiles VALUES (?,?,?,?,?,?,?) ON CONFLICT DO NOTHING',
                     (mapped['record_id'],mapped['extraction_id'],VERSION,mapped['mapper_sha256'],p['contact']['full_name'],mapped['review_status'],dump(mapped)))
        for section in ORDER:
            entries=[p[section]] if section=='contact' else p[section]
            for i,entry in enumerate(entries):
                conn.execute('INSERT INTO profile_entries VALUES (?,?,?,?) ON CONFLICT DO NOTHING',
                             (mapped['record_id'],section,i,dump(entry)))


def readable(mapped):
    p=mapped['profile'];out=[p['contact']['full_name'] or 'Unknown name',
                           'Document: '+mapped['document_id'],'Status: '+mapped['review_status']]
    for section in ORDER:
        if not p[section]:continue
        out.extend(['',section.upper()])
        entries=[p[section]] if section=='contact' else p[section]
        for entry in entries:
            if isinstance(entry,str):out.append(entry);continue
            for key,val in entry.items():
                if key in ['source_text','source_line_ids','source_records','ordinal']:continue
                if val is not None and val!=[] and val!='':
                    out.append(key+': '+(val if isinstance(val,str) else json.dumps(val,ensure_ascii=False)))
            # Retain block content in the text view for details not modeled separately.
            if entry.get('source_text'):out.append('Source block: '+entry['source_text'])
    return '\n'.join(out)+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('--out',type=Path,default=Path('mapped_results'))
    parser.add_argument('--db',type=Path,default=Path('resumes.sqlite'))
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True);args.db.parent.mkdir(parents=True,exist_ok=True)
    paths=[args.input] if args.input.is_file() else sorted(args.input.rglob('*.json'))
    # Parse only full extraction results; folder runs skip quality/batch/structured files.
    paths=[p for p in paths if not p.resolve().is_relative_to(args.out.resolve())]
    conn=sqlite3.connect(args.db);conn.executescript((ROOT/'storage_schema.sql').read_text(encoding='utf-8'))
    summary=[];failed=False
    for path in paths:
        try:
            raw_bytes=path.read_bytes();original=json.loads(raw_bytes.decode('utf-8-sig'))
            if not isinstance(original,dict) or 'structured' not in original or 'source' not in original:
                if args.input.is_file():raise ValueError('Not a full resume extraction result')
                continue
            mapped=map_result(original,digest(raw_bytes));directory=args.out/mapped['record_id'];directory.mkdir(exist_ok=True)
            (directory/'original_resume.json').write_bytes(raw_bytes)
            (directory/'profile.json').write_text(json.dumps(mapped,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            (directory/'profile.txt').write_text(readable(mapped),encoding='utf-8')
            md=path.with_suffix('.md')
            if md.exists():(directory/'original_resume.md').write_bytes(md.read_bytes())
            save_database(conn,mapped,original)
            summary.append({'input':str(path),'source':mapped['source']['filename'],'name':mapped['profile']['contact']['full_name'],
                            'record_id':mapped['record_id'],'status':mapped['review_status'],'changes':len(mapped['mapping_changes'])})
        except (ValueError,KeyError,TypeError,OSError,sqlite3.Error) as exc:
            summary.append({'input':str(path),'error':str(exc)});failed=True
    conn.close();(args.out/'mapping_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 1 if failed or not summary else 0


if __name__=='__main__':raise SystemExit(main())
