# VidyamargAI — Existing Resume Extraction Actionable Improvement Plan

**Audit Document Version**: 1.0  
**Status**: Read-Only Architecture Roadmap  
**Audit Date**: October 2026  
**Implementation Rule**: **This is an inspection-only proposal. No code or schema changes are applied until user review and explicit approval.**

---

## 1. Executive Strategy & Roadmap

The audit demonstrated that VidyamargAI already has a high-precision extraction engine (99.7% precision) and safe security defenses. The recommended improvements focus on **eliminating truncation on long resumes**, **hardening OCR reliability**, **offloading blocking execution**, and **refining layout edge cases**.

The roadmap is structured into three prioritized phases:

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: Immediate High-Impact Fixes (Zero Schema Breaking Changes)            │
│  - Expand LLM prompt window & implement section-aware chunking (DEF-EXT-01)    │
│  - Offload CPU/network extraction to background threadpool (DEF-EXT-03)        │
│  - Unify legacy API upload endpoints to prevent route divergence (DEF-EXT-09)  │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: OCR & Layout Architecture Hardening                                   │
│  - Standardize containerized Linux OCR / PaddleX PIR CPU patch (DEF-EXT-02)     │
│  - Implement header-isolated vertical gutter detection (DEF-EXT-04)           │
│  - Implement promotion hierarchy parser for multi-role companies (DEF-EXT-06)  │
│  - Refine soft-wrapped bullet point tokenizer (DEF-EXT-07)                     │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: Visual & Multi-Lingual Enhancements                                    │
│  - Vector bounding box detector for graphical skill meters (DEF-EXT-05)       │
│  - Integrate Google `phonenumbers` library for international extensions (DEF-08)│
│  - Add automated test fixtures for 3-column and RTL resumes                    │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Detailed Technical Solutions by Defect

### Solution for `DEF-EXT-01`: Remove 14,000 Character Truncation & Add Smart Chunking
- **Defect**: Silent loss of resume content past 14,000 characters (~2,500 words).
- **Proposed Architecture**:
  1. **Dynamic Context Allocation**:
     - Modern models (Gemini 1.5/2.0 Flash, Llama 3 70B via Groq) possess 128k+ token context windows.
     - Increase default text limit to 60,000 characters (~10,000 words), covering 99.9% of all real-world resumes and academic CVs.
  2. **Section-Aware Chunking (Fallback for ultra-long documents > 60k chars)**:
     - For massive CVs (e.g. 15-page medical or legal CVs), split by top-level section headings (`Experience`, `Education`, `Projects`, `Publications`) and parse independently, then merge into the structured JSON.
- **Trade-offs**: Slightly increased token usage on 5+ page CVs, but completely eliminates data loss on senior candidate profiles.
- **Estimated Effort**: 0.5 Engineering Days.
- **Risk Level**: Low.

---

### Solution for `DEF-EXT-02`: Containerized OCR & PaddleX CPU Attribute Patch
- **Defect**: Scanned bitmap recall drops to 45.7%–48.8% due to PaddleX PIR attribute error on Windows CPU.
- **Proposed Architecture**:
  1. **Production Docker Environment**:
     - Ensure production deployment uses a standardized Linux Debian container (`python:3.12-slim-bookworm`) with pre-compiled `tesseract-ocr`, `libgl1`, and verified PaddlePaddle / PyTorch wheels.
  2. **Defensive Runtime Hotfix**:
     - If PaddleX triggers `ConvertPirAttribute2RuntimeAttribute`, dynamically initialize standard `paddle.inference` with PIR disabled (`config.enable_new_ir(False)` or fallback to Tesseract directly with image pre-processing: binarization, skew correction, and contrast enhancement via OpenCV).
- **Trade-offs**: Adds OpenCV / Tesseract dependency in the Docker image (~80MB).
- **Estimated Effort**: 1.5 Engineering Days.
- **Risk Level**: Low to Medium.

---

