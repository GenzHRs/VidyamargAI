# Document 08 — Ground Truth Test Corpus Specification

**VidyaMarg AI — Document Intelligence & Resume Parsing Architecture**  
**Version:** 2.0-Production  
**Status:** Approved & Implemented  
**Date:** October 2026  

---

## 1. Overview and Objectives

To ensure zero-regression document extraction across all real-world formats and layouts, VidyaMarg AI establishes a comprehensive **12-Fixture Ground Truth Test Corpus**. Each fixture is programmatically generated in-memory with precise coordinate geometries, typographies, and challenging edge-case patterns.

Every fixture defines:
1. **Layout & Geometry:** Document format, dimension, column splits, and block layout.
2. **Challenge Points:** Specific edge cases designed to stress-test the pipeline.
3. **Expected Ground Truth:** The strict, verified extraction output required for test passage.

---

## 2. Test Corpus Inventory

| Fixture ID | Fixture Name | Format | Primary Architectural Challenge | Pass Status |
|---|---|---|---|---|
| **F01** | `single_column_standard` | PDF (A4) | Baseline chronological extraction, zero hallucinations | **PASSED** |
| **F02** | `two_column_left_sidebar` | PDF (A4) | Left sidebar gutter sweep ($X \approx 200$), non-interleaving | **PASSED** |
| **F03** | `two_column_right_sidebar` | PDF (A4) | Right sidebar gutter sweep ($X \approx 380$), chronological order | **PASSED** |
| **F04** | `scanned_pdf_ocr_fallback` | PDF (Image) | Low text density detection ($<20$ words), OCR trigger | **PASSED** |
| **F05** | `docx_tables_and_links` | DOCX | Table cells extraction, XML relationships hyperlinks | **PASSED** |
| **F06** | `multipage_running_headers` | PDF (2-Page) | Multi-page running header/footer suppression across pages 2..N | **PASSED** |
| **F07** | `multijob_single_company` | PDF (A4) | Active employer tracking across consecutive promotions | **PASSED** |
| **F08** | `multiple_projects_long_bullets` | Synthetic | Deduplication of overview text against bullets, no fake bullets | **PASSED** |
| **F09** | `unusual_headings_handling` | Text/PDF | Non-standard section mappings ("Scholastic", "Milestones") | **PASSED** |
| **F10** | `concatenated_tech_stack` | String list | Tokenization of slash-separated dense technology strings | **PASSED** |
| **F11** | `unicode_ligatures_multilingual` | Text/PDF | NFKD decomposition of ligatures (`ﬁ`, `ﬂ`, `ﬃ`), C++/C# safety | **PASSED** |
| **F12** | `hyperlinks_custom_labels` | PDF (Links) | Visible label recovery, block-level binding to project entities | **PASSED** |

---

## 3. Detailed Fixture Specifications

### Fixture 01: Single-Column Standard Chronological (`single_column_standard`)
* **Geometry:** Standard single column ($X \in [50, 545]$, $W=595, H=842$).
* **Challenge:** Baseline extraction validation. Ensures personal contact information, summary, work experience, education, and skills are extracted completely with zero injected placeholder strings.
* **Ground Truth Expectations:**
  - Name: `ALEX MERCER`
  - Email: `alex.mercer@example.com`
  - Experience: 2 jobs (`Acme Corporation`, `Beta Labs`).
  - Responsibilities: Exact bullet texts preserved.
  - Zero placeholder strings: `"Designed and implemented project functionality."` and `"Key contributor to team deliverables."` must be completely absent.

---

### Fixture 02: Two-Column Left Sidebar Layout (`two_column_left_sidebar`)
* **Geometry:** Left sidebar ($X \in [50, 190]$), Right main column ($X \in [230, 550]$). Gutter exists between $X=190$ and $X=230$.
* **Challenge:** Dynamic vertical gutter detection must identify the left sidebar without line-by-line interleaving of sidebar contact/skills with right-column experience bullets.
* **Ground Truth Expectations:**
  - Layout detected: `left_sidebar` or `two_column`.
  - Reading order: Full header $\to$ Left column (Contact, Skills, Education) $\to$ Right column (Experience).
  - Experience text remains uninterrupted and coherent.

---

### Fixture 03: Two-Column Right Sidebar Layout (`two_column_right_sidebar`)
* **Geometry:** Left main column ($X \in [50, 360]$), Right sidebar ($X \in [400, 550]$). Gutter exists between $X=360$ and $X=400$.
* **Challenge:** Gutter sweep must detect split at $X \approx 380$. Right-sidebar skills and education must not interleave into left-column experience bullets. Header detection must not misclassify wide experience bullets as headers.
* **Ground Truth Expectations:**
  - Layout detected: `right_sidebar` or `two_column`.
  - Employer: `Stripe`
  - Role: `Staff Systems Engineer`
  - All bullets sorted in chronological, vertical reading order.

---

