"""Evidence-first resume understanding, layered on the existing layout engine.

Saved structured data is used only for comparison. Rebuild from immutable raw
lines, then perform context-aware NER, grouping, mapping and validation offline.
"""
from __future__ import annotations
from collections import defaultdict
from copy import deepcopy
from dataclasses import fields as dataclass_fields
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from .config import load_config
from .entities import recognize, ROLE, ORG, DETAIL, ACTION
from .models import Line, Run, Document
from .text_rules import split_top_level

VERSION='1.0.0'
ORDER=['personal_details','summary','education','work_experience','internships',
       'projects','skills','certifications','training','awards','publications','languages','other_sections']


def value(x):
    return x.get('value') if isinstance(x,dict) and 'value' in x else x


def settings(config=None):
    cfg=deepcopy(config or load_config());cfg['understanding']=True
    cfg['sections']['experience'] += ['internships','internship','employment','work history','research experience']
    cfg['sections']['training']=['training','professional development','courses','workshops','courses & training']
    cfg['sections']['education'] += ['educational qualifications','academic background']
    return cfg


def refine_lines(lines,cfg):
    """Recover project boundaries in plain text using contextual anchors."""
    from .sections import canonical_heading
    from .fields import date_pattern
    date=re.compile(date_pattern(cfg),re.I);context='preamble'
    for i,line in enumerate(lines):
        canonical,_=canonical_heading(line.text,cfg)
        if line.tag=='H1':context=canonical or 'custom';continue
        if context!='projects' or line.tag in ('BULLET','H2'):continue
        text=line.text.strip();next_line=lines[i+1] if i+1<len(lines) else None
        if (text and text[0].isupper() and len(text.split())<=14 and not ACTION.match(text)
            and not re.match(r'^(?:Tech|Technologies|Technology Stack)\s*:',text,re.I)
            and not date.fullmatch(text) and next_line
            and (date.fullmatch(next_line.text.strip()) or next_line.tag=='BULLET'
                 or re.match(r'^(?:Tech|Technologies|Technology Stack)\s*:',next_line.text,re.I))):
            line.tag='H2';line.heading_confidence=0.7


def refine_fields(raw,lines,sections,fields,cfg):
    """Use NER context to disambiguate title/employer and restrict contact URIs."""
    ents=recognize(raw,lines,sections,cfg)
    contact_ids={e['source_line_id'] for e in ents if e['section'] in ('preamble','contact')}
    fields['urls'][:]=[f for f in fields['urls'] if set(f['source_line_ids'])<=contact_ids]
    for job in fields['experience']:
        title=value(job['title']) or '';company=value(job['company']) or ''
        relevant=[e for e in ents if e['source_line_id'] in job['source_line_ids']]
        org_ids={e['source_line_id'] for e in relevant if e['label']=='ORG'}
        role_ids={e['source_line_id'] for e in relevant if e['label']=='JOB_TITLE'}
        if (company and not ROLE.search(title) and ROLE.search(company)
            and (ORG.search(title) or set(job['title']['source_line_ids'])&org_ids)
            and set(job['company']['source_line_ids'])&role_ids):
            job['title'],job['company']=job['company'],job['title']


def refine_structure(s,lines,sections,cfg):
    """Credential names stop at explicit training-detail cues, not at commas."""
    rebuilt=[]
    for item in s['certifications']:
        members=[l for l in lines if set(l.source_ids)&set(item['source_line_ids'])]
        # Two undated plain-text credential headings are separate records even
        # without bold styling. Do not split explanatory/training prose.
        def credential_header(l):
            return (len(l.text.split())<=14 and not DETAIL.match(l.text)
                    and not re.match(r'^(?:This|The|Course|Completed|Earned|Trained|Covered|Active|Status|Expires|Issued)\b|^License\s*(?:#|ID\b|No\b)',l.text,re.I)
                    and bool(re.search(r'\b(?:Certified|Certificate|Certification|Chartered|License)\b',l.text,re.I)))
        starts=[i for i,l in enumerate(members) if credential_header(l)]
        if len(starts)>1 and starts[0]==0:
            for start,end in zip(starts,starts[1:]+[len(members)]):
                block=members[start:end];ids=list(dict.fromkeys(sid for l in block for sid in l.source_ids))
                rebuilt.append({'name':{'value':re.sub(r'^[•–*-]\s*','',block[0].text),
                                         'source_line_ids':block[0].source_ids,'confidence':0.8},
                                'details':' '.join(l.text for l in block[1:]),
                                'text':'\n'.join(l.text for l in block),'source_line_ids':ids})
        else:rebuilt.append(item)
    s['certifications']=rebuilt
    for item in s['certifications']:
        text=value(item['name']) or '';m=DETAIL.search(text)
        if m and m.start()>0:
            item['name']['value']=text[:m.start()].strip()
            item['details']=' '.join(filter(None,[text[m.start():].strip(),item['details']]))


