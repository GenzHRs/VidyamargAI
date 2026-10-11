# VidyamargAI — Phase 0 Error Analysis & Loss Attribution Report

**Audit Date**: October 2026  
**Corpus Fixtures Analyzed**: 48  
**Total Ground-Truth Entities Evaluated**: 536  
**Entities Successfully Extracted**: 371 (69.2%)  
**Total Entities Lost / Omitted**: 165  

---

## 1. Loss Causes Ranked by Pipeline Stage

| Rank | Pipeline Stage | Missed Entities | % of Total Losses | Primary Root Cause |
| :---: | :--- | :---: | :---: | :--- |
| 1 | `llm_heuristic_extraction` | **81** | 49.1% | Parser omitted entity present in raw text (heading ambiguity, regex boundary). |
| 2 | `text_extraction` | **63** | 38.2% | OCR degradation on scanned bitmaps, font ligature issues, or prompt truncation. |
| 3 | `evaluator_matcher` | **21** | 12.7% | Strict matcher artifact (key mismatch e.g. `skills.technical` vs category dict). |

---

## 2. Loss Frequency Ranked by Entity Field

| Rank | Field Path | Missed Count | % of Field Losses | Loss Characteristics |
| :---: | :--- | :---: | :---: | :--- |
| 1 | `skills.technical` | **47** | 28.5% | High frequency drop target |
| 2 | `work_experience.employer` | **39** | 23.6% | High frequency drop target |
| 3 | `education.institution` | **28** | 17.0% | High frequency drop target |
| 4 | `personal_info.phone` | **19** | 11.5% | High frequency drop target |
| 5 | `personal_info.location` | **8** | 4.8% | High frequency drop target |
| 6 | `professional_summary` | **8** | 4.8% | High frequency drop target |
| 7 | `projects.name` | **7** | 4.2% | High frequency drop target |
| 8 | `personal_info.full_name` | **5** | 3.0% | High frequency drop target |
| 9 | `personal_info.email` | **4** | 2.4% | High frequency drop target |

---

## 3. Loss Frequency by Layout Category

| Rank | Layout Category | Missed Count | % of Total Losses |
| :---: | :--- | :---: | :---: |
| 1 | Scanned Bitmap Document | **14** | 8.5% |
| 2 | Raster Image (PNG) | **13** | 7.9% |
| 3 | Raster Image (JPEG) | **13** | 7.9% |
| 4 | Raster Image (TIFF) | **13** | 7.9% |
| 5 | 5+ Page Executive CV | **12** | 7.3% |
| 6 | Hybrid Vector-Raster PDF | **11** | 6.7% |
| 7 | Two-Column with Full-Width Header | **8** | 4.8% |
| 8 | Three-Column Complex Magazine | **7** | 4.2% |
| 9 | ATS Standard Chronological | **4** | 2.4% |
| 10 | ATS Single-Column Chronological | **4** | 2.4% |
| 11 | ATS Reverse Chronological | **4** | 2.4% |
| 12 | Career Change Transition | **4** | 2.4% |
| 13 | Unconventional Headings Layout | **4** | 2.4% |
| 14 | RTL Multilingual Arabic-English | **4** | 2.4% |
| 15 | Interactive AcroForm Fields | **4** | 2.4% |
| 16 | Functional Skills-Focused Layout | **3** | 1.8% |
| 17 | Hybrid Combination Layout | **3** | 1.8% |
| 18 | Executive Leadership Format | **3** | 1.8% |
| 19 | Entry-Level Graduate Resume | **3** | 1.8% |
| 20 | Modern Left Sidebar | **3** | 1.8% |
| 21 | Canva Stylized Layout | **3** | 1.8% |
| 22 | Icon Contact & Graphical Skillbars | **3** | 1.8% |
| 23 | CJK Japanese-English Multilingual | **3** | 1.8% |
| 24 | Standard DOCX Document | **2** | 1.2% |
| 25 | Plain ASCII Text | **2** | 1.2% |
| 26 | Semantic HTML Export | **2** | 1.2% |
| 27 | Technical Systems Architect | **2** | 1.2% |
| 28 | Multi-page Repeated Running Headers | **2** | 1.2% |
| 29 | PDF Tabular Cells | **2** | 1.2% |
| 30 | Adversarial Prompt Injection Defense | **2** | 1.2% |
| 31 | Legacy Word 97-2003 Binary | **1** | 0.6% |
| 32 | OpenDocument Text (.odt) | **1** | 0.6% |
| 33 | Academic CV Layout | **1** | 0.6% |
| 34 | Modern Two-Column Balanced | **1** | 0.6% |
| 35 | Modern Right Sidebar | **1** | 0.6% |
| 36 | Multi-Job Same Company Promotion | **1** | 0.6% |
| 37 | Multi-Project Shared Tech Stack | **1** | 0.6% |
| 38 | Unicode Ligatures & Hyphenated Lines | **1** | 0.6% |

---

## 4. Loss Frequency by Document Format

| Format | Missed Count | % of Total Losses |
| :--- | :---: | :---: |
| `.pdf` | **118** | 71.5% |
| `.png` | **13** | 7.9% |
| `.jpg` | **13** | 7.9% |
| `.tiff` | **13** | 7.9% |
| `.docx` | **2** | 1.2% |
| `.txt` | **2** | 1.2% |
| `.html` | **2** | 1.2% |
| `.doc` | **1** | 0.6% |
| `.odt` | **1** | 0.6% |

---

## 5. Key Discoveries & Recommendations for Phase 1

1. **Matcher Artifact Discrepancy**: A large volume of reported misses in previous benchmarks stemmed from the evaluator looking exclusively for `structured['skills']['technical']` rather than flattening all skill category buckets (`programming_languages`, `databases`, `cloud_platforms`, etc.) and `all_raw_skills`.
2. **Location & Header Parsing**: Personal location is frequently lost when candidates place it on lines with full titles (`Senior Engineer | Austin, TX`) rather than alongside phone numbers.
3. **Bitmap Scans & OCR**: Pure scanned images (`rw_02`, `rw_12`, `rw_13`, `rw_14`) account for the vast majority of `text_extraction` losses, confirming the Windows CPU PaddleX limitation.
4. **Prompt Truncation on 5+ Page CV**: `rw_42` demonstrates that any entities appearing after character 14,000 in long CVs are completely dropped from AI extraction.
