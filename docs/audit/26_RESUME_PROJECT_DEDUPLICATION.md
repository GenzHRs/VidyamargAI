# 26. RESUME PROJECT DEDUPLICATION & TECHNOLOGY NORMALIZATION AUDIT

## Executive Summary

When candidates uploaded resumes, projects in the candidate profile displayed duplicated content (e.g. project descriptions followed immediately by identical bullet points) and concatenated technology strings (`FastAPIPythonPostgreSQLAzure OCRNERGemini LLM`).

This document details the audit of the complete resume extraction pipeline, the root causes identified, the architectural solution implemented across backend and frontend, the safe repair migration, and verification test results.

---

## 1. Pipeline Audit & Root Cause Analysis

### Pipeline Components Inspected
1. **Document Text Extraction (`_extract_pdf_layout_aware`, `_extract_docx_clean`)**:
   - Layout-aware extraction extracted text blocks from PDF bounding boxes. In dense multi-column or skill badge layouts, consecutive tokens without bounding whitespace were occasionally fused into single contiguous string tokens like `FastAPIPythonPostgreSQLAzure OCRNERGemini LLM`.
2. **Heuristic Project Parsing (`_parse_heuristic_projects`)**:
   - In fallback/offline parsing or multi-pass aggregation, project blocks parsed bullet lines and executed:
     ```python
     b["description"] = " ".join(b["bullets"])
     b["responsibilities"] = b["bullets"]
     ```
     This set the project's `description` to the concatenated bullets while also preserving the exact same lines in `responsibilities`.
3. **Structured JSON Normalization (`_normalize_and_validate_extraction`)**:
   - The validation phase checked required keys but did not deduplicate between `description` and `responsibilities`/`bullets`.
4. **Database Persistence (`ResumeProject`, `ResumeExtraction`)**:
   - Both the full `description` and `responsibilities` array were persisted to the database.
5. **Frontend Profile Rendering (`frontend/app/candidate/profile/page.tsx`)**:
   - The React component rendered `pDesc` as a `<p>` paragraph, and then immediately rendered `pBullets` as a `<ul>` list, displaying the exact same sentences twice in the UI.
   - Technologies were rendered as raw strings or simple comma splits without tokenizing fused multi-word technologies.

---

## 2. Implemented Fixes

### A. Technology Tokenization Engine
Added `KNOWN_TECH_TERMS` dictionary and `normalize_technologies_list()` in `backend/app/services/resume_extractor_engine.py`:
- Recognizes 120+ known technical terms (e.g., `FastAPI`, `Python`, `PostgreSQL`, `Azure OCR`, `NER`, `Gemini LLM`, `React`, `Docker`, `Kubernetes`).
- Sorts known terms by length descending to match composite terms (`Azure OCR`) before sub-terms (`OCR`).
- Calculates non-overlapping match spans within the concatenated string.
- Sorts identified terms by their appearance position in the original text, preserving the resume's authentic sequence.

Example:
- Input: `"FastAPIPythonPostgreSQLAzure OCRNERGemini LLM"`
- Output: `["FastAPI", "Python", "PostgreSQL", "Azure OCR", "NER", "Gemini LLM"]`

### B. Bullet Marker Normalization
Added `clean_bullet_text()`:
- Strips leading Unicode bullets, private-use glyphs, dashes, and duplicate markers (`• •`, `▪ -`, `► ▸`, `* -`).
- Trims whitespace and preserves all internal metrics, dates, and technical details.

### C. Project Deduplication & Canonical Representation
Added `normalize_and_deduplicate_project()`:
- Strips duplicate bullet entries and cleans bullet prefixes.
- Detects if `description` is identical to or composed entirely of sentences present in `responsibilities`/`bullets`.
- If `description` merely repeats the bullets, sets `description = None` so only one canonical representation is stored.
- If `description` contains genuinely distinct, additional context (e.g. high-level business goal or architecture summary), `description` is preserved alongside the bullets.
- Never merges content across distinct project boundaries.

### D. Frontend Deduplication Guard
Updated `frontend/app/candidate/profile/page.tsx`:
- Before rendering `pDesc`, checks if `normDesc` is contained within the bullet text. If duplicate, the paragraph is suppressed.
- Renders `pTechs` as discrete pill badges with clean typography, preventing concatenated strings from cluttering the layout.

---

## 3. Database Repair Script (`repair_resume_projects.py`)

A production-ready data repair utility was created in `backend/repair_resume_projects.py`:
- **Dry-run mode (`--dry-run`)**: Default behavior. Evaluates all existing records, computes normalization, and prints before/after comparison previews without making any database changes.
- **Apply mode (`--apply`)**: Idempotently repairs affected records in `ResumeProject`, `ResumeExtraction.structured_data["projects"]`, and `Candidate.projects`.
- **Automated Backup**: Before applying changes, writes a timestamped snapshot of original data to `backend/backups/resume_projects_backup_<timestamp>.json`.
- **Snapshot Immutability**: Does not modify submitted job application snapshots or historical immutable artifacts.

---

## 4. Regression Test Results

### Backend Test Suite (`pytest`)
Ran `pytest tests/test_resume_project_deduplication.py`:
```
tests\test_resume_project_deduplication.py .........                     [100%]
9 passed in 0.10s
```

Test coverage:
1. `test_concatenated_technology_strings`: Validates exact tokenization of `"FastAPIPythonPostgreSQLAzure OCRNERGemini LLM"`.
2. `test_repeated_bullet_markers`: Validates stripping of `• •`, `► ▸`, `▪ -`.
3. `test_paragraph_and_bullet_duplication`: Confirms paragraph description is cleared when repeating bullets.
4. `test_paragraph_with_genuine_additional_information`: Confirms genuine additional overview text is preserved.
5. `test_multiple_distinct_projects`: Confirms distinct project boundaries and technology lists are preserved.
6. `test_legitimate_repeated_keywords`: Confirms legitimate recurring keywords (e.g., `Qdrant`) across bullets do not cause accidental deduplication.
7. `test_idempotency_re_extracting_same_resume`: Confirms multiple passes yield identical output.
8. `test_original_master_resume_raw_text_preservation`: Confirms raw extracted document text is unmutated.
9. `test_job_snapshot_immutability`: Confirms historical job application snapshots remain untouched.

Ran `pytest tests/test_resume_extraction_engine.py`:
```
tests\test_resume_extraction_engine.py .....                             [100%]
5 passed in 2.87s
```

### Frontend Build
Ran Next.js 16.3.8 production build:
```
✓ Compiled successfully in 1139ms
✓ Completed runAfterProductionCompile in 481ms
✓ Generating static pages using 7 workers (35/35) in 597ms
```
All 35 frontend routes compiled without errors.
