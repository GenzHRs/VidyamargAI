"""Visual and lexical line tagging; no dependence on Word heading styles."""
from __future__ import annotations
from dataclasses import replace
from statistics import median
from typing import Any
import re
from .models import Line
from .sections import canonical_heading


def classify(lines: list[Line], config: dict[str, Any]) -> list[Line]:
    """Tag TITLE/SUBTITLE/H1/H2/BULLET/TEXT and split explicit inline sections."""
    c=config['classify']; expanded=[]
    for line in lines:
        label,sep,body=line.text.partition(':')
        canonical,_=canonical_heading(label,config)
        if sep and body.strip() and canonical and len(label.split())<=c['heading_max_words']:
            expanded.append(replace(line,text=label+':',id=line.id+':h',tag='H1'))
            expanded.append(replace(line,text=body.lstrip(),id=line.id+':b',tag='TEXT',runs=[]))
        else: expanded.append(replace(line))
    sizes=[r.size for line in lines for r in line.runs if r.size and r.text.strip()]
    base=median(sizes) if sizes else 0
    def plausible_name(line: Line) -> bool:
        text=line.text.strip()
        return c['title_min_words']<=len(text.split())<=c['name_max_words'] and not re.search(r'[@/|•:\d]',text) and not canonical_heading(text,config)[0]
    title_candidates=[(line.size,i) for i,line in enumerate(expanded) if i<c['title_position_limit'] and base and line.size>=base*c['title_size_ratio'] and plausible_name(line)]
    title_index=max(title_candidates,key=lambda x:(x[0],-x[1]))[1] if title_candidates else None
    if title_index is None:
        # First typographic heading-like candidate is advisory, never certainty.
        title_index=next((i for i,line in enumerate(expanded[:c['title_position_limit']]) if plausible_name(line) and (line.bold or line.text.isupper())),None)
        if title_index is None:title_index=next((i for i,line in enumerate(expanded[:c['title_position_limit']]) if plausible_name(line)),None)
    for i,line in enumerate(expanded):
        text=line.text.strip();words=len(text.split());canonical,confidence=canonical_heading(text,config)
        colored=any(r.color is not None and r.color not in c['neutral_colors'] for r in line.runs)
        short=words<=c['heading_max_words'] and len(text)<=c['heading_max_chars']
        if i==title_index:
            line.tag='TITLE';line.heading_confidence=c['title_confidence'] if title_candidates else c['name_fallback_confidence']
        elif canonical and short:
            line.tag='H1';line.heading_confidence=confidence
        elif title_index is not None and i==title_index+1:
            if words<=c['subtitle_max_words'] and not re.search(r'@|\b\d{3}\b|linkedin\.',text):line.tag='SUBTITLE'
            else:line.tag='TEXT'
        elif line.bullet or text.startswith(('•','- ','* ')):
            line.tag='BULLET'
        elif line.bold and re.search(config['patterns']['date_year']+r'\s*[–—-]',text):
            line.tag='H2'
        elif re.match(r'^(?:Tech|Technologies|Technology Stack)\s*:',text,re.I):
            line.tag='TEXT'
        elif short and line.bold and (re.search(r'\s[|—]\s',text) or (i+1<len(expanded) and re.search(config['patterns']['date_year']+r'\s*[–—-]', expanded[i+1].text)) or (line.table is not None and line.row==0)):
            line.tag='H2'
        elif short and text and not re.search(r'[:\d]',text) and (text.isupper() or ((line.bold or colored) and base and line.size>=base*c['custom_heading_size_ratio'])):
            line.tag='H1';line.heading_confidence=c['custom_confidence']
        elif short and line.bold:
            line.tag='H2'
        else:line.tag='TEXT'
    return expanded
