# Universal Resume Ingestion — Format Support Matrix

**Document Version**: 2.0.0  
**Status**: Production Verified  
**Engine Reference**: `backend/app/services/resume_extractor_engine.py`

---

## 1. Supported Document Formats Overview

The VidyaMarg AI extraction engine supports 15 distinct file extensions covering PDF, modern Word, legacy binary documents, open standards, rich text, markup, plain text, presentations, and image formats.

| Format / Extension | MIME Type / Magic Header | Handler Function | Hyperlink Capture Method | Layout & Column Awareness | OCR Fallback Support |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PDF (`.pdf`)** | `application/pdf`<br>`%PDF-` | `_extract_pdf_layout_aware` | Spatial bounding box clipping (`page.get_links()` + `page.get_text(clip=...)`) | Multi-column, 2-column sidebar, header banner | Yes (< 50 chars threshold) |
| **DOCX (`.docx`)** | `application/vnd.openxmlformats-officedocument.wordprocessingml.document`<br>`PK\x03\x04` | `_extract_docx_with_tables` | OpenXML `w:hyperlink` elements mapped to `document.part.rels` | Body paragraphs, tabular rows/cols, text boxes (`w:txbxContent`) | N/A (Structured) |
| **DOC (`.doc`)** | `application/msword`<br>`\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1` | `_extract_doc_content` | Stream text URL regex recovery | Sequential text stream extraction | N/A (Structured) |
| **ODT (`.odt`)** | `application/vnd.oasis.opendocument.text`<br>`PK\x03\x04` | `_extract_odt_content` | OpenDocument `text:a` tags mapped to `xlink:href` | Headings, paragraphs, cell tables | N/A (Structured) |
| **RTF (`.rtf`)** | `application/rtf`, `text/rtf`<br>`{\rtf` | `_extract_rtf_content` | Control word parsing: `{\field{\*\fldinst{HYPERLINK "url"}}{\fldrslt label}}` | Group and paragraph line separation | N/A (Structured) |
| **HTML (`.html`, `.htm`)** | `text/html`<br>`<!DOCTYPE` / `<html` | `_extract_html_content` | Semantic DOM parsing via BeautifulSoup: `<a href="...">label</a>` | Semantic heading hierarchy (`h1`-`h6`, `table`, `ul`/`li`) | N/A (Structured) |
| **TXT (`.txt`)** | `text/plain` | `_extract_plain_text` | Regex URL and email pattern recovery | Newline and indentation preserving | N/A (Plain text) |
| **LaTeX (`.tex`)** | `text/x-tex`, `application/x-tex` | `_extract_tex_clean` | TeX `\href{url}{label}` and URL pattern recovery | Strips comment lines (`%`), preserves sections | N/A (Source code) |
| **PNG (`.png`)** | `image/png`<br>`\x89PNG\r\n\x1a\n` | `_extract_image_content` | Plaintext pattern recovery on OCR text | In-memory PDF synthesis + PaddleOCR/PyMuPDF | Yes (Primary engine) |
| **JPEG (`.jpg`, `.jpeg`)** | `image/jpeg`<br>`\xff\xd8\xff` | `_extract_image_content` | Plaintext pattern recovery on OCR text | In-memory PDF synthesis + PaddleOCR/PyMuPDF | Yes (Primary engine) |
| **TIFF (`.tiff`, `.tif`)** | `image/tiff`<br>`II*\x00` / `MM\x00*` | `_extract_image_content` | Plaintext pattern recovery on OCR text | In-memory PDF synthesis + PaddleOCR/PyMuPDF | Yes (Primary engine) |
| **PPTX (`.pptx`)** | `application/vnd.openxmlformats-officedocument.presentationml.presentation`<br>`PK\x03\x04` | `_extract_pptx_content` | OpenXML slide shape hyperlinks | Slide shape hierarchy, text bodies, table cells | N/A (Structured) |

---

## 2. Format Ingestion Specifications

### 2.1 PDF Ingestion (`.pdf`)
- **PyMuPDF / fitz Engine**: Fast, thread-safe C-bindings with zero external rendering dependencies.
- **Scanned Document Detection**: Pages generating fewer than 50 selectable characters trigger OCR extraction using `PaddleOCR` (or in-memory PyMuPDF OCR).
- **Security Check**: Enforces `doc.is_encrypted` and `doc.needs_pass`. Files requiring a decryption password return:
  ```json
  {
    "status": 400,
    "error_code": "FILE_ENCRYPTED",
    "message": "Encrypted or password-protected PDF detected. Please remove password protection before uploading."
  }
  ```

### 2.2 DOCX Ingestion (`.docx`)
- **Table Reconstruction**: Tables are extracted row-by-row, column-by-column, formatting cell contents into structured lines (`Key: Value`) instead of jumbled strings.
- **Floating Text Boxes**: Scans `w:txbxContent` in the document body XML to recover content placed inside sidebar containers or shapes.
- **Embedded Links**: Resolves relationship identifiers (`r:id`) to hyperlink targets in document relationships.

### 2.3 ODT Ingestion (`.odt`)
- **Pure-Python Architecture**: Uses standard library `zipfile` and `xml.etree.ElementTree` without requiring LibreOffice or external desktop runtimes.
- **Element Mapping**:
  - `text:h`: Converted to section titles based on outline level.
  - `text:p`: Extracted as structured paragraph text.
  - `table:table`: Reconstructed as structured grid data.
  - `text:a`: Extracted into canonical hyperlink records.

### 2.4 RTF Ingestion (`.rtf`)
- **Control Word Elimination**: Strips formatting words (`\fs24`, `\b`, `\par`, `\deff0`) while decoding hex escaped characters (`\'e9` $\to$ `é`).
- **Field Hyperlinks**: Intercepts `{\field{\*\fldinst{HYPERLINK "url"}}{\fldrslt label}}` and extracts both target URL and visible run text.

### 2.5 HTML Ingestion (`.html`, `.htm`)
- **DOM Cleaning**: Decomposes `<script>`, `<style>`, `<noscript>`, `<meta>`, and `<link>` elements before extraction.
- **Semantic Structure**: Prioritizes `h1`-`h6`, `p`, `li`, `tr` tags to maintain logical reading order.
- **Link Preservation**: Preserves `a[href]` and anchors with parent node context for entity association.

### 2.6 Presentation Ingestion (`.pptx`)
- **Slide Traversal**: Evaluates `ppt/slides/slide*.xml` sequentially.
- **Resilient Fallback**: Uses regex stream extraction `<[a-zA-Z0-9_:]*t[^>]*>(.*?)</[a-zA-Z0-9_:]*t>` when third-party software generates non-compliant slide XML.

### 2.7 Scanned & Image Resumes (`.png`, `.jpg`, `.jpeg`, `.tiff`)
- **Pillow Verification**: Validates image format and integrity via `Image.verify()`.
- **In-Memory Conversion**: Converts image data to PDF via PyMuPDF in memory, avoiding temporary disk writes.
- **OCR Engine**: Employs layout-aware text recognition with angle classification.
