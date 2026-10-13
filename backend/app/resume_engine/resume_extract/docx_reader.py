"""Walk OOXML nodes directly, retaining real cells, hyperlinks and run styles."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from zipfile import ZipFile
from lxml import etree
from .models import Document, Line, Run

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS = {'w': W, 'r': R}

def q(name: str) -> str:
    return '{' + W + '}' + name

def xml(data: bytes) -> Any:
    return etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))

def read_docx(path: Path, config: dict[str, Any]) -> Document:
    """Read body order and distinct header/footer parts once, including text boxes.

    Text values are kept verbatim; caps is recorded as presentation metadata.
    Headers precede body and footers follow it. No layout engine is implied.
    """
    lines: list[Line] = []
    warnings: list[str] = []
    with ZipFile(path) as archive:
        names = archive.namelist()
        styles = xml(archive.read('word/styles.xml')) if 'word/styles.xml' in names else None
        style_map = {s.get(q('styleId')): s for s in styles.findall(q('style'))} if styles is not None else {}
        defaults = styles.find('w:docDefaults/w:rPrDefault/w:rPr', NS) if styles is not None else None
        def style_chain(sid: str | None, seen: set[str] | None = None) -> list[Any]:
            seen = set() if seen is None else seen
            if sid not in style_map or sid in seen:
                return []
            seen.add(sid)
            style = style_map[sid]
            based = style.find(q('basedOn'))
            return style_chain(based.get(q('val')) if based is not None else None, seen) + [style.find(q('rPr'))]

        def props(run: Any, paragraph_style: str | None) -> dict[str, Any]:
            rp = run.find(q('rPr'))
            rs = rp.find(q('rStyle')) if rp is not None else None
            layers = [defaults] + style_chain(paragraph_style or 'Normal') + style_chain(rs.get(q('val')) if rs is not None else None) + [rp]
            result: dict[str, Any] = {'bold': False, 'size': None, 'color': None, 'caps': False, 'font': None}
            for layer in layers:
                if layer is None: continue
                for key, name in [('bold','b'), ('caps','caps')]:
                    el = layer.find(q(name))
                    if el is not None: result[key] = el.get(q('val'), '1') not in ('0','false','off')
                for key, name in [('size','sz'), ('color','color'), ('font','rFonts')]:
                    el = layer.find(q(name))
                    if el is not None:
                        value = el.get(q('ascii')) if key == 'font' else el.get(q('val'))
                        result[key] = float(value) / 2 if key == 'size' and value else value
            return result

        parts = sorted(n for n in names if n.startswith('word/header') and n.endswith('.xml'))
        parts += ['word/document.xml']
        parts += sorted(n for n in names if n.startswith(('word/footer', 'word/footnotes', 'word/endnotes')) and n.endswith('.xml'))
        roots = {part: xml(archive.read(part)) for part in parts}
        for part, root in roots.items():
            relpath = 'word/_rels/' + part.split('/')[-1] + '.rels'
            rels = {x.get('Id'): x.get('Target') for x in xml(archive.read(relpath))} if relpath in names else {}
            table_count = [0]
            def walk(node: Any, ctx: dict[str, Any]) -> None:
                if node.tag == q('tbl'):
                    table_count[0] += 1
                    tid = f'{part}:t{table_count[0]}'
                    # Wrappers such as sdt around rows/cells are transparent.
                    rows = node.xpath('.//w:tr', namespaces=NS)
                    rows = [r for r in rows if next(r.iterancestors(q('tbl')), None) is node]
                    for ri, row in enumerate(rows):
                        cells = [c for c in row.xpath('.//w:tc', namespaces=NS) if next(c.iterancestors(q('tr')), None) is row]
                        for ci, cell in enumerate(cells):
                            walk(cell, {**ctx, 'table': tid, 'row': ri, 'cell': ci, 'flow': f'{tid}:r{ri}:c{ci}'})
                    return
                if node.tag == q('p'):
                    ps = node.find('w:pPr/w:pStyle', NS)
                    sid = ps.get(q('val')) if ps is not None else None
                    numbered = node.find('w:pPr/w:numPr', NS) is not None
                    if not numbered and sid in style_map:
                        numbered = style_map[sid].find('w:pPr/w:numPr', NS) is not None
                    bucket: list[Run] = []
                    def flush() -> None:
                        if not bucket: return
                        lid = f'l{len(lines):05d}'
                        lines.append(Line(lid, ''.join(r.text for r in bucket), list(bucket),
                                          part=part, style=sid, bullet=numbered,
                                          source_ids=[lid], **ctx))
                        bucket.clear()
                    def inline(el: Any, formatting: dict[str, Any] | None = None, link: str | None = None) -> None:
                        if el.tag == q('txbxContent'):
                            flush()
                            walk(el, {**ctx, 'flow': ctx['flow'] + ':textbox'})
                            return
                        if el.tag == q('r'):
                            formatting = props(el, sid)
                        if el.tag == q('hyperlink'):
                            link = rels.get(el.get('{' + R + '}id'))
                        if el.tag in (q('t'), q('delText')):
                            # Deleted text is retained and flagged, never silently cleaned away.
                            if el.tag == q('delText'): warnings.append('Tracked deletion text retained')
                            bucket.append(Run(el.text or '', **(formatting or {}), hyperlink=link))
                        elif el.tag in (q('br'), q('cr')):
                            flush()
                        elif el.tag == q('tab'):
                            bucket.append(Run('\t', **(formatting or {})))
                        elif el.tag == q('noBreakHyphen'):
                            bucket.append(Run('‑', **(formatting or {})))
                        elif el.tag == q('softHyphen'):
                            bucket.append(Run('\u00ad', **(formatting or {})))
                        elif el.tag == q('sym'):
                            value = el.get(q('char'))
                            if value: bucket.append(Run(chr(int(value,16)), **(formatting or {})))
                        else:
                            for child in el: inline(child, formatting, link)
                    inline(node)
                    flush()
                    return
                for child in node: walk(child, ctx)
            walk(root, {'flow': part})
        # Independent XML text baseline: concatenate within runs/paragraphs,
        # preserve break/tab boundaries, including wrappers and textboxes.
        def source(node: Any) -> str:
            if node.tag in (q('t'),q('delText')): return node.text or ''
            if node.tag in (q('br'), q('cr'), q('tab')): return '\n'
            if node.tag == q('noBreakHyphen'): return '‑'
            if node.tag == q('softHyphen'): return '\u00ad'
            if node.tag == q('sym'): return chr(int(node.get(q('char')),16))
            text = ''.join(source(child) for child in node)
            return '\n'+text+'\n' if node.tag in (q('p'),q('tc'),q('txbxContent')) else text
        source_text = '\n'.join(source(root) for root in roots.values())
        if any(root.find('.//w:altChunk', NS) is not None for root in roots.values()):
            warnings.append('Unsupported altChunk embedded content: manual review required')
    return Document(lines, source_text, 'docx_xml_text', warnings=sorted(set(warnings)))