def decode_lines(data):
    allowed={f.name for f in dataclass_fields(Line)};run_allowed={f.name for f in dataclass_fields(Run)}
    out=[];seen=set()
    for item in data:
        if not isinstance(item,dict) or not isinstance(item.get('text'),str):raise ValueError('Invalid raw line')
        lid=item.get('id')
        if not lid or lid in seen:raise ValueError('Raw line IDs must be present and unique')
        seen.add(lid);args={k:v for k,v in item.items() if k in allowed}
        args['source_ids']=[lid]  # This line is the immutable provenance unit.
        args['runs']=[Run(**{k:v for k,v in r.items() if k in run_allowed}) for r in item.get('runs',[])]
        out.append(Line(**args))
    return out


def read_artifact(path):
    """Full raw-line JSON > raw/natural text. Never parse generated structured.md.

    TXT/MD fallback has no independent PDF reference or recoverable typography;
    that loss is explicit in source metadata and validation status.
    """
    path=Path(path);blob=path.read_bytes();digest=hashlib.sha256(blob).hexdigest()
    if path.suffix.lower()=='.json':
        d=json.loads(blob.decode('utf-8-sig'))
        if not isinstance(d,dict) or not d.get('raw_lines'):raise ValueError('No immutable raw_lines in JSON')
        src=deepcopy(d.get('source',{}));raw=decode_lines(d['raw_lines'])
        reference=d.get('source_text')
        doc=Document(raw,reference or '',src.get('reference_method','unavailable') if reference else 'unavailable',
                     bool(src.get('ocr')),list(d.get('quality',{}).get('warnings',[])),src.get('pages'),src.get('ocr_pages',[]))
        src.setdefault('filename',path.name);src.setdefault('type','txt');src.setdefault('sha256',digest)
        if not isinstance(src['sha256'],str) or not re.fullmatch(r'[a-fA-F0-9]{64}',src['sha256']):
            src['sha256']=digest
            doc.warnings.append('Invalid source digest: identity uses artifact hash, not verified original document hash')
        src['sha256']=src['sha256'].lower()
        return doc,src,d,digest
    if path.suffix.lower() not in ('.txt','.md'):raise ValueError('Use saved JSON or natural text artifacts')
    if path.stem.lower() in ('structured','profile','understanding'):raise ValueError('Generated structured text is comparison data, not source')
    text=blob.decode('utf-8-sig');lines=[]
    for i,textline in enumerate(text.splitlines()):
        lid=f'l{i:05d}'
        lines.append(Line(lid,textline,source_ids=[lid]))
    doc=Document(lines,'','unavailable',warnings=['Text fallback: layout, embedded links and independent completeness reference unavailable'])
    return doc,{'filename':path.name,'type':'txt','sha256':digest},None,digest


def normalized_date(raw):
    if raw is None:return {'raw':None,'value':None,'precision':None}
    if re.fullmatch(r'Present|Current|Now|Ongoing',raw,re.I):return {'raw':raw,'value':None,'precision':'open'}
    if re.fullmatch(r'(?:19|20)\d{2}',raw):return {'raw':raw,'value':raw,'precision':'year'}
    months={m:i for i,m in enumerate(['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'],1)}
    m=re.fullmatch(r'([A-Za-z]+)\s+((?:19|20)\d{2})',raw.strip())
    if m and m[1][:3].lower() in months:return {'raw':raw,'value':f'{m[2]}-{months[m[1][:3].lower()]:02d}','precision':'month'}
    m=re.fullmatch(r'(0?[1-9]|1[0-2])/((?:19|20)\d{2})',raw.strip())
    if m:return {'raw':raw,'value':f'{m[2]}-{int(m[1]):02d}','precision':'month'}
    return {'raw':raw,'value':None,'precision':None}


def source_refs(raw,ids,text=None):
    refs=[]
    for sid in dict.fromkeys(ids):
        if sid not in raw:continue
        l=raw[sid];start=l.text.find(text) if isinstance(text,str) and text else -1
        refs.append({'line_id':sid,'start':start if start>=0 else 0,
                     'end':start+len(text) if start>=0 else len(l.text),
                     'text':text if start>=0 else l.text,'page':l.page,'bbox':l.bbox,
                     'granularity':'exact_span' if start>=0 else 'supporting_line'})
    return refs


