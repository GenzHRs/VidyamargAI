"""Canonical database keys with original headings and custom sections preserved."""
from __future__ import annotations
import re
from typing import Any
from rapidfuzz import fuzz
from .models import Line


def heading_key(text: str) -> str:
    """Case/whitespace equivalence only; do not erase meaningful heading words."""
    return re.sub(r'\s+',' ',text.strip().rstrip(':')).casefold()


def canonical_heading(text: str, config: dict[str, Any]) -> tuple[str | None, float]:
    """Exact synonyms first, then deterministic full-string fuzzy score >=90."""
    key=heading_key(text)
    if key.startswith(('•','- ','* ')):return None,config['classify']['custom_confidence']
    candidates=[]
    for canonical,aliases in config['sections'].items():
        for alias in aliases:
            score=fuzz.ratio(key,heading_key(alias))
            candidates.append((score,canonical))
            if score==100:return canonical,config['classify']['known_confidence']
    score,canonical=max(candidates,key=lambda x:(x[0],x[1]))
    if score>=config['classify']['fuzzy_threshold']:return canonical,score/100
    return None,config['classify']['custom_confidence']


def build_sections(lines: list[Line], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Partition visible content once. Original heading and every line stay linked."""
    result=[]; current=None
    for line in lines:
        if line.duplicate_of:continue
        if line.tag=='H1':
            canonical,confidence=canonical_heading(line.text,config)
            current={'id':f's{len(result):03d}','canonical':canonical or 'custom',
                     'original_heading':line.text,'heading_line_id':line.id,'confidence':confidence,
                     'line_ids':[],'text':''}
            result.append(current)
        else:
            if current is None or line.tag=='TITLE':
                current={'id':f's{len(result):03d}','canonical':'preamble','original_heading':None,
                         'heading_line_id':None,'confidence':1.0,'line_ids':[],'text':''}
                result.append(current)
            current['line_ids'].append(line.id)
            current['text']+=('\n' if current['text'] else '')+line.text
    return result
