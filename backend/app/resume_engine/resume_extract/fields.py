"""Offline field rules with evidence, confidence and conservative ambiguity."""
from __future__ import annotations
import re
from typing import Any
import phonenumbers
from email_validator import validate_email, EmailNotValidError
from .models import Line


def date_pattern(config: dict[str, Any]) -> str:
    """Month-name, numeric month/year, year-only and open ended date intervals."""
    p=config['patterns'];year=p['date_year']
    date=rf"(?:(?:{p['date_month']})\s+{year}|(?:0?[1-9]|1[0-2])/{year}|{year})"
    return rf"(?P<start>{date})\s*[–—-]\s*(?P<end>{date}|{p['date_current']})"


def extract_fields(lines: list[Line], sections: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    """Extract field candidates; never infer names/companies without evidence."""
    p=config['patterns'];c=config['fields'];scores=c['confidence']
    fields:dict[str,Any]={'name':None,'emails':[],'phones':[],'urls':[],'locations':[],'date_ranges':[],
                          'degrees':[],'gpas':[],'skills':[],'experience':[]}
    visible=[l for l in lines if not l.duplicate_of];index={l.id:l for l in visible}
    section_by_line={lid:s['canonical'] for s in sections for lid in s['line_ids']}
    def evidence(value: Any, line: Line, confidence: float, **extra: Any) -> dict[str, Any]:
        return {'value':value,'confidence':confidence,'source_line_ids':list(line.source_ids),**extra}
    def add(key:str,value:Any,line:Line,confidence:float,**extra:Any) -> None:
        if not any(x['value']==value for x in fields[key]):fields[key].append(evidence(value,line,confidence,**extra))
    title=next((l for l in visible if l.tag=='TITLE'),None)
    if title:fields['name']=evidence(title.text.strip(),title,title.heading_confidence or config['classify']['name_fallback_confidence'])
    date_re=re.compile(date_pattern(config),re.I)
    for i,line in enumerate(visible):
        text=line.text
        # Repair only whitespace immediately around @; retain the source spelling.
        email_text=re.sub(r'(?<=[A-Za-z0-9._%+\-])\s*@\s*(?=[A-Za-z0-9])', '@', text)
        for match in re.finditer(p['email'],email_text):
            value=match.group()
            try:validate_email(value,check_deliverability=False);score=scores['exact']
            except EmailNotValidError:score=scores['invalid_phone']
            add('emails',value,line,score if email_text==text else 0.85, normalization='none' if email_text==text else 'whitespace_around_at', raw=line.text)
        for match in re.finditer(p['phone'],text):
            value=match.group();digits=re.sub(r'\D','',value)
            if not c['phone_min_digits']<=len(digits)<=c['phone_max_digits']:continue
            try:
                phone=phonenumbers.parse(value,c['default_phone_region']);valid=phonenumbers.is_valid_number(phone)
                possible=phonenumbers.is_possible_number(phone)
                canonical=phonenumbers.format_number(phone,phonenumbers.PhoneNumberFormat.E164)
            except phonenumbers.NumberParseException:valid=possible=False;canonical=None
            add('phones',value,line,scores['valid_phone'] if valid else scores['possible_phone'] if possible else scores['invalid_phone'],normalized=canonical,valid=valid)
        url_text=text+' '+ ' '.join(r.hyperlink for r in line.runs if r.hyperlink)
        for match in re.finditer(p['url'],url_text,re.I):
            value=match.group().rstrip('.,;)')
            if not value.lower().startswith(('http://','https://','www.')) and section_by_line.get(line.id) not in ('contact','preamble'):continue
            if any(value in x['value'] for x in fields['emails']):continue
            if not value.lower().startswith(('http://','https://','www.')):
                host=value.split('/')[0]
                if host.count('.')<2 and host.rsplit('.',1)[-1].lower() not in ('com','org','net','io','dev','me','ai','edu','co') and not re.search(r'\b(?:portfolio|website|web)\s*:',text,re.I):continue
            add('urls',value,line,scores['exact'],kind='linkedin' if 'linkedin.com' in value.lower() else 'github' if 'github.com' in value.lower() else 'website')
        # Contact location only: do not turn past employer locations into home addresses.
        contact=(section_by_line.get(line.id) in ('contact','preamble') or (i<c['contact_scan_lines'] and ('@' in text or 'Location:' in text)))
        if contact and line.tag not in ('TITLE','SUBTITLE'):
            for match in re.finditer(p['location'],text):
                value=match.group(1).strip()
                if len(value)<=c['location_max_chars']:add('locations',value,line,scores['location'])
        if section_by_line.get(line.id) not in c['excluded_date_sections']:
            for match in date_re.finditer(text):add('date_ranges',{'start':match['start'],'end':match['end']},line,scores['exact'],raw=match.group())
        if section_by_line.get(line.id)=='education':
            for match in re.finditer(p['degree'],text,re.I):add('degrees',match.group().strip(),line,scores['degree'])
        for match in re.finditer(p['gpa'],text,re.I):add('gpas',{'score':match.group(1),'scale':match.group(2)},line,scores['exact'])
        # Longest phrase wins within each line (Tailwind CSS does not add CSS).
        matches=[]
        for skill in config['skills_gazetteer']:
            aliases=[skill]+[alias for alias,target in config['skill_aliases'].items() if target==skill]
            flags=0 if skill in c['case_sensitive_skills'] else re.I
            for alias in aliases:
                for match in re.finditer(p['skill_left_boundary']+re.escape(alias)+p['skill_right_boundary'],text,flags):
                    matches.append((match.start(),match.end(),skill,alias))
        occupied=[]
        for start,end,skill,alias in sorted(matches,key=lambda m:(-(m[1]-m[0]),m[0],m[2])):
            if any(start<b and end>a for a,b in occupied):continue
            occupied.append((start,end));add('skills',skill,line,scores['skill'],matched_alias=alias)

    def job(block:list[Line]) -> dict[str,Any] | None:
        """Group by dates plus header or one real table row; retain unparsed text."""
        joined='\n'.join(l.text for l in block);match=date_re.search(joined)
        content=[l for l in block if not re.match(p['table_header'],l.text)]
        if not content:return None
        headers=[];bullets=[]
        from .reading_order import location_like
        for line in content:
            if line.tag=='BULLET' or line.text.lstrip().startswith('•'):bullets.append(line.text)
            elif not bullets:
                clean=re.sub(r'\(\s*\)', '', date_re.sub('',line.text)).strip(' |–—')
                corporate_location=re.search(r'^(.*?\b(?:Inc\.?|LLC|Ltd\.?|Corp\.?|LLP))\s+([^,]+,\s*[^,]+)$',clean,re.I)
                if corporate_location:clean=corporate_location[1]
                if clean and not location_like(clean) and not re.match(r'^(?:Developed|Built|Led|Managed|Improved|Implemented|Designed|Automated|Evaluated)\b',clean) and not re.fullmatch(r'\(?[A-Za-z .-]+, [A-Z]{2}\)?',clean):headers.append((clean,line))
        title_value=company_value=None;score=scores['experience_ambiguous'];ev=content[0]
        if headers:
            first,ev=headers[0];parts=re.split(p['experience_separator'],first,maxsplit=1)
            title_value=parts[0].strip()
            if len(parts)==2:company_value=parts[1].strip();score=scores['experience']
            elif len(headers)>1:company_value=headers[1][0];score=scores['experience']
        location_value=None
        if company_value:
            location_match=re.search(r'\(([^()]+,\s*[A-Z]{2})\)\s*$',company_value)
            if location_match:
                location_value=location_match.group(1);company_value=company_value[:location_match.start()].strip()
        if location_value is None:
            corporate_location=next((re.search(r'\b(?:Inc\.?|LLC|Ltd\.?|Corp\.?|LLP)\s+([^,]+,\s*[^,]+)$',l.text,re.I) for l in content if re.search(r'\b(?:Inc\.?|LLC|Ltd\.?|Corp\.?|LLP)\s+([^,]+,\s*[^,]+)$',l.text,re.I)),None)
            if corporate_location:location_value=corporate_location[1].strip()
        if location_value is None:
            location_value=next((l.text.strip() for l in content if location_like(l.text)),None)
        if location_value is None:
            location_match=re.search(p['location'],joined)
            if location_match:location_value=location_match.group(1).strip()
        if title_value is None:return None
        all_dates=list(date_re.finditer(joined))
        ambiguous_dates=len(all_dates)>1
        date_value=None if ambiguous_dates or not match else {'start':match['start'],'end':match['end']}
        return {'title':evidence(title_value,ev,score),'company':evidence(company_value,headers[1][1] if len(headers)>1 and company_value else ev,score),'location':evidence(location_value,next((l for l in content if location_value and location_value in l.text),ev),scores['location'] if location_value else scores['experience_ambiguous']),
                'dates':evidence(date_value,next((l for l in content if date_re.search(l.text)),ev),scores['experience_ambiguous'] if ambiguous_dates or not match else scores['exact']),
                'bullets':bullets,'text':joined,'confidence':score,'source_line_ids':[sid for l in block for sid in l.source_ids]}
    for section in sections:
        if section['canonical']!='experience':continue
        slines=[index[lid] for lid in section['line_ids'] if lid in index]
        # A date|title|duties grid has multiple physical cells in each row.
        rows={}
        for l in slines:
            if l.table is not None:rows.setdefault((l.table,l.row),[]).append(l)
        consumed=set()
        for row in rows.values():
            if len({l.cell for l in row})>1 and date_re.search('\n'.join(l.text for l in row)):
                parsed=job(row)
                if parsed:fields['experience'].append(parsed);consumed.update(l.id for l in row)
        rest=[l for l in slines if l.id not in consumed];blocks=[];current=[]
        for i,l in enumerate(rest):
            next_date=i+1<len(rest) and bool(date_re.search(rest[i+1].text))
            from .reading_order import location_like
            header=(l.tag=='H2' or next_date) and not location_like(l.text) and l.tag!='BULLET' and (not date_re.search(l.text) or bool(date_re.sub('',l.text).strip()))
            # Start only when current block already has a date, preventing
            # academic title and its following company line from splitting.
            if header and current and date_re.search('\n'.join(x.text for x in current)) and any(x.tag=='BULLET' for x in current):
                blocks.append(current);current=[]
            current.append(l)
        if current:blocks.append(current)
        for block in blocks:
            parsed=job(block)
            if parsed:fields['experience'].append(parsed)
    return fields
