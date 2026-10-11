# VidyamargAI — Existing Resume Extraction Drawback and Limitation Catalog

**Audit Document Version**: 1.0  
**Status**: Read-Only Defect & Limitation Audit  
**Audit Date**: October 2026  
**Audited Files**: `resume_extractor_engine.py`, `resume_center.py`, `resume_context_service.py`, `hyperlink_extractor.py`, `project_normalizer.py`, `ats_optimizer.py`

---

## 1. Executive Summary of Limitations

The VidyamargAI extraction engine achieves a high overall precision (99.7%) on standard single- and two-column chronological resumes. However, the architecture exhibits distinct systemic limitations, performance bottlenecks, and edge-case vulnerabilities:

1. **Information Loss on Extended Resumes**: A hardcoded 14,000-character truncation boundary in the AI extraction prompt silently drops late-document content on multi-page resumes (3+ pages).
2. **Platform-Dependent OCR Degradation**: The Windows CPU runtime exhibits a known PaddleX PIR attribute limitation, causing scanned document recall to drop from >80% to 45.7%–48.8%.
3. **Synchronous In-Request Processing**: Heavy PDF layout parsing, OCR processing, and external LLM network round-trips run synchronously in the FastAPI route thread, causing high request latency and serverless timeout risks.
4. **Layout & Typographic Edge Cases**: Visual progress bars (vector graphics in Canva templates), promotion hierarchies within a single employer, and unpunctuated soft-wrapped bullets experience information loss or flattening.
5. **Architectural Route Duplication**: Two parallel resume upload routes exist in the API layer with divergent behaviors.

---

## 2. Comprehensive Defect & Limitation Catalog

| ID | Severity | Category | Subsystem / Location | Impact Summary |
| :--- | :--- | :--- | :--- | :--- |
| `DEF-EXT-01` | **CRITICAL** | Content Loss | `resume_extractor_engine.py` (Line 1104) | Silent truncation of resume text beyond 14,000 characters (~2,500 words). Dropping certifications, publications, and projects on long CVs. |
| `DEF-EXT-02` | **CRITICAL** | OCR Reliability | `resume_extractor_engine.py` (Lines 445–470) | PaddleOCR Windows CPU runtime error on bitmap scans, resulting in degraded recall (45.7%–48.8%). |
| `DEF-EXT-03` | **HIGH** | Latency & Blocking | `resume_center.py` (Lines 849–860) | Synchronous execution of OCR and AI calls blocks the server worker thread and risks HTTP 504 timeouts. |
| `DEF-EXT-04` | **HIGH** | Layout Classification | `resume_extractor_engine.py` (Lines 350–420) | Full-width headers atop two-column bodies can confuse horizontal gutter sweep, causing column interleaving. |
| `DEF-EXT-05` | **MEDIUM** | Visual Extraction | `resume_extractor_engine.py` (Lines 330–345) | Graphical/vector skill progress bars and dots (Canva templates) lose proficiency ratings; only text labels are retained. |
| `DEF-EXT-06` | **MEDIUM** | Hierarchy Loss | `resume_extractor_engine.py` (Lines 1350–1420) | Multi-job single-employer promotions are flattened into a single entry or split into disconnected entries. |
| `DEF-EXT-07` | **MEDIUM** | Bullet Splitting | `resume_extractor_engine.py` (Lines 1450–1510) | Soft line-wrapped bullet points without terminal periods merge adjacent sentences into bloated bullet blocks. |
| `DEF-EXT-08` | **LOW** | Normalization | `resume_extractor_engine.py` (Lines 1940–1970) | Non-standard international phone extensions (e.g. `ext. 402`) are occasionally truncated. |
| `DEF-EXT-09` | **LOW** | API Architecture | `resume.py` (Line 53) vs `resume_center.py` (Line 802) | Legacy route divergence: `POST /candidates/resume` vs `POST /resumes/upload`. |

---

## 3. Detailed Defect Analysis

### `DEF-EXT-01`: 14,000 Character Truncation in AI Prompt
- **Severity**: **CRITICAL**
- **Affected File**: `VidyamargAI/backend/app/services/resume_extractor_engine.py`
- **Affected Lines**: Line 1104
  ```python
  prompt = f"{EXTRACTION_SYSTEM_PROMPT}\n\nRESUME TEXT TO EXTRACT:\n{raw_text[:14000]}"
  ```
- **Root Cause**:
  The developer inserted a defensive string slice `raw_text[:14000]` to avoid token limit overflow on smaller context LLMs. However:
  - 14,000 characters is approximately 2,200–2,500 words.
  - Comprehensive academic CVs, executive resumes, or senior engineering portfolios (3 to 5 pages) frequently reach 18,000 to 30,000 characters.
  - Modern LLMs (Gemini 1.5/2.0, Llama 3) support 128k to 1M token contexts, making this restriction unnecessary.