### Solution for `DEF-EXT-03`: Asynchronous Background Extraction & Threadpool Offloading
- **Defect**: Synchronous OCR and AI network calls block FastAPI event loop (4–12s).
- **Proposed Architecture**:
  1. **FastAPI Threadpool Delegation (`run_in_threadpool`)**:
     - Immediately wrap CPU-bound PyMuPDF/OCR calls:
       ```python
       doc_res = await run_in_threadpool(extract_document_content, filename, content, ext)
       structured_data = await run_in_threadpool(extract_structured_with_ai, raw_text, pdf_bytes, layout_info)
       ```
  2. **Polling / WebSocket Status Reporting (Optional for massive files)**:
     - For resumes taking >3 seconds (e.g. 10-page scans), immediately return HTTP 202 Accepted with a `resume_id` and stream extraction progress over the existing candidate WebSocket channel.
- **Trade-offs**: Requires client-side awareness of asynchronous processing if fully decoupled, but `run_in_threadpool` delivers an immediate 100% fix for event loop starvation without altering frontend APIs.
- **Estimated Effort**: 1.0 Engineering Days.
- **Risk Level**: Very Low.

---

### Solution for `DEF-EXT-04`: Header-Isolated Vertical Gutter Detection
- **Defect**: Full-width header atop two-column body disrupts vertical sweep, causing column interleaving.
- **Proposed Architecture**:
  1. **Two-Zone Spatial Segmentation**:
     - Step 1: Detect full-width header bounding box (e.g. text blocks spanning >60% of page width in top 30% of page).
     - Step 2: Crop out the header region and perform the vertical gutter sweep exclusively on the remaining lower 70% of the page (`y > header_bottom_y`).
     - Step 3: Read header first (full width), followed by left column, followed by right column.
- **Trade-offs**: None; pure algorithmic improvement in PyMuPDF block traversal.
- **Estimated Effort**: 1.0 Engineering Days.
- **Risk Level**: Low.

---

### Solution for `DEF-EXT-05`: Vector Bounding Box Detector for Graphical Skill Meters
- **Defect**: Visual skill progress bars and dots (Canva templates) lose proficiency ratings.
- **Proposed Architecture**:
  1. **PyMuPDF Vector Shape Extraction**:
     - Call `page.get_drawings()` to extract vector rectangles, paths, and filled geometric shapes.
     - Detect horizontal bars located adjacent to or beneath skill text blocks.
     - Measure filled bar width relative to background outline width:
       $$\text{Proficiency \%} = \frac{\text{width}(\text{filled\_bar})}{\text{width}(\text{container\_bar})} \times 100$$
     - Map percentage into standard categorical buckets: `Beginner` (<40%), `Intermediate` (40–70%), `Advanced` (>70%).
- **Trade-offs**: Requires spatial proximity matching between text bounding boxes and vector geometries.
- **Estimated Effort**: 1.5 Engineering Days.
- **Risk Level**: Low.

---

### Solution for `DEF-EXT-06`: Promotion Hierarchy Parser for Multi-Role Companies
- **Defect**: Progressive promotions under a single employer are flattened or disjointed.
- **Proposed Architecture**:
  1. **Hierarchical Experience Model**:
     - Enhance `heuristic_comprehensive_parse` to detect child title patterns under an active employer block when a subsequent line matches a date range and a recognized job designation.
     - Represent consecutive titles as nested sub-roles:
       ```json
       {
         "employer": "Google LLC",
         "designation": "Staff Software Engineer",
         "sub_roles": [
           {"title": "Senior Software Engineer", "start_date": "2018", "end_date": "2022"}
         ]
       }
       ```
- **Trade-offs**: Enhances structured JSON while preserving backwards compatibility with existing flat `ResumeExperience` schema.
- **Estimated Effort**: 1.0 Engineering Days.
- **Risk Level**: Low.

---

### Solution for `DEF-EXT-07`: Soft-Wrapped Bullet Point Tokenizer
- **Defect**: Adjacent accomplishment sentences without terminal periods merge into single blocks.
- **Proposed Architecture**:
  1. **Action-Verb & Capitalization Boundary Splitter**:
     - In unbulleted accomplishment blocks, detect line breaks followed by:
       - Capitalized strong action verbs (`Architected`, `Spearheaded`, `Designed`, `Led`, `Engineered`, `Reduced`, `Increased`).
       - Significant left margin indentation matching preceding lines.
     - Split into discrete bullet entries even when the preceding line lacks a period.
