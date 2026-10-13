"""Source-preserving text rules shared by structured extractors."""
import re


def split_top_level(text, delimiters=',;|•'):
    """Split lists only outside balanced parentheses/brackets/braces."""
    parts=[]; start=0; stack=[]; pairs={')':'(',']':'[','}':'{'}
    for i,char in enumerate(text):
        if char in '([{':stack.append(char)
        elif char in pairs and stack and stack[-1]==pairs[char]:stack.pop()
        elif char in delimiters and not stack:
            if text[start:i].strip():parts.append(text[start:i].strip())
            start=i+1
    if text[start:].strip():parts.append(text[start:].strip())
    return parts


def split_institution_location(text):
    """Use explicit separators or city + region; keep single-comma campus names."""
    match=re.search(r'\s+[—–]\s+([^,]+,\s*[^,]+)$',text)
    if match and not re.search(r'\b(?:School|College|Faculty)\b',match[1],re.I):
        return text[:match.start()].strip(),match[1].strip()
    parts=text.rsplit(',',2)
    if len(parts)==3 and not re.search(r'\b(?:School|College|University|Institute)\b',parts[1],re.I):
        return parts[0].strip(),', '.join(p.strip() for p in parts[1:])
    return text,None