### Fixture 04: Scanned PDF / Image OCR Fallback (`scanned_pdf_ocr_fallback`)
* **Geometry:** Single page with sparse text ($<15$ words) simulating a scanned document or raster graphic.
* **Challenge:** Word density threshold ($<20$ words or $<100$ characters) triggers OCR pipeline with PaddleOCR and pytesseract fallbacks without crashing.
* **Ground Truth Expectations:**
  - Scanned page flagged: `page 1` in `layout_info["scanned_pages"]`.
  - Non-empty readable raw text produced.

---

### Fixture 05: DOCX Tables and Relationships (`docx_tables_and_links`)
* **Geometry:** Word document containing structured tables for skills and body paragraphs for experience.
* **Challenge:** Extract table cells in logical order (row-by-row, column-by-column) and merge with paragraph runs.
* **Ground Truth Expectations:**
  - Name: `Sarah Jenkins`
  - Table skills: `Python, Go, Java, SQL`, `AWS, Kubernetes, Terraform, Docker`.
  - Experience: `Dell Technologies` with complete bullet points.

---

### Fixture 06: Multi-Page Running Headers & Footers (`multipage_running_headers`)
* **Geometry:** 2-page PDF. Page 2 includes top margin header ("Elena Rostova | Staff Software Engineer | Resume Page 2") and bottom margin footer ("Confidential Document - Page 2 of 2").
* **Challenge:** Running header and footer on Page 2 must be suppressed and not injected into experience descriptions or job titles.
* **Ground Truth Expectations:**
  - Page 2 experience employer: `Snowflake`
  - Running headers/footers absent from all employer names and bullet points.

---

### Fixture 07: Hierarchical Multi-Job at Single Employer (`multijob_single_company`)
* **Geometry:** Single company ("Google LLC") followed by 3 sequential roles:
  1. Staff Software Engineer (2022 - Present)
  2. Senior Software Engineer (2019 - 2022)
  3. Software Engineer (2017 - 2019)
* **Challenge:** Maintain `active_company` across all roles so roles 2 and 3 retain "Google LLC" as their employer.
* **Ground Truth Expectations:**
  - Experience count: $\ge 3$ entries.
  - Employer for all entries: `Google LLC`.
  - Zero placeholder employer names (`"Company"`).

---

### Fixture 08: Multiple Projects with Long Bullets (`multiple_projects_long_bullets`)
* **Geometry:** Multiple distinct project objects with overview descriptions and detailed bullet points.
* **Challenge:** Deduplicate overview description when redundant with bullet points. Strip fake bullets. Keep projects separate.
* **Ground Truth Expectations:**
  - 2 distinct projects preserved.
  - Project 1 description cleared (was duplicate of bullet 1).
  - All legitimate technical bullets preserved.
  - Zero injected fake bullets.

---

### Fixture 09: Unusual Headings Handling (`unusual_headings_handling`)
* **Geometry:** Resume text using non-standard section headings:
  - `"SCHOLASTIC BACKGROUND"` $\to$ Education
  - `"CAREER MILESTONES & TRAJECTORY"` $\to$ Work Experience
  - `"TECHNICAL TOOLKIT & COMPETENCIES"` $\to$ Skills
  - `"WORKS PUBLISHED"` $\to$ Publications
* **Challenge:** Heuristic section pattern matching maps unusual headings to canonical entities rather than dropping them.
* **Ground Truth Expectations:**
  - Education contains `Stanford University`.
  - Experience contains `Anthropic`.
  - Publications or custom sections contain the NeurIPS paper.

---

### Fixture 10: Concatenated Tech Stack Tokenization (`concatenated_tech_stack`)
* **Geometry:** Dense slash-separated string: `"Python/FastAPI/PostgreSQL/Docker/Kubernetes/Redis/AWS/GraphQL/React.js"`.
* **Challenge:** Tokenizer must split the string into discrete canonical terms without data loss.
* **Ground Truth Expectations:**
  - List of 9 individual skill strings extracted.

---

### Fixture 11: Unicode Ligatures & Multilingual (`unicode_ligatures_multilingual`)
* **Geometry:** Typographical ligatures (`ﬁ`, `ﬂ`, `ﬃ`), curly quotes, and language keywords (`C++`, `C#`).
* **Challenge:** Normalization must decompose ligatures into standard characters without corrupting `C++` or `C#`.
* **Ground Truth Expectations:**
  - `"ﬁle"` $\to$ `"file"`
  - `"ﬂow"` $\to$ `"flow"`
  - `"oﬃce"` $\to$ `"office"`
  - `"C++"` and `"C#"` retained intact.

---

### Fixture 12: Hyperlinks with Custom Labels & Binding (`hyperlinks_custom_labels`)
* **Geometry:** PDF with embedded link annotations:
  - Anchor text: `"Live Demo"` $\to$ `https://editor.devonreed.dev`
  - Anchor text: `"GitHub Repository"` $\to$ `https://github.com/devonreed/editor-core`
* **Challenge:** Visible anchor text preserved alongside target URL. Links occurring within project boundaries bound to project entity.
* **Ground Truth Expectations:**
  - Both URIs captured.
  - Project `RealTime Collaborative Editor` bound to repo/demo URLs.