- **Reproduction Conditions**:
  Upload any resume exceeding 14,000 characters (e.g. a 4-page technical CV with comprehensive project listings or academic publications).
- **Impact**:
  - All content past character 14,000 is completely invisible to the AI parser.
  - While the heuristic multi-pass fallback attempts to salvage missing projects, any custom sections, certifications, patents, or publications on later pages are permanently lost from the AI structured output.
- **Risk Level**: High risk of candidate data omission and reduced ATS match scores for senior candidates.

---

### `DEF-EXT-02`: PaddleOCR Windows CPU Double-Attribute pir Limitation
- **Severity**: **CRITICAL**
- **Affected File**: `VidyamargAI/backend/app/services/resume_extractor_engine.py`
- **Affected Lines**: Lines 445–470 (`_attempt_ocr_on_page`)
- **Root Cause**:
  Under Windows with Python 3.12 and PaddleX v3, running inference on CPU triggers:
  ```
  NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support [pir::ArrayAttribute<pir::DoubleAttribute>]
  ```
  While the engine catches the exception and falls back to PyMuPDF's built-in OCR textpage or image metadata, PyMuPDF OCR without local Tesseract language packs produces lower character accuracy on low-contrast scans.
- **Empirical Benchmark Evidence**:
  In our real-world evaluation of all 41 corpus fixtures:
  - Selectable PDFs achieved **0.783** mean recall and **0.872** F1.
  - Scanned PDF (`rw_02`) achieved only **0.488** recall and **0.656** F1.
  - Image scans (`rw_12_image_png`, `rw_13_image_jpg`, `rw_14_image_tiff`) achieved only **0.457** recall and **0.627** F1.
- **Impact**:
  Candidates uploading mobile photos of resumes or scanned PDFs receive incomplete extractions where only headers and high-contrast lines are recognized, omitting fine body text.
- **Risk Level**: High risk for users who upload photos or scanned physical resumes.

---

### `DEF-EXT-03`: Synchronous In-Request Processing Locks FastAPI Event Loop
- **Severity**: **HIGH**
- **Affected File**: `VidyamargAI/backend/app/api/routers/resume_center.py`
- **Affected Lines**: Lines 848–862 (`upload_resume_file`)
  ```python
  # 4. Multi-column, layout-aware document extraction (SYNCHRONOUS CPU BOUND)
  doc_res = extract_document_content(filename, content, ext)
  
  # 5. Comprehensive structured extraction (SYNCHRONOUS NETWORK BOUND AI CALL)
  structured_data = extract_structured_with_ai(raw_text, pdf_bytes, layout_info)
  ```
- **Root Cause**:
  `extract_document_content` (PyMuPDF geometry analysis and OCR) is CPU-bound. `extract_structured_with_ai` (Gemini / NVIDIA / Groq HTTP requests with retry backoff) is network-bound. Both run synchronously inside the `async def upload_resume_file` route without delegation to a threadpool (`run_in_threadpool`) or Celery/Redis background worker.
- **Impact**:
  - Uploading a multi-page PDF or image scan blocks the FastAPI worker thread for 4 to 12 seconds.
  - Under concurrent user traffic, this starves the asyncio event loop.
  - On platforms with tight reverse-proxy timeouts (e.g. Vercel 10s limit, Cloudflare 15s limit), slow OCR or AI latency triggers HTTP 504 Gateway Timeout errors.
- **Risk Level**: High scalability and reliability risk under production load.

---

### `DEF-EXT-04`: Dual-Column Gutter Ambiguity with Asymmetric Headers
- **Severity**: **HIGH**
- **Affected File**: `VidyamargAI/backend/app/services/resume_extractor_engine.py`
- **Affected Lines**: Lines 350–420 (`_extract_pdf_layout_aware`)
- **Root Cause**:
  The multi-column classifier searches for an unbroken vertical corridor across the entire page height. In modern resume designs:
  - The top 25% of the page has a wide banner (Candidate Name, Title, Contact Info spanning from x=50 to x=550).
  - The remaining 75% of the page is split into a narrow left sidebar (30% width) and a main content column (70% width).
  - Because the top banner blocks intersect the vertical sweep corridor, naive full-height gutter detection can fail to detect the two-column split below the banner, causing the engine to revert to standard top-to-bottom reading order.
- **Impact**:
  Horizontal lines across the left sidebar and main body interleave, mixing technical skills into job responsibilities (e.g. `"Led distributed microservices | Docker, Kubernetes | reduced latency by 30%"`).
- **Risk Level**: High data quality risk for two-column templates with full-width headers.

---

