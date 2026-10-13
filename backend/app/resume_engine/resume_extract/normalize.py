"""Non-destructive normalized view with provenance and exact-repeat annotations."""
from __future__ import annotations
from dataclasses import replace
from typing import Any
import re
import unicodedata
from .models import Line


def normalize_text(text: str, config: dict[str, Any]) -> str:
    """Unicode compatibility normalization and explicit bullet substitutions."""
    text=unicodedata.normalize('NFKC',text)
    text=re.sub(r'\(cid:\d+\)','•',text)
    return text.translate(str.maketrans({c:'•' for c in config['normalize']['bullet_chars']}))


def normalize(lines: list[Line], config: dict[str, Any]) -> list[Line]:
    """Join only tight, same-flow text lines; keep raw lines untouched."""
    result=[]; seen={};cfg=config['normalize']
    aliases={s.casefold().strip(':') for values in config['sections'].values() for s in values}
    for original in lines:
        text=normalize_text(original.text,config)
        if config.get('understanding'):
            # Only the normalized view changes; raw text and offsets are immutable.
            text=re.sub(r'(?<=[\w%)\]])\s+([,.;:!?])(?=\s|$)',r'\1',text)
        line=replace(original,text=text,source_ids=list(original.source_ids),bullet=original.bullet or bool(re.match(r'^[•–−*-]\s+',text)))
        margin=original.part in ('header','footer') or '/header' in original.part or '/footer' in original.part
        if margin:
            key=(original.part if original.part in ('header','footer') else re.sub(r'\d+','',original.part), original.text)
            if key in seen: line.duplicate_of=seen[key]
            else: seen[key]=line.id
        if result:
            prev=result[-1]
            same=(prev.flow==line.flow and prev.page==line.page and not line.duplicate_of and not prev.duplicate_of)
            tight=(prev.bbox is not None and line.bbox is not None and line.bbox[1]-prev.bbox[3] <= max(prev.size,line.size)*cfg['tight_gap_size_ratio'] and line.bbox[1]>=prev.bbox[1])
            heading=text.strip().rstrip(':').casefold() in aliases or prev.text.strip().rstrip(':').casefold() in aliases
            contact=('@' in prev.text or '@' in text or re.search(r'https?://|linkedin\.com|github\.com',prev.text+' '+text))
            date_wrap=bool(re.search(r'\d{4}\s*[–—-]\s*$',prev.text) and re.match(r'^(?:Present|Current|\d{4})\b',text,re.I))
            hyphen_wrap=prev.text.endswith('-') and bool(re.match(r'^[a-z]',text)) and tight
            prose=(cfg['join_wrapped_prose'] and tight and len(prev.text.split())>=cfg['prose_min_words'] and not heading and not contact and not line.bold and abs(prev.size-line.size)<=cfg['font_size_tolerance'] and bool(re.match(r'^(?:[a-z]|\()',text)))
            # A wrapped bullet may begin with a percentage, acronym or proper noun.
            bold_continuation=(config.get('understanding') and line.bold
                               and bool(re.match(r'^[a-z]',text))
                               and not re.search(r'[.!?]\s*$',prev.text)
                               and len(text.split())<=12)
            bullet_wrap=(prev.bullet and tight and not line.bullet and (not line.bold or bold_continuation) and not heading
                         and not contact and abs(prev.size-line.size)<=cfg['font_size_tolerance']
                         and line.bbox[0]>=prev.bbox[0]-1
                         and not re.search(r'(?<!\d)(?:19|20)\d{2}\s*[–—-]',text))
            if same and (date_wrap or hyphen_wrap or prose or bullet_wrap):
                prev.text=prev.text[:-1]+text if hyphen_wrap else prev.text+' '+text
                prev.source_ids+=line.source_ids
                prev.runs=prev.runs+line.runs
                if prev.bbox and line.bbox:prev.bbox=(min(prev.bbox[0],line.bbox[0]),prev.bbox[1],max(prev.bbox[2],line.bbox[2]),line.bbox[3])
                continue
        result.append(line)
    return result
