# Document 07 — Root Cause and Data Loss Audit

**VidyaMarg AI — Document Intelligence & Resume Parsing Architecture**  
**Version:** 2.0-Production  
**Status:** Approved & Implemented  
**Date:** October 2026  

---

## 1. Executive Summary

Despite prior iterations aimed at project bullet deduplication and LaTeX rendering, real-world candidate resumes uploaded to VidyaMarg AI continued to suffer from systematic extraction errors, data loss, and hallucinations. A deep, evidence-based audit of the live ingestion pipeline revealed that extraction failures were not random; they stemmed from structural limitations in layout geometry detection, dual-route API divergence, and aggressive default fallbacks that injected synthetic placeholders into database records.

This document presents the complete forensic audit of all root causes, mapping each failure mode directly to the affected files, specific line numbers, and architectural mechanisms in the codebase.

---

## 2. Forensic Failure Mode Audit & Exact Code Attribution

### 2.1 Failure Mode 1: Static Column Split Causing Interleaving of Sidebars
* **Affected Component:** `backend/app/services/resume_extractor_engine.py` (formerly lines 280–310)
* **Root Cause Mechanism:**  
  The engine evaluated a hardcoded vertical coordinate threshold ($X = 0.45 \times \text{page\_width}$) to split blocks into columns. This static assumption broke down for:
  - **Left Sidebars** (common in modern ATS and Canva templates where sidebar $X \in [0.25W, 0.38W]$): The hardcoded $0.45W$ split placed left-column body text into the right column or vice-versa, causing left-column skills to interleave line-by-line into right-column work experience bullets.
  - **Right Sidebars** (where sidebar $X \in [0.60W, 0.75W]$): A split at $0.45W$ cut directly through the middle of the main experience column, splitting sentences and bullet points in half.
  - **Wide Header Detection Flaw:** Wide bullet points (e.g., width $> 0.45W$) occurring near $Y \le 0.16H$ were misclassified as header blocks, hoisting bullet points above the company and job title.
* **Resolution:**  
  Implemented a **Dynamic Gutter Sweep Algorithm** that sweeps candidate vertical gutters from $0.25W$ to $0.75W$ in 10pt increments. It scores each candidate gutter using $S = |L| + |R| - 3 \times |\text{Spanning}|$. Gutters with zero or minimal spanning blocks receive the highest score. Headers are strictly restricted to $Y \le 0.05H$ or full-width title blocks at $Y \le 0.08H$.

---

### 2.2 Failure Mode 2: Injected Placeholder Strings (Hallucinations)
* **Affected Components:**
  - `backend/app/api/routers/resume_center.py` (lines 400–445, 715–765)
  - `backend/app/services/project_normalizer.py` (lines 282–285)
  - `backend/app/services/resume_extractor_engine.py` (lines 1180–1210)
* **Root Cause Mechanism:**  
  When optional or unextracted fields were absent, several fallback expressions injected artificial strings:
  ```python
  # Former code in resume_center.py
  title = e.get("designation") or "Software Engineer"
  company = e.get("employer") or "Company"
  bullets = e.get("responsibilities") or ["Key contributor to team deliverables."]
  degree = ed.get("degree") or "Bachelor of Technology"
  institution = ed.get("institution") or "University"
  bullets = norm_p.get("bullets") or ["Designed and implemented project functionality."]
  ```
  These values entered candidate records, database tables (`resume_experiences`, `resume_educations`, `resume_projects`), and compiled LaTeX resumes, creating synthetic roles and fake bullet points never written by the candidate.
* **Resolution:**  
  Removed all synthetic strings. Empty fields now evaluate to empty strings `""` or `None`. The database schemas retain non-null compliance with empty strings while strictly avoiding any invented titles, degrees, or bullets.

---

### 2.3 Failure Mode 3: Disparate Dual Upload Routes
* **Affected Components:**
  - `backend/app/api/routers/resume.py` (`POST /candidates/resume`, lines 53–104)
  - `backend/app/api/routers/resume_center.py` (`POST /resumes/upload`, lines 799–950)
  - `backend/app/services/orchestrator.py` (`run_resume_collection_agent`, lines 220–310)
* **Root Cause Mechanism:**  
  The application maintained two independent resume upload endpoints:
  1. `POST /candidates/resume`: Called legacy `orchestrator.run_resume_collection_agent()`, which executed naive `pypdf.extract_text()`, bypassed layout detection, created a `CandidateResume` without creating a `Resume` or `ResumeProfile` entry, and failed to update Resume Center.
  2. `POST /resumes/upload`: Called the layout-aware engine and updated `ResumeCenter`.
  Candidates uploading through the onboarding flow bypassed layout analysis entirely, resulting in unparsed or corrupted profiles.
* **Resolution:**  
  Unified both upload routes. `POST /candidates/resume` and `orchestrator.run_resume_collection_agent` now invoke `extract_pdf_layout_aware()`, populate both legacy (`CandidateResume`) and modern (`Resume`, `ResumeExtraction`, `ResumeProfile`, `ResumeExperience`, `ResumeEducation`, `ResumeProject`, `ResumeSkill`, `ResumeVersion`) schemas, and synchronize state atomically via `ResumeContextService.replace_active_resume()`.

---

### 2.4 Failure Mode 4: Multi-Page Running Header and Footer Contamination
* **Affected Component:** `backend/app/services/resume_extractor_engine.py` (lines 240–280)
* **Root Cause Mechanism:**  
  Multi-page resumes (2–4 pages) frequently print running headers ("Jane Doe | Senior Systems Architect | Page 2 of 3") and footers ("Confidential - 2026"). In previous versions, these lines were treated as ordinary body text on pages 2..N, becoming embedded into work experience bullet points or creating spurious job titles.
