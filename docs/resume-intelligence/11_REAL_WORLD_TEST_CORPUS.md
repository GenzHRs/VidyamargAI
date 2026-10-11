# 11. Real-World Resume Test Corpus Specification

## 1. Executive Summary & Objective

VidyaMarg AI requires bulletproof extraction completeness across diverse real-world resume formats, visual layouts, and edge conditions. This document outlines the composition, methodology, and licensing boundaries of the **41-fixture Real-World Test Corpus** (`backend/tests/real_world_corpus/`).

The objective is to validate extraction fidelity against rigorous ground truth across the entire production lifecycle:
$$\text{Raw Upload} \longrightarrow \text{Format Parsing} \longrightarrow \text{Layout Detection} \longrightarrow \text{OCR} \longrightarrow \text{Link Recovery} \longrightarrow \text{Normalization} \longrightarrow \text{DB Sync} \longrightarrow \text{PDF Render}$$

---

## 2. Corpus Architecture & Directory Layout

The corpus is structured into three strictly synchronized subsystems:

```
backend/tests/real_world_corpus/
├── manifest.json                  # Canonical 41-fixture index with metadata & challenge tags
├── fixtures/                      # Deterministically synthesized and curated binary test files
│   ├── rw_01_pdf_selectable.pdf
│   ├── rw_02_pdf_scanned_ocr.pdf
│   ├── ...
│   └── rw_41_edge_unsupported.xyz
└── ground_truth/                  # Field-by-field JSON expected outputs (verified ground truth)
    ├── rw_01_truth.json
    ├── rw_02_truth.json
    ├── ...
    └── rw_41_truth.json
```

---

## 3. Fixture Matrix & Taxonomy

The 41 fixtures are stratified across four critical operational dimensions:

