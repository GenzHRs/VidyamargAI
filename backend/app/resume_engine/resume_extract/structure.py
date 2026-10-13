"""Stable application schema. All records retain text and raw-line evidence."""
import re
from dataclasses import replace
from .fields import date_pattern
from .reading_order import location_like
from .text_rules import split_top_level, split_institution_location

ORDER=['contact','summary','experience','education','projects','skills','certifications','other_sections']
INSTITUTION=re.compile(r'\b(?:university|college|institute|school|polytechnic|IIT|NIT|UT Austin|UC Berkeley Haas|UCLA)\b',re.I)


def ids(lines):
    return list(dict.fromkeys(s for line in lines for s in line.source_ids))


def field(value, lines, score=0.85):
    return {'value':value,'source_line_ids':ids(lines),'confidence':score if value is not None else 0.0}


def clean(text):
    return re.sub(r'^[•–−*-]\s*', '', text.strip()).strip()


def build_structured(lines, sections, fields, config):
    index={l.id:l for l in lines}
    date_re=re.compile(date_pattern(config),re.I)
    degree_re=re.compile(config['patterns']['degree'],re.I)
    gpa_re=re.compile(config['patterns']['gpa'],re.I)
    out={'schema_version':'3.0.0','section_order':ORDER,'entry_order':'source',
         'contact':{'name':fields['name'],'emails':fields['emails'],'phones':fields['phones'],
                    'locations':list(fields['locations']),'links':fields['urls']},
         'summary':[], 'experience':fields['experience'],'education':[], 'projects':[],
         'skills':[], 'certifications':[], 'other_sections':[], 'review':[]}
    def record(block):
        return {'text':'\n'.join(l.text for l in block),'source_line_ids':ids(block)}
    def dates(block, kind="education"):
        matches=[(m,l) for l in block for m in date_re.finditer(l.text)]
        if len(matches)==1:
            m,l=matches[0];return field({'start':m['start'],'end':m['end']},[l],0.95)
        if len(matches)>1:
            out['review'].append({'path':'structured.'+kind,'reason':'Multiple date ranges in one block; dates left null','confidence':0.0})
        return field(None,[])
    def education(block):
        if not block:return
        degrees=[l for l in block if degree_re.search(l.text)]
        schools=[l for l in block if INSTITUTION.search(l.text) and not degree_re.match(clean(l.text))]
        degree_line=degrees[0] if degrees else None
        # Delimiters separate degree and institution; preserve content in record.text.
        parts=re.split(r'\s*(?:[|•]|\s[—–]\s)\s*',clean(degree_line.text),maxsplit=1) if degree_line else []
        degree=date_re.sub('',parts[0]).strip() if parts else None
        inline=next((part for part in parts[1:] if INSTITUTION.search(part)),None)
        institution=clean(schools[0].text) if schools else re.split(r'[|•]',inline,maxsplit=1)[0].strip() if inline else None
        institution_lines=schools[:1] or ([degree_line] if inline else [])
        # PDF table cells can wrap an institution onto several physical lines.
        if schools and schools[0].table:
            first=schools[0]
            institution_lines=[first]
            for l in block[block.index(first)+1:]:
                if (l.table!=first.table or l.row!=first.row or l.cell!=first.cell or
                    degree_re.search(l.text) or date_re.search(l.text) or gpa_re.search(l.text) or
                    re.search(r'\bGraduat(?:ed|ion)\b',l.text,re.I)):break
                institution_lines.append(l)
            institution=' '.join(clean(l.text) for l in institution_lines)
        if institution:
            institution=re.sub(r'\s*\([^()]*(?:19|20)\d{2}[^()]*\)\s*$', '',institution)
            institution=re.sub(r',?\s+(?:19|20)\d{2}\s*$', '',institution).strip()
        institution_location=None
        if institution:
            institution=gpa_re.sub('',institution).strip()
            institution,institution_location=split_institution_location(institution)
        graduation=[]
        graduation_label=any(re.search(r'\bGraduat(?:ed|ion)\b',l.text,re.I) for l in block)
        for l in block:
            if date_re.search(l.text):continue
            context=graduation_label or bool(INSTITUTION.search(l.text))
            if context:
                for m in re.finditer(r'(?:(?:'+config['patterns']['date_month']+r')\s+)?'+config['patterns']['date_year'],l.text,re.I):
                    graduation.append((m.group(),l))
        gpas=[(gpa_re.search(l.text),l) for l in block if gpa_re.search(l.text)]
        locations=[l for l in block if location_like(l.text)]
        entry={**record(block),'degree':field(degree,degrees[:1]),'institution':field(institution,institution_lines),
               'dates':dates(block),'graduation':field(graduation[0][0] if len(graduation)==1 else None,[graduation[0][1]] if len(graduation)==1 else []),'location':field(institution_location or (locations[0].text if locations else None),institution_lines if institution_location else locations[:1]),
               'gpa':field({'score':gpas[0][0][1],'scale':gpas[0][0][2]} if gpas else None,[gpas[0][1]] if gpas else [])}
        if not degrees and re.search(r'\b(?:Certified|Chartered|License|Certification)\b',entry['text'],re.I):
            out['certifications'].append({**record(block),'name':field(clean(block[0].text),[block[0]]),'details':' '.join(clean(l.text) for l in block[1:])})
        else:out['education'].append(entry)
    def cert(items):
        if not items:return
        text=clean(items[0].text)
        candidates=split_top_level(text,',•')
        credential=r'\b(?:Certified|Chartered|License|Certification|Six Sigma)\b'
        parts=candidates if len(candidates)>1 and all(re.search(credential,c,re.I) for c in candidates) else [text]
        for part in parts:
            out['certifications'].append({**record(items),'name':field(part,[items[0]]),
                'details':' '.join(clean(l.text) for l in items[1:])})
    handled={'preamble' ,'contact','summary','experience','education','projects','skills','certifications'}
    for section in sections:
        block=[index[i] for i in section['line_ids'] if i in index and index[i].text.strip()]
        kind=section['canonical']
        if kind in ('preamble','contact'):
            for l in block:
                if '@' in l.text or '|' in l.text:
                    for part in l.text.split('|'):
                        if location_like(part) and not any(x['value']==part.strip() for x in out['contact']['locations']):
                            out['contact']['locations'].append(field(part.strip(),[l]))
        elif kind=='summary':
            if block:out['summary'].append({**record(block),'value':' '.join(clean(l.text) for l in block)})
        elif kind=='education':
            expanded=[]
            for l in block:
                parts=split_top_level(clean(l.text),'•')
                for part in parts:
                    item=replace(l,text=part)
                    if len(parts)>1 and re.search(r'\b(?:Certified|Chartered|License|Certification|Six Sigma .*Belt)\b',part,re.I) and not degree_re.search(part):cert([item])
                    else:expanded.append(item)
            block=expanded
            current=[]
            for l in block:
                if re.match(config['patterns']['table_header'],l.text):continue
                if l.tag=='BULLET' and not l.table and re.search(r'\b(?:Certified|Chartered|License|Certification|Six Sigma .*(?:Belt))\b',l.text,re.I) and not degree_re.search(l.text):
                    education(current);current=[];cert([l]);continue
                has_degree=any(degree_re.search(x.text) for x in current)
                has_school=any(INSTITUTION.search(x.text) and not degree_re.match(clean(x.text)) for x in current)
                new_degree=bool(degree_re.search(l.text))
                new_school=bool(INSTITUTION.search(l.text)) and not new_degree
                table_new=bool(current and l.table and current[-1].table==l.table and l.row!=current[-1].row)
                if current and (table_new or (new_degree and has_degree) or (new_school and has_school and has_degree)):
                    education(current);current=[]
                current.append(l)
            education(current)
        elif kind=='projects':
            current=[]
            def is_project_header(l):
                return (l.tag=='H2' or bool(re.match(r'^\d+[.)]\s+',l.text))) and not re.match(r'^(?:Tech|Technologies|Technology Stack)\s*:',l.text,re.I)
            def project(items):
                if not items:return
                first=items[0];title=is_project_header(first)
                tech_lines=[l for l in items if re.match(r'^(?:Tech|Technologies|Technology Stack)\s*:',l.text,re.I)]
                technologies=[field(t,[l]) for l in tech_lines for t in split_top_level(l.text.partition(':')[2])]
                out['projects'].append({**record(items),
                    'name':field(date_re.sub('',re.sub(r'^\d+[.)]\s+','',clean(first.text))).strip() if title else None,[first] if title else []),
                    'dates':dates(items,'projects'),'technologies':technologies,
                    'description':' '.join(clean(l.text) for l in (items[1:] if title else items)),
                    'bullets':[clean(l.text) for l in items if l.tag=='BULLET']})
            for l in block:
                if current and is_project_header(l):project(current);current=[]
                current.append(l)
            project(current)
        elif kind=='skills':
            table_headers={(l.table,l.cell):l for l in block if l.table and l.row==0 and l.tag=='H2'}
            for l in block:
                header=table_headers.get((l.table,l.cell))
                if l is header:continue
                text=clean(l.text);category,sep,body=text.partition(':')
                out['skills'].append({**record([header,l] if header else [l]),
                    'category':category.strip() if sep else clean(header.text) if header else None,
                    'items':split_top_level(body if sep else text)})
        elif kind in ('certifications','awards_and_certifications'):
            current=[]
            def mixed_cert(items):
                if not items:return
                if kind=='awards_and_certifications':
                    if not re.search(r'\b(?:Certified|Chartered|License|Certification)\b',items[0].text,re.I):
                        out['other_sections'].append({'canonical':'awards','original_heading':section['original_heading'],**record(items)})
                        return
                    # Explicit issuer separated from certification title; prose commas are not lists.
                    text=' '.join(clean(l.text) for l in items)
                    parts=re.split(r'\s+[–—]\s+',text,maxsplit=1)
                    out['certifications'].append({**record(items),'name':field(parts[0],[items[0]]),'details':parts[1] if len(parts)>1 else ''})
                else:cert(items)
            for l in block:
                if current and l.tag in ('BULLET','H2'):mixed_cert(current);current=[]
                current.append(l)
            mixed_cert(current)
        elif kind not in handled:
            out['other_sections'].append({'canonical':kind,'original_heading':section['original_heading'],**record(block)})
    # Every original section remains available, including incomplete/unparsed blocks.
    out['source_sections']=sections
    # Schema checks cannot establish semantic accuracy; missing evidence is reviewable.
    for kind,key in [('education','degree'),('education','institution'),('projects','name')]:
        for i,item in enumerate(out[kind]):
            if item[key]['value'] is None:
                out['review'].append({'path':f'structured.{kind}[{i}].{key}','reason':'No unambiguous label found; source text retained','confidence':0.0})
    return out