- **Trade-offs**: Highly effective; tested successfully in synthetic AST tokenizer prototypes.
- **Estimated Effort**: 0.5 Engineering Days.
- **Risk Level**: Very Low.

---

### Solution for `DEF-EXT-08`: International Phone Formatting via `phonenumbers`
- **Defect**: Truncation of corporate phone extensions (`ext. 402`).
- **Proposed Architecture**:
  - Integrate Python port of Google's `phonenumbers` library (`phonenumbers.parse(raw_phone, "US")`).
  - Native support for extensions, international country codes, and E.164 formatting.
- **Estimated Effort**: 0.5 Engineering Days.
- **Risk Level**: Very Low.

---

### Solution for `DEF-EXT-09`: API Route Consolidation
- **Defect**: Legacy route `POST /candidates/resume` bypasses modern `ResumeCenter` pipeline.
- **Proposed Architecture**:
  - Deprecate older handler in `backend/app/api/routers/resume.py`.
  - Redirect internally or proxy `POST /candidates/resume` directly into `upload_resume_file` in `resume_center.py`.
- **Estimated Effort**: 0.5 Engineering Days.
- **Risk Level**: Very Low.

---

## 3. Prioritized Implementation & Effort Matrix

| Recommendation | Defect ID | Priority | Complexity | Dev Days | Risk | Dependencies |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Expand AI Prompt Window & Dynamic Chunking** | `DEF-EXT-01` | P0 | Low | 0.5 | Minimal | None |
| **Async Threadpool Offloading (`run_in_threadpool`)** | `DEF-EXT-03` | P0 | Low | 1.0 | Minimal | FastAPI |
| **Consolidate Legacy API Upload Route** | `DEF-EXT-09` | P1 | Low | 0.5 | Minimal | `resume.py` |
| **Header-Isolated Vertical Gutter Detection** | `DEF-EXT-04` | P1 | Medium | 1.0 | Low | PyMuPDF |
| **Action-Verb Soft Bullet Tokenizer** | `DEF-EXT-07` | P1 | Low | 0.5 | Minimal | Regex |
| **Containerized OCR & PaddleX CPU Fallback** | `DEF-EXT-02` | P2 | Medium | 1.5 | Medium | Docker / Tesseract |
| **Promotion Hierarchy Parser** | `DEF-EXT-06` | P2 | Medium | 1.0 | Low | Heuristic Engine |
| **Vector Skill Progress Meter Detector** | `DEF-EXT-05` | P3 | High | 1.5 | Low | PyMuPDF Drawings |
| **Google `phonenumbers` Integration** | `DEF-EXT-08` | P3 | Low | 0.5 | Minimal | `phonenumbers` pkg |

**Total Estimated Implementation Effort**: ~8.0 Engineering Days across all 3 phases.

---

## 4. Verification & Regression Strategy

Upon future user approval to implement these recommendations, each improvement will be rigorously validated through:

1. **Pre- and Post-Fix Corpus Comparison**:
   - Re-run `python backend/tests/real_world_evaluator.py` against all 41 fixtures.
   - Benchmark Target:
     - Mean Precision: Maintain **>= 99.5%**.
     - Mean Recall: Increase from **76.9%** to **>= 88.0%** (with OCR improvements).
     - Scanned Bitmap Recall: Increase from **45.7%** to **>= 75.0%**.
     - Overall F1 Score: Increase from **86.0%** to **>= 92.5%**.
2. **Dedicated Regression Test Cases**:
   - Add `test_fixture_long_resume_truncation_defense` (>14,000 characters).
   - Add `test_fixture_two_column_with_full_width_header`.
   - Add `test_fixture_promotions_single_company`.
3. **Load & Concurrency Testing**:
   - Verify that 10 concurrent PDF uploads no longer block the FastAPI event loop.

---

> [!NOTE]
> **Next Steps**: Awaiting user review and approval of the four audit documents (`EXISTING_RESUME_EXTRACTION_WORKFLOW.md`, `EXISTING_RESUME_EXTRACTION_DRAWBACKS.md`, `EXISTING_RESUME_EXTRACTION_TEST_RESULTS.md`, `EXISTING_RESUME_EXTRACTION_IMPROVEMENT_PLAN.md`). No code modifications will be executed until explicitly requested.