### `DEF-EXT-05`: Graphical / Vector Skill Rating Bars Dropped
- **Severity**: **MEDIUM**
- **Affected File**: `VidyamargAI/backend/app/services/resume_extractor_engine.py`
- **Affected Lines**: Lines 330–345 & Fixture `rw_29`
- **Root Cause**:
  Canva, Novoresume, and Figma resume templates frequently render skill proficiency as graphical vector meters (e.g., filled rectangles `fitz.Rect` or 5 colored stars/circles). PyMuPDF text extraction extracts character glyphs, not drawing vectors (`draw_rect`, `draw_circle`).
- **Impact**:
  The parser extracts the skill name (`"Python"`, `"AWS"`), but completely drops the rating or proficiency level (`"Advanced"`, `"90%"`). While skill keywords are preserved for ATS matching, candidate proficiency tiering is lost.
- **Risk Level**: Moderate impact on candidate profiling.

---

### `DEF-EXT-06`: Multi-Role Single-Employer Promotion Flattening
- **Severity**: **MEDIUM**
- **Affected File**: `VidyamargAI/backend/app/services/resume_extractor_engine.py`
- **Affected Lines**: Lines 1350–1420 (`heuristic_comprehensive_parse`)
- **Root Cause**:
  When a candidate has multiple titles at the same employer:
  ```
  Google LLC — 2018 to Present
  Staff Software Engineer (2022 – Present)
  • Led technical architecture...
  Senior Software Engineer (2018 – 2022)
  • Developed data pipelines...
  ```
  The heuristic parser segments sections on employer boundary changes. Because the employer name is not repeated before the second title, the parser either:
  1. Merges both roles into a single experience entry under the most recent title, flattening the promotion timeline.
  2. Or treats the second title as an unattached bullet point under the first role.
- **Impact**:
  Career velocity, progressive seniority, and internal promotions are obscured.
- **Risk Level**: Moderate impact on senior engineering and executive profiles.

---

### `DEF-EXT-07`: Soft Line-Wrapped Bullet Boundary Merging
- **Severity**: **MEDIUM**
- **Affected File**: `VidyamargAI/backend/app/services/resume_extractor_engine.py`
- **Affected Lines**: Lines 1450–1510 (`heuristic_comprehensive_parse`)
- **Root Cause**:
  In resumes lacking explicit bullet characters (`•`, `-`, `*`), the heuristic parser attempts to segment bullets on sentence boundaries (`.\n` or double newlines). If a candidate writes wrapped accomplishment statements without a period at the end of each item, the boundary detector fails to split them.
- **Impact**:
  Multiple distinct accomplishments collapse into a single monolithic paragraph block, reducing readability in the candidate resume editor and confusing the ATS optimizer.
- **Risk Level**: Moderate UI and formatting impact.

---

### `DEF-EXT-08`: Non-Standard Phone Number Extension Truncation
- **Severity**: **LOW**
- **Affected File**: `VidyamargAI/backend/app/services/resume_extractor_engine.py`
- **Affected Lines**: Lines 1940–1970 (`_normalize_and_validate_extraction`)
- **Root Cause**:
  The phone regex cleans non-numeric characters aggressively:
  ```python
  cleaned_phone = re.sub(r"[^\d+ext\s-]", "", raw_phone)
  ```
  Numbers formatted with corporate extensions like `+1 (555) 019-2834 x402` or `ext. 102` occasionally have the extension stripped or placed into `additional_phones` as a fragmented number.
- **Impact**:
  Recruiters attempting to call a corporate extension may miss the extension number.
- **Risk Level**: Low impact, as primary mobile numbers rarely contain extensions.

---

### `DEF-EXT-09`: API Route Divergence (`/candidates/resume` vs `/resumes/upload`)
- **Severity**: **LOW**
- **Affected File**:
  - `backend/app/api/routers/resume.py` (Line 53: `@router.post("/candidates/resume")`)
  - `backend/app/api/routers/resume_center.py` (Line 802: `@router.post("/resumes/upload")`)
- **Root Cause**:
  The codebase maintains two separate resume upload endpoints:
  1. `/candidates/resume` (in `resume.py`): Calls `orchestrator.run_resume_collection_agent`, which historically applied older parsing logic and rate-limits to 3 uploads per hour.
  2. `/resumes/upload` (in `resume_center.py`): Calls `resume_extractor_engine.py`, performs SHA-256 fingerprinting, layout analysis, multi-pass AI/heuristic extraction, and atomic active resume replacement via `ResumeContextService`.
- **Impact**:
  If a legacy frontend component or mobile client invokes `/candidates/resume`, it bypasses the modern `ResumeCenter` extraction, versioning, and companion table sync.
- **Risk Level**: Low to moderate technical debt.