def structured_markdown(data):
    def val(x):
        v=x.get('value') if x else None
        if isinstance(v,dict):return ' – '.join(str(z) for z in v.values() if z is not None)
        return str(v) if v is not None else ''
    name=val(data['contact']['name']) or 'Resume'
    out=['# '+name,'## Contact']
    for key in ('emails','phones','locations','links'):
        out.extend('- '+val(x) for x in data['contact'][key])
    for section in ORDER[1:]:
        entries=data[section]
        if not entries:continue
        out.append('## '+section.replace('_',' ').title())
        for entry in entries:
            if section=='summary':out.append(entry['value'])
            elif section=='skills':out.append(('**'+entry['category']+':** ' if entry['category'] else '')+', '.join(entry['items']))
            elif section=='experience':
                out.append('### '+(val(entry['title']) or 'Unresolved role'))
                out.append(' | '.join(filter(None,[val(entry['company']),val(entry['location']),val(entry['dates'])])))
                out.extend('- '+clean(b) for b in entry['bullets'])
                if not entry['bullets']:out.append(entry['text'])
            elif section=='education':
                out.append('### '+(val(entry['degree']) or 'Unresolved qualification'))
                out.append(' | '.join(filter(None,[val(entry['institution']),val(entry['location']),val(entry['dates']),val(entry['graduation'])])))
                if entry['gpa']['value']:
                    g=entry['gpa']['value'];out.append('GPA: '+g['score']+('/'+g['scale'] if g['scale'] else ''))
            elif section=='projects':
                out.append('### '+(val(entry['name']) or 'Unresolved project'))
                out.append(val(entry['dates']))
                if entry['technologies']:out.append('Technologies: '+', '.join(val(x) for x in entry['technologies']))
                out.append(entry['description'])
            elif section=='certifications':out.extend([val(entry['name']),entry['details']])
            else:out.extend(['### '+str(entry['original_heading'] or entry['canonical']),entry['text']])
    return '\n\n'.join(x for x in out if x)+'\n'