def build_understanding(result,doc,entities,artifact_sha):
    s=result['structured'];raw={l.id:l for l in doc.lines};evidence={};issues=[]
    profile={k:[] for k in ORDER};profile['personal_details']=deepcopy(s['contact'])
    preamble={lid for sec in result['sections'] if sec['canonical'] in ('preamble','contact') for lid in sec['line_ids']}
    headline=next((l for l in result['lines'] if l['id'] in preamble and l['tag']=='SUBTITLE'),None)
    profile['personal_details']['headline']={'value':headline['text'] if headline else None,
                                            'source_line_ids':headline['source_ids'] if headline else [],'confidence':0.7 if headline else 0.0}
    profile['summary']=deepcopy(s['summary']);profile['education']=deepcopy(s['education'])
    profile['projects']=deepcopy(s['projects']);profile['skills']=deepcopy(s['skills'])
    profile['certifications']=deepcopy(s['certifications'])
    for job in s['experience']:
        kind='internships' if re.search(r'\bintern(?:ship)?\b',value(job['title']) or '',re.I) else 'work_experience'
        profile[kind].append(deepcopy(job))
    lineindex={l['id']:l for l in result['lines']}
    for section in s['other_sections']:
        kind=section['canonical'];kind=kind if kind in ('training','awards','publications','languages') else 'other_sections'
        if kind=='other_sections':profile[kind].append(deepcopy(section));continue
        source_ids=set(section['source_line_ids'])
        ls=[l for l in result['lines'] if set(l['source_ids'])&source_ids and l['tag']!='H1']
        blocks=[];current=[]
        for l in ls:
            if current and (l['tag'] in ('H2','BULLET') or kind=='languages'):
                blocks.append(current);current=[]
            current.append(l)
        if current:blocks.append(current)
        for block in blocks:
            ids=list(dict.fromkeys(sid for l in block for sid in l['source_ids']))
            text='\n'.join(l['text'] for l in block)
            entry={'text':text,'source_line_ids':ids,'original_heading':section['original_heading']}
            if kind=='languages':
                for part in split_top_level(re.sub(r'^[•–*-]\s*','',text)):
                    m=re.fullmatch(r'(.+?)\s*(?:[-–—:]\s*|\()(Native|Fluent|Professional|Intermediate|Basic|Beginner|[ABC][12])\)?',part,re.I)
                    profile[kind].append({**entry,'name':m[1].strip() if m else part,
                                          'proficiency':m[2] if m else None})
            else:
                entry['name']=re.sub(r'^[•–*-]\s*','',block[0]['text'])
                entry['details']=' '.join(l['text'] for l in block[1:])
                # Bibliographic text stays verbatim; author/title guessing is not justified.
                if kind=='publications':entry.update(citation=text,authors=None,venue=None,doi=None)
                profile[kind].append(entry)

    # URI ownership is determined by source membership, never by host popularity.
    contact_sections=[x for x in result['sections'] if x['canonical'] in ('preamble','contact')]
    contact_ids={sid for sec in contact_sections for lid in sec['line_ids'] for sid in lineindex[lid]['source_ids']}
    assigned_links=set();unassigned_links=[]
    for e in entities:
        if e['label']!='URL':continue
        key=(e['source_line_id'],e['text'])
        if key in assigned_links:continue
        assigned_links.add(key);owners=[]
        for kind,entries in profile.items():
            if kind in ('personal_details','skills','summary'):continue
            for i,item in enumerate(entries):
                if e['source_line_id'] in item.get('source_line_ids',[]):owners.append((kind,i,item))
        item={'value':e['text'],'source_line_ids':[e['source_line_id']],'entity_id':e['id']}
        if len(owners)==1:owners[0][2].setdefault('links',[]).append(item)
        elif e['source_line_id'] not in contact_ids:
            unassigned_links.append(item)
            issues.append({'code':'ambiguous_link_owner','path':'unassigned_links','reason':'No unique record owner','source_line_ids':[e['source_line_id']]})
    profile['unassigned_links']=unassigned_links

    # Derive normalized dates without adding false precision or synthetic values.
    for kind in ('education','work_experience','internships','projects'):
        for i,item in enumerate(profile[kind]):
            period=value(item.get('dates')) or {}
            item['normalized_dates']={k:normalized_date(period.get(k)) for k in ('start','end')}
            a=item['normalized_dates']['start'];b=item['normalized_dates']['end']
            if a['value'] and b['value'] and a['value'][:4]>b['value'][:4]:
                issues.append({'code':'reversed_dates','path':f'{kind}[{i}].dates','reason':'End year precedes start year','source_line_ids':item['source_line_ids']})
            if kind=='education':
                g=value(item.get('gpa'))
                if g and g.get('scale') and float(g['score'])>float(g['scale']):
                    issues.append({'code':'invalid_gpa','path':f'{kind}[{i}].gpa','reason':'Score exceeds explicit scale','source_line_ids':item['source_line_ids']})
    # Evidence for EVERY data leaf, including unknown blocks and bullet bodies.
    # A supporting-line reference is not falsely advertised as an exact span.
    metadata={'source_line_ids','confidence','schema_version','original_heading','entity_id'}
    def walk(obj,path,ids):
        if isinstance(obj,dict):
            own=obj.get('source_line_ids',ids)
            for key,val in obj.items():
                if key not in metadata:walk(val,path+'.'+key if path else key,own)
        elif isinstance(obj,list):
            for i,val in enumerate(obj):walk(val,f'{path}[{i}]',ids)
        elif obj is not None:
            refs=source_refs(raw,ids,obj)
            evidence[path]={'source_refs':refs,'confidence_kind':'uncalibrated_rule_score'}
            if not refs:issues.append({'code':'missing_evidence','path':path,'reason':'No source reference for non-null value','source_line_ids':ids})
    walk(profile,'',[])
    used={sid for ev in evidence.values() for ref in ev['source_refs'] for sid in [ref['line_id']]}
    headings={sid for l in result['lines'] if l['tag']=='H1' for sid in l['source_ids']}
    unclassified=[{'text':l.text,'source_line_ids':[l.id],'reason':'No mapped field; retained verbatim'}
                  for l in doc.lines if l.id not in used|headings and l.text.strip()]
    # Record membership graph enables inspection of splits/merges without hiding ambiguity.
    records=[]
    for kind in ORDER:
        if kind=='personal_details':continue
        for i,item in enumerate(profile[kind]):
            records.append({'record_id':f'{kind}:{i}','section':kind,'ordinal':i,
                            'source_line_ids':item.get('source_line_ids',[]),
                            'entity_ids':[e['id'] for e in entities if e['source_line_id'] in item.get('source_line_ids',[])]})
    for rec in records:
        if rec['section'] in ('education','work_experience','internships','projects'):
            dates=[e for e in entities if e['id'] in rec['entity_ids'] and e['label']=='DATE_RANGE']
            if len({e['text'] for e in dates})>1:
                issues.append({'code':'possible_false_merge','path':rec['record_id'],'reason':'Multiple distinct date ranges in one record','source_line_ids':rec['source_line_ids']})
    anchor_sections={'DEGREE':{'education'},'PROJECT':{'projects'},'JOB_TITLE':{'work_experience','internships'}}
    for entity in entities:
        if entity['label'] not in anchor_sections:continue
        owners=[r for r in records if r['section'] in anchor_sections[entity['label']] and entity['id'] in r['entity_ids']]
        if not owners:
            issues.append({'code':'unmapped_record_anchor','path':entity['label'],
                           'reason':'Detected record anchor has no owning record; source retained',
                           'source_line_ids':[entity['source_line_id']]})
        elif len(owners)>1:
            issues.append({'code':'possible_false_split','path':entity['label'],
                           'reason':'One anchor belongs to multiple records; inspect membership',
                           'source_line_ids':[entity['source_line_id']]})
    return {'understanding_schema_version':VERSION,'engine':'offline_rule_ner','source':deepcopy(result['source']),
            'artifact_sha256':artifact_sha,'section_order':ORDER,'entry_order':'source',
            'profile':profile,'entities':entities,'records':records,'evidence':evidence,
            'source_sections':deepcopy(result['sections']),'unclassified':unclassified,
            'raw_lines':deepcopy(result['raw_lines']),'raw_text':result['raw_text'],
            'validation':{'issues':issues,'legacy_schema_errors':result['quality']['schema_errors'],
                          'completeness':deepcopy(result['quality']['completeness']),
                          'semantic_accuracy':'not_established_by_schema_validation'},
            'review_status':'needs_review' if issues or result['needs_review'] or unclassified else 'mapped_unverified'}


def understand_artifact(path,config=None):
    """Public Python API: returns (compatible_resume_v3, understanding_v1)."""
    from .pipeline import process_document
    doc,src,comparison,sha=read_artifact(path);cfg=settings(config)
    result=process_document(doc,src,src['filename'],cfg)
    lines=decode_lines(result['lines'])
    # Normalized lines can have IDs like ':b'; restore their raw provenance.
    for line,serialized in zip(lines,result['lines']):line.source_ids=serialized['source_ids']
    entities=recognize(doc.lines,lines,result['sections'],cfg)
    rich=build_understanding(result,doc,entities,sha)
    rich['comparison']={'provided':bool(comparison and comparison.get('structured')),
                        'changed':bool(comparison and comparison.get('structured')!=result['structured']),
                        'ground_truth':False}
    return result,rich