| ID | Fixture Filename | Format | Primary Layout / Archetype | Page Count | Key Challenge |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **rw_01** | `rw_01_pdf_selectable.pdf` | PDF | ATS Standard Chronological | 1 | Base vector text, clean sections, embedded links |
| **rw_02** | `rw_02_pdf_scanned_ocr.pdf` | PDF | Scanned Bitmap Document | 1 | Pure raster image page, OCR trigger, layout angles |
| **rw_03** | `rw_03_pdf_mixed_text_image.pdf` | PDF | Hybrid Vector-Raster PDF | 1 | Mixed vector body with raster certificates/badges |
| **rw_04** | `rw_04_docx_paragraphs.docx` | DOCX | Native Paragraph Flow | 1 | Standard Word document styles, headings, bullets |
| **rw_05** | `rw_05_docx_tables.docx` | DOCX | Grid / Table-Formatted Resume | 1 | Two-column borderless tables, body reading order |
| **rw_06** | `rw_06_docx_hyperlinks_styled.docx` | DOCX | Styled Hyperlink Word Doc | 1 | Embedded `w:hyperlink` relationships, rFonts |
| **rw_07** | `rw_07_doc_legacy.doc` | DOC | Legacy Microsoft Word 97-2003 | 1 | Compound binary OLE2 container / RTF fallback |
| **rw_08** | `rw_08_rtf_formatted.rtf` | RTF | Rich Text Format Document | 1 | RTF control word groups (`\par`, `\field`) |
| **rw_09** | `rw_09_odt_standard.odt` | ODT | OpenDocument Text | 1 | Zip-compressed XML (`content.xml`), xlink tags |
| **rw_10** | `rw_10_txt_plain.txt` | TXT | Plain ASCII Text | 1 | Monospace spacing, uppercase heading markers |
| **rw_11** | `rw_11_html_export.html` | HTML | Semantic Web Document | 1 | DOM tags (`<section>`, `<h3>`, `<ul>`, `<a>`) |
| **rw_12** | `rw_12_image_png.png` | PNG | High-Res Raster Screenshot | 1 | 300 DPI raster canvas, no font table metadata |
| **rw_13** | `rw_13_image_jpg.jpg` | JPEG | Compressed Color Photograph | 1 | Lossy compression artifacts, non-white backgrounds |
| **rw_14** | `rw_14_image_tiff.tiff` | TIFF | Scanned Multi-Strip Archive | 1 | LZW compression, enterprise scanner profile |
| **rw_15** | `rw_15_pptx_slides.pptx` | PPTX | Slide Deck Portfolio Resume | 1 | Shape tree textboxes, non-linear reading order |
| **rw_16** | `rw_16_ats_single_column_chronological.pdf` | PDF | ATS Single-Column Chronological | 1 | Standard linear chronology, standard dates |
| **rw_17** | `rw_17_ats_reverse_chronological.pdf` | PDF | ATS Reverse-Chronological | 1 | Most recent role first, promotion trajectories |
| **rw_18** | `rw_18_ats_functional_skills_focused.pdf` | PDF | ATS Functional (Skills-Based) | 1 | Skills clusters preceding brief employment history |
| **rw_19** | `rw_19_ats_combination_hybrid.pdf` | PDF | Hybrid ATS Combination | 1 | Summary of competencies + chronological depth |
| **rw_20** | `rw_20_academic_cv_publications.pdf` | PDF | Academic Curriculum Vitae | 2 | Publications, grants, teaching experience |
| **rw_21** | `rw_21_executive_leadership.pdf` | PDF | Executive Leadership Profile | 2 | P&L ownership, board relations, corporate scope |
| **rw_22** | `rw_22_entry_level_graduate.pdf` | PDF | Entry-Level Graduate | 1 | Education top, GPA, coursework, extracurriculars |
| **rw_23** | `rw_23_technical_systems_architect.pdf` | PDF | Enterprise Cloud Architect | 2 | Multi-cloud systems, enterprise architecture |
| **rw_24** | `rw_24_career_change_transition.pdf` | PDF | Career Transition Profile | 1 | Transferable skills, domain shift, bootcamps |
| **rw_25** | `rw_25_modern_two_column_balanced.pdf` | PDF | Balanced 50/50 Dual Column | 1 | Left: Experience / Right: Education & Skills |
| **rw_26** | `rw_26_modern_left_sidebar_skills_contact.pdf` | PDF | Left Sidebar (30/70) | 1 | Dark sidebar with contact & skills, body right |
| **rw_27** | `rw_27_modern_right_sidebar.pdf` | PDF | Right Sidebar (70/30) | 1 | Main chronology left, meta/skills right |
| **rw_28** | `rw_28_modern_canva_decorative_headings.pdf` | PDF | Canva Stylized Graphic Layout | 1 | Decorative lines, uppercase headings |
| **rw_29** | `rw_29_modern_icon_contact_skillbars.pdf` | PDF | Icon Contact & Percentage Bars | 1 | Glyphs instead of labels, percentage skill bars |
| **rw_30** | `rw_30_complex_multipage_repeated_headers.pdf` | PDF | Multi-Page Repeated Header | 2 | Candidate header repeated on page 2 |
| **rw_31** | `rw_31_complex_tables_education_experience.pdf` | PDF | Complex Multi-Row Tables | 1 | Table grids containing roles and degrees |
| **rw_32** | `rw_32_complex_unconventional_headings.pdf` | PDF | Unconventional Section Headings | 1 | Non-standard headings ("Where I've Been", etc.) |
| **rw_33** | `rw_33_edge_multijob_same_company.pdf` | PDF | Multi-Role Single Employer | 1 | Nested promotions within Google LLC |
| **rw_34** | `rw_34_edge_multiproject_same_tech.pdf` | PDF | Multi-Project Shared Stack | 1 | Distributed tech stack attributes across projects |
| **rw_35** | `rw_35_edge_split_urls_anchor_mismatch.pdf` | PDF | Split URLs & Mismatched Anchors | 1 | Clickable text differs from destination href |
| **rw_36** | `rw_36_edge_unicode_hyphenated_ligatures.pdf` | PDF | Unicode Ligatures & Hyphens | 1 | Ligatures (`ﬁ`, `ﬂ`), smart quotes, en-dashes |
| **rw_37** | `rw_37_edge_prompt_injection_security.pdf` | PDF | Hostile Prompt Injection | 1 | Malicious prompt overrides inside hidden text |
| **rw_38** | `rw_38_edge_corrupted.pdf` | PDF | Truncated / Corrupt Binary | 0 | Header only, missing xref table, EOF missing |
| **rw_39** | `rw_39_edge_empty.pdf` | PDF | Zero-Byte Empty Payload | 0 | 0 bytes uploaded to endpoint |
| **rw_40** | `rw_40_edge_encrypted.pdf` | PDF | Encrypted / Password Protected | 1 | Standard 128-bit AES user password lock |
| **rw_41** | `rw_41_edge_unsupported.xyz` | XYZ | Unsupported Binary Format | 0 | Prohibited extension & non-document magic bytes |

---

## 4. Synthesis Methodology & PII Compliance

### Deterministic Generation
To ensure 100% reproducible testing without flaky external network dependencies, all 41 test fixtures are deterministically built via `backend/tests/real_world_corpus/fixture_builder.py`.
- **PyMuPDF (`fitz`)**: Used to construct vector PDFs with exact coordinates, dual-column bounding boxes, annotations, and multi-page flows.
- **`python-docx`**: Used to construct strict OpenXML Word documents with body paragraph-table sequences and relationship XML trees.
- **Pillow (`PIL`)**: Used to rasterize 300 DPI image canvases for PNG, JPEG, and TIFF fixtures.
- **`python-pptx`**: Used to generate Presentation shape trees.

### Privacy & License Compliance
- **Zero Real PII**: Every single name, email address, telephone number, and physical address in this corpus is completely synthetic (e.g., Marcus Vance, Rachel Sterling, Elena Rostova, Marcus Chen).
- **Domain Names**: All email domains use RFC 2606 reserved domains (`example.com`, `apexcloud.io`, `nexuscore.io`).
- **Copyright Free**: All documents are generated under the MIT license for VidyaMarg AI testing purposes and contain no proprietary third-party template assets.