* **Resolution:**  
  Implemented **Multi-Page Running Header/Footer Suppression**:
  - Scans top 10% and bottom 10% margins of pages 2..N.
  - Detects recurring text patterns matching page 1 header content or page-numbering regexes (`Page X of Y`, `\d+/\d+`).
  - Filters recurring noise blocks prior to section classification.

---

### 2.5 Failure Mode 5: Loss of Company Across Consecutive Promotions
* **Affected Component:** `backend/app/services/resume_extractor_engine.py` (`_parse_heuristic_experience`, lines 1320–1370)
* **Root Cause Mechanism:**  
  When a candidate listed multiple roles at a single company (e.g., "Google LLC \n Senior Engineer 2022-Present \n Engineer 2020-2022"), the engine cleared the company name for role 2 because the immediate preceding line was a bullet point from role 1. The second role lost its employer and received an empty or fallback employer.
* **Resolution:**  
  Introduced an `active_company` contextual tracker in `_parse_heuristic_experience()`. If a new designation and date range are detected without an explicit company name, the active employer is inherited across all consecutive internal promotions.

---

### 2.6 Failure Mode 6: Dropped Hyperlinks and Inaccurate Binding
* **Affected Components:**
  - `backend/app/services/hyperlink_extractor.py` (lines 170–250)
  - `backend/app/services/resume_extractor_engine.py` (lines 210–235)
* **Root Cause Mechanism:**  
  Hyperlinks in PDF documents were either ignored or extracted only as raw URLs. Link annotations with custom visible anchor text (e.g., "Live Demo" pointing to `https://demo.app`) lost their anchor text. Extracted project repositories were dumped into generic `custom_links` rather than being bound to the enclosing project entity.
* **Resolution:**  
  1. Extracted embedded PDF link annotations using `page.get_links()`, intersecting spatial bounding boxes with page words to capture visible anchor text.
  2. Implemented block-level entity association: links occurring inside project bounding boxes or matching project name slugs are bound directly to `project.link`, `project.repo_url`, or `project.demo_url`.

---

### 2.7 Failure Mode 7: Concatenated Technology Strings
* **Affected Components:**
  - `backend/app/services/project_normalizer.py` (lines 40–125)
  - `backend/app/services/resume_extractor_engine.py` (lines 1540–1580)
* **Root Cause Mechanism:**  
  Resumes with dense slash-separated, newline-separated, or bullet-separated tech strings (e.g., `Python/FastAPI/PostgreSQL/Docker/Kubernetes`) were treated as a single token because split patterns only checked standard commas.
* **Resolution:**  
  Upgraded `normalize_technologies_list()` to split across `[,;|•·/\n]`, match known technical dictionary keywords (60+ curated terms), and preserve distinct tokens.

---

### 2.8 Failure Mode 8: Unicode Ligature and Character Corruption
* **Affected Component:** `backend/app/services/project_normalizer.py` and `resume_extractor_engine.py`
* **Root Cause Mechanism:**  
  Professional typesetting software (LaTeX, InDesign, Word) encodes typographic ligatures (`ﬁ`, `ﬂ`, `ﬃ`, `ﬄ`), curly quotes (`“`, `”`, `’`), and em-dashes (`—`). Raw text extraction without Unicode normalization corrupted search keywords (e.g., "ﬁle" failed regex searches for "file").
* **Resolution:**  
  Applied `unicodedata.normalize("NFKD", text)` across all extraction entry points, decomposing ligatures into standard ASCII characters while preserving accented multilingual text.

---

## 3. Summary of Code Changes

| Component | File Path | Nature of Fix |
|---|---|---|
| Universal Extractor Engine | `backend/app/services/resume_extractor_engine.py` | Dynamic gutter sweep, running header suppression, multi-job company tracking, zero-hallucination normalization. |
| Hyperlink Extractor | `backend/app/services/hyperlink_extractor.py` | Spatial visible label recovery, block-level entity association, slug and bullet matching. |
| Project Normalizer | `backend/app/services/project_normalizer.py` | NFKD ligature normalization, removal of invented bullets, dense tech string tokenization. |
| Resume Center Router | `backend/app/api/routers/resume_center.py` | Elimination of placeholder strings in `convert_to_template_payload` and `sync_extraction_to_database`. |
| Legacy Upload Router | `backend/app/api/routers/resume.py` | Route unification, returning `resume_id` and `active_resume_id`. |
| Agent Orchestrator | `backend/app/services/orchestrator.py` | Delegation to layout-aware engine, bidirectional synchronization with modern Resume Center tables. |
| Repair CLI Utility | `backend/scripts/repair_existing_resumes.py` | Safe dry-run repair script with JSON backup snapshots. |
| Ground Truth Corpus | `backend/tests/test_ground_truth_corpus.py` | 12 rigorous synthetic fixtures validating all layout styles. |

---

## 4. Verification & Status

All unit tests and integration suites pass with 100% success rate:
- `test_ground_truth_corpus.py`: 12/12 passed.
- `test_universal_resume_extractor.py`: 6/6 passed.
- `test_project_bullet_deduplication.py`: 8/8 passed.
- `test_resume_project_deduplication.py`: 8/8 passed.
- `test_resume_center.py`: 10/10 passed.
- Frontend Next.js build: 35/35 routes compiled with zero TypeScript errors.
