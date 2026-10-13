"""Offline, explainable NER. Offsets always address immutable raw-line text.

This is a rule recognizer, not a trained or probabilistically calibrated model.
Context restricts ambiguous entities; unknown text is retained by the engine.
"""
from __future__ import annotations
import re
from .fields import date_pattern
from .structure import INSTITUTION

ROLE = re.compile(r'\b(?:engineer|developer|architect|analyst|manager|director|officer|'
                  r'intern|internship|scientist|researcher|professor|lecturer|designer|'
                  r'consultant|accountant|auditor|president|associate|specialist|lead|head)\b', re.I)
ORG = re.compile(r'\b(?:Inc\.?|LLC|Ltd\.?|Limited|Corp\.?|Corporation|LLP|'
                 r'Company|Solutions|Technologies|Systems|Labs|Group|University|College|Institute)\b', re.I)
ACTION = re.compile(r'^(?:built|developed|led|managed|improved|implemented|designed|'
                    r'automated|evaluated|trained|achieved|created|delivered|reduced|increased)\b', re.I)
DETAIL = re.compile(r'\b(?:Trained in|Training (?:in|on)|Coursework:|Covered:|Skills acquired:)\s*', re.I)


def recognize(raw_lines, lines, sections, config):
    """Return typed literal spans and separately identified hyperlink targets.

    Candidate organization/role spans are limited to headers, not achievement
    prose. Skills use longest-match gazetteer rules; explicit skill-list items
    remain available even if absent from that gazetteer.
    """
    contexts = {}
    for section in sections:
        for lid in section['line_ids']:
            contexts[lid] = section['canonical']
    raw_context = {}
    tags = {}
    for line in lines:
        for sid in line.source_ids:
            raw_context[sid] = contexts.get(line.id, 'unknown')
            tags[sid] = line.tag
    entities = []
    seen = set()
    def add(line, label, start, end, rule, normalized=None, target=None, run_index=None):
        key = (line.id, label, start, end, target)
        if key in seen or start == end and target is None:
            return
        seen.add(key)
        text = target if target is not None else line.text[start:end]
        entities.append({'id':f'e{len(entities):05d}', 'label':label, 'text':text,
                         'normalized':normalized if normalized is not None else text,
                         'source_line_id':line.id, 'start':start, 'end':end,
                         'source_kind':'hyperlink' if target is not None else 'text',
                         'run_index':run_index, 'page':line.page, 'bbox':line.bbox,
                         'section':raw_context.get(line.id,'unknown'), 'rule':rule,
                         'confidence_kind':'uncalibrated_rule_score',
                         'confidence':0.7 if label in ('PERSON','ORG','JOB_TITLE','PROJECT') else 0.9})
    p = config['patterns']
    for line in raw_lines:
        text = line.text; context = raw_context.get(line.id,'unknown'); tag = tags.get(line.id)
        for label, pattern in [('EMAIL',p['email']),('PHONE',p['phone']),('DATE_RANGE',date_pattern(config)),
                               ('GPA',p['gpa'])]:
            for m in re.finditer(pattern,text,re.I):
                if label == 'PHONE' and not 10 <= len(re.sub(r'\D','',m.group())) <= 15:continue
                add(line,label,m.start(),m.end(),'regex:'+label.lower())
        for m in re.finditer(p['url'],text,re.I):
            if m.start() and text[m.start()-1]=='@':continue
            val=m.group().rstrip('.,;)')
            if not val.startswith(('http://','https://','www.')) and '/' not in val and context not in ('preamble','contact'):continue
            add(line,'URL',m.start(),m.start()+len(val),'literal_url')
        for ri,run in enumerate(line.runs):
            if run.hyperlink:
                label='EMAIL' if run.hyperlink.startswith('mailto:') else 'URL'
                add(line,label,None,None,'embedded_hyperlink',target=run.hyperlink,run_index=ri)
        if tag=='TITLE' and context in ('preamble','contact'):
            add(line,'PERSON',0,len(text),'preamble_title')
        if context=='education':
            for m in re.finditer(p['degree'],text,re.I):add(line,'DEGREE',m.start(),m.end(),'education_degree')
            if INSTITUTION.search(text) and not re.match(p['degree'],text,re.I):
                end=re.search(r'\s+[|•]\s+|\s*\((?:19|20)\d{2}',text)
                add(line,'INSTITUTION',0,end.start() if end else len(text),'education_institution')
        if context=='experience' and tag!='BULLET' and not ACTION.match(text):
            for m in re.finditer(r'[^|\n]+',text):
                part=m.group().strip(); start=m.start()+len(m.group())-len(m.group().lstrip())
                dm=re.search(date_pattern(config),part,re.I)
                if dm:part=part[:dm.start()].rstrip(' –—-')
                if not part:continue
                if ROLE.search(part):add(line,'JOB_TITLE',start,start+len(part),'role_header')
                elif ORG.search(part):add(line,'ORG',start,start+len(part),'organization_header')
        if context=='projects' and tag=='H2' and not re.match(r'^(?:Tech|Technologies)\s*:',text,re.I):
            dm=re.search(date_pattern(config),text,re.I)
            add(line,'PROJECT',0,dm.start() if dm else len(text),'project_header')
        if context in ('certifications','awards_and_certifications') and not DETAIL.match(text):
            if tag in ('H2','BULLET') or re.search(r'\b(?:Certification|Certified|Certificate)\b',text,re.I):
                dm=DETAIL.search(text)
                add(line,'CERTIFICATION',0,dm.start() if dm else len(text),'credential_context')
        matches=[]
        for skill in config['skills_gazetteer']:
            flags=0 if skill in config['fields']['case_sensitive_skills'] else re.I
            for alias in [skill]+[a for a,v in config['skill_aliases'].items() if v==skill]:
                for m in re.finditer(p['skill_left_boundary']+re.escape(alias)+p['skill_right_boundary'],text,flags):
                    matches.append((m.start(),m.end(),skill))
        occupied=[]
        for start,end,skill in sorted(matches,key=lambda x:(-(x[1]-x[0]),x[0])):
            if any(start<b and end>a for a,b in occupied):continue
            occupied.append((start,end));add(line,'SKILL',start,end,'gazetteer_longest_match',skill)
    return entities
