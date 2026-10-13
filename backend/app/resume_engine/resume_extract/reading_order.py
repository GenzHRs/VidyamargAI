"""Conservative PDF satellite-column repair; original lines remain immutable."""
from collections import defaultdict
from dataclasses import replace
import re
from .fields import date_pattern

BULLETS = '•●▪◦‣∙·\uf0b7\uf075\uf06c'


def location_like(text):
    """Only isolated city/region-like strings, never an arbitrary prose sentence."""
    if re.search(r'\b(?:Inc|LLC|Ltd|Corp|Company|LLP)\.?$',text.strip(),re.I):return False
    return bool(re.fullmatch(r'[A-Z][A-Za-z .\-]+,\s*[A-Z][A-Za-z .\-]+(?:,?\s*\d{5,6})?', text.strip())) and len(text.split()) <= 8


def repair_order(lines, config):
    groups = defaultdict(list)
    for line in lines:
        if line.bbox and line.page is not None and line.table is None:
            groups[(line.page, line.flow)].append(line)
    dates = re.compile(date_pattern(config), re.I)
    moved = {}; after = defaultdict(list); notes = []
    for (page, flow), group in groups.items():
        content = [l for l in group if l.text.strip()]
        # A real sidebar has headings/skills/prose and is deliberately left alone.
        if not content or not all(dates.fullmatch(l.text.strip()) or location_like(l.text) for l in content):
            continue
        for line in content:
            candidates = [l for l in lines if l.page == page and l.bbox and l.table is None
                          and l.flow != flow and l.bbox[2] < line.bbox[0]
                          and l.text.strip() and l.text.strip() not in BULLETS
                          and abs((l.bbox[1]+l.bbox[3]-line.bbox[1]-line.bbox[3])/2) <= 6
                          and not dates.fullmatch(l.text.strip()) and not location_like(l.text)]
            candidates.sort(key=lambda l: (abs(l.bbox[1]-line.bbox[1]), l.id))
            if not candidates: continue
            anchor = candidates[0]
            if len(candidates)>1 and abs(candidates[1].bbox[1]-line.bbox[1]) - abs(anchor.bbox[1]-line.bbox[1]) < 1:
                notes.append({'path':'reading_order','reason':'Ambiguous aligned metadata: '+line.id,'confidence':0.0})
                continue
            moved[line.id] = anchor.id
            after[anchor.id].append(replace(line, flow=anchor.flow))
    out=[]
    for line in lines:
        if line.id in moved: continue
        out.append(line)
        out.extend(sorted(after[line.id],key=lambda l:(l.bbox[0],l.id)))
    return out, notes


def attach_bullets(lines):
    """Merge a detached PDF glyph into the text sharing its visual baseline."""
    attached=defaultdict(list); glyphs=set()
    for line in lines:
        if not line.bbox or line.text.strip() not in BULLETS: continue
        center=(line.bbox[1]+line.bbox[3])/2
        choices=[l for l in lines if l.bbox and l.page==line.page and l.flow==line.flow
                 and l.id!=line.id and l.text.strip() and l.text.strip() not in BULLETS
                 and 0 <= l.bbox[0]-line.bbox[2] <= 40
                 and abs((l.bbox[1]+l.bbox[3])/2-center)<=5]
        if len(choices)==1:
            attached[choices[0].id].append(line);glyphs.add(line.id)
    out=[]
    for line in lines:
        if line.id in glyphs:continue
        if line.id in attached:
            gs=attached[line.id]
            line=replace(line,text='• '+line.text,bullet=True,
                         source_ids=[sid for g in gs for sid in g.source_ids]+list(line.source_ids),
                         runs=[r for g in gs for r in g.runs]+list(line.runs))
        out.append(line)
    return out
