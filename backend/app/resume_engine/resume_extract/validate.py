"""Independent multiset completeness, fixed-schema checks, review routing."""
from __future__ import annotations
from collections import Counter
from typing import Any
import re
from pathlib import Path
import json


def completeness(source: str, extracted: str, config: dict[str, Any]) -> dict[str, Any]:
    """Case-sensitive Unicode word multiset; every missing/extra token fails.

    Pre-processing removes pdftotext font-encoding artifacts before tokenization:
    pdftotext sometimes decodes PDF separator glyphs (e.g., visual dividers in
    contact lines) as isolated Latin-1 supplement characters (U+0080–U+00FF) that
    match \\w but are not produced by pdfplumber.  We normalise both texts with
    NFKC and then strip any isolated single-character Latin-1 supplement token
    (surrounded by non-word context) that would appear as a lone separator word.
    Real Latin-1 letters embedded in actual words (café, naïve) are unaffected
    because they appear adjacent to other word characters.
    """
    import unicodedata as _ud
    # Regex to strip isolated single Latin-1 supplement chars used as separators.
    # Matches a word-boundary-isolated single char in U+0080-U+00FF.
    _sep_glyphs=re.compile(r'(?<!\w)[\x80-\xff](?!\w)')
    pattern=config['validate']['word_pattern']
    def _norm(t: str) -> str:
        return _sep_glyphs.sub(' ', _ud.normalize('NFKC', t))
    norm_source=_norm(source);norm_extracted=_norm(extracted)
    expected=Counter(re.findall(pattern,norm_source));actual=Counter(re.findall(pattern,norm_extracted))
    missing=expected-actual;extra=actual-expected
    matched=sum((expected&actual).values());total=sum(expected.values());produced=sum(actual.values())
    return {'status':'pass' if not missing and not extra else 'fail','reference_words':total,'extracted_words':produced,
            'matched_words':matched,'recall':matched/total if total else (1.0 if not produced else 0.0),
            'precision':matched/produced if produced else (1.0 if not total else 0.0),
            'missing':dict(sorted(missing.items())),'extra':dict(sorted(extra.items()))}


def needs_review(fields: dict[str, Any], sections: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return every low-confidence nested field, null candidate and custom section."""
    result=[];threshold=config['validate']['review_threshold']
    def visit(value: Any,path: str) -> None:
        if isinstance(value,dict):
            if 'confidence' in value and (value['confidence']<threshold or ('value' in value and value['value'] is None)):
                result.append({'path':path,'reason':'missing or low-confidence candidate','confidence':value['confidence']})
            for key,item in value.items():visit(item,path+'.'+key)
        elif isinstance(value,list):
            for i,item in enumerate(value):visit(item,f'{path}[{i}]')
    visit(fields,'fields');visit(sections,'sections')
    if fields['name'] is None:result.append({'path':'fields.name','reason':'No candidate name found','confidence':0.0})
    return result


def validate_schema(data: Any, schema: dict[str, Any] | None = None) -> list[str]:
    """Validate the shipped schema subset using stdlib, with recursive $ref checks."""
    root=schema or json.loads(Path(__file__).with_name('schema.json').read_text(encoding='utf-8'))
    errors=[]
    types={'object':dict,'array':list,'string':str,'number':(int,float),'integer':int,'boolean':bool,'null':type(None)}
    def check(value: Any,spec: dict[str,Any],path: str) -> None:
        if '$ref' in spec:
            spec=root['$defs'][spec['$ref'].split('/')[-1]]
        expected=spec.get('type');choices=expected if isinstance(expected,list) else [expected] if expected else []
        if choices and not any(isinstance(value,types[t]) and not (t in ('number','integer') and isinstance(value,bool)) for t in choices):
            errors.append(path+': incorrect type');return
        if 'enum' in spec and value not in spec['enum']:errors.append(path+': invalid enum')
        if isinstance(value,(float,int)) and not isinstance(value,bool):
            if 'minimum' in spec and value<spec['minimum']:errors.append(path+': below minimum')
            if 'maximum' in spec and value>spec['maximum']:errors.append(path+': above maximum')
        if isinstance(value,dict):
            for key in spec.get('required',[]):
                if key not in value:errors.append(path+'.'+key+': required')
            for key,item in value.items():
                if key in spec.get('properties',{}):check(item,spec['properties'][key],path+'.'+key)
                elif spec.get('additionalProperties') is False:errors.append(path+'.'+key+': unknown property')
        if isinstance(value,list):
            for i,item in enumerate(value):check(item,spec.get('items',{}),f'{path}[{i}]')
    check(data,root,'$')
    return errors
