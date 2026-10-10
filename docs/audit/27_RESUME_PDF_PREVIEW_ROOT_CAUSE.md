# VIDYAMARG AI — RESUME PDF PREVIEW & COMPILATION ROOT-CAUSE AUDIT & PERMANENT FIX

**Document Reference**: `docs/audit/27_RESUME_PDF_PREVIEW_ROOT_CAUSE.md`  
**Date**: October 10, 2026  
**Auditor**: Senior Next.js 16, React 19, FastAPI, PDF Rendering & Document Generation Engineer  
**Status**: RESOLVED & VERIFIED

---

## 1. Executive Summary & Root Cause Analysis

### The Problem
On the candidate resume editor (`/candidate/resumes/edit/2`), the PDF Preview panel remained stuck on:
> *"Resume Not Yet Compiled — Click the Compile PDF button above to render this resume into an Overleaf-grade PDF document."*

When clicking **Compile PDF** or **Compile Now**, the preview panel was blank or remained uncompiled instead of rendering the resume document.

### Root Cause Breakdown (End-to-End Pipeline Trace)

#### Root Cause 1: Standalone PDF Fallback Crash on Heterogeneous Data
1. In cloud container environments (Railway, Docker, Vercel, serverless runtimes) and developer environments where TeX Live is not installed (a 4GB+ installation that is typically absent), `is_latex_installed()` returns `False`.
2. When `is_latex_installed()` was `False`, the backend was designed to execute `render_structured_data_to_pdf(version.structured_data, ...)` in `backend/app/services/latex_service.py` to generate an ATS-grade vector PDF.
3. However, `render_structured_data_to_pdf` crashed with:
   ```python
   TypeError: sequence item 0: expected str instance, dict found
   ```
   **Why?** Resumes extracted via LLMs, heuristic parsers, or user edits often store skills and experience bullets as complex objects (e.g., `[{"name": "Python"}, {"name": "FastAPI"}]` or `[{"text": "bullet description"}]`) rather than pure string primitives. When calling `", ".join(items)` or ReportLab flowable builders, Python raised an unhandled `TypeError`.
4. As a result of this crash, `compile_resume` caught the exception and returned:
   ```json
   {
     "status": "warning",
     "latex_available": false,
     "message": "LaTeX engine (pdflatex) is not installed on this server. Your Overleaf-compatible .tex source has been generated and saved for download.",
     "latest_tex_url": "...",
     "latex_source": "..."
   }
   ```
   Crucially, **no `latest_pdf_url` was returned**, and **no PDF bytes were saved**.

#### Root Cause 2: Frontend Gating Preview on `result.latex_available`
In `frontend/app/candidate/resumes/edit/[resumeId]/page.tsx`, `handleCompile` had the following control flow:
```typescript
const result = await resumeCenterApi.compileResume(resumeId);
if (result.latex_available) {
  const blob = await resumeCenterApi.downloadPdfBlob(resumeId);
  ...
} else {
  setPreviewMode("latex");
  setSuccessMessage("LaTeX source compiled! Ready for Overleaf export.");
}
```
Because `result.latex_available` was `false` (pdflatex not on host), the frontend forced `setPreviewMode("latex")` and **never initiated `downloadPdfBlob`**.
Furthermore, if the user toggled back to "PDF Preview", `pdfBlobUrl` remained `null`, which triggered the default JSX branch:
```tsx
{previewMode === "pdf" ? (
  pdfBlobUrl ? (
    <iframe src={pdfBlobUrl} ... />
  ) : (
    <ResumeNotYetCompiled ... />
  )
)}
```
leaving the candidate permanently stuck seeing "Resume Not Yet Compiled".

#### Root Cause 3: Content-Disposition & Preview Headers
The backend endpoint `GET /resumes/{resume_id}/download/pdf` unconditionally sent `Content-Disposition: attachment`. In browser embedded contexts (`<iframe>`, `<object>`), `Content-Disposition: inline` is required so browsers render the document stream directly in the viewport.

---

## 2. Architecture & Pipeline Solution

```
┌────────────────────────────────────────────────────────────────────────┐
│ Candidate Clicks "Compile PDF" or "Compile Now" in Editor              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 1. Auto-saves structured inputs
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ POST /api/v1/resumes/{id}/compile                                      │
├────────────────────────────────────────────────────────────────────────┤
│ • Validates candidate identity & resume ownership (403 if unauthorized)│
│ • Consolidates structured resume data if version is partially empty    │
│ • Generates Overleaf-compatible .tex artifact                          │
│ • Compilation Decision:                                                │
│   ├── If pdflatex installed -> compile_latex_to_pdf(latex_source)      │
│   └── If pdflatex not installed OR fails -> render_structured_data_to_pdf
│       (Guaranteed sanitization of all heterogeneous dict/list fields)  │
│ • Validates %PDF magic bytes & size > 100 bytes                        │
│ • Stores PDF privately in user-isolated storage                        │
│ • Returns: status="success", pdf_available=true, latest_pdf_url="..."  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ 2. Receives status="success" & URL
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Frontend Fetches PDF Preview Blob                                      │
├────────────────────────────────────────────────────────────────────────┤
│ • GET /api/v1/resumes/{id}/preview/pdf                                 │
│ • Serves binary %PDF with Content-Disposition: inline                  │
│ • Client wraps stream into strict new Blob([buffer], { application/pdf})│
│ • URL.createObjectURL(blob) created & tracked                          │
│ • Renders inside <object> with fallback <iframe>                       │
│ • Smooth loading spinner overlay during compilation                    │
│ • Auto-revokes obsolete object URLs on recompile or unmount            │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Files Changed & Implementation Details

### 1. `backend/app/services/latex_service.py`
- Implemented robust recursive normalization helpers:
  - `_to_clean_str(val)`: Safely extracts string representations whether `val` is a `str`, `dict` (`name`, `title`, `label`, `text`, `value`), `list`, or number.
  - `_to_clean_bullets(bullets)`: Coerces bullet points whether given as string list, dict list (`{"text": ...}`), or nested structures.
- Added comprehensive data normalization for Personal Info, Summary, Skills (dict categories, flat lists, dict items), Experience, Projects, Education, and Certifications.
- Ensured `render_structured_data_to_pdf` generates valid `%PDF-` document bytes with clean typography and ATS formatting without external LaTeX binary dependencies.

### 2. `backend/app/api/routers/resume_center.py`
- **`compile_resume`**:
  - Enforces authenticated candidate ownership via `_verify_resume_ownership`.
  - Added fallback data consolidation via `_get_consolidated_resume_data` if structured data is not yet saved on the version.
  - Automatically falls back to high-fidelity ReportLab engine if `pdflatex` is not installed or if `pdflatex` fails with package errors.
  - Validates output bytes (`pdf_bytes.startswith(b"%PDF-")` and length > 100 bytes) before marking status `COMPILED`.
  - Returns `{"status": "success", "pdf_available": True, "compiler": compiler_used, "latest_pdf_url": ...}`.
- **`download_resume_pdf`**:
  - Added `preview: bool = Query(False)` query param.
  - When `preview=True`, returns `Content-Disposition: inline`.
  - When `preview=False`, returns `Content-Disposition: attachment; filename="{safe_name}.pdf"`.
  - Added on-the-fly compilation fallback if storage file is missing.
- **`preview_resume_pdf`** (`GET /resumes/{id}/preview/pdf`):
  - Dedicated endpoint for inline preview rendering.

### 3. `frontend/services/resumeCenterApi.ts`
- Updated `compileResume` return contract to include `pdf_available?: boolean`, `compiler?: string`, and `pdf_size_bytes?: number`.
- Enhanced `downloadPdfBlob(resumeId, isPreview = false)`:
  - When `isPreview = true`, hits the `/preview/pdf` endpoint.
  - Reads `await res.arrayBuffer()` and constructs `new Blob([buffer], { type: "application/pdf" })`. This guarantees the browser PDF renderer receives a strictly typed `application/pdf` Blob.

### 4. `frontend/app/candidate/resumes/edit/[resumeId]/page.tsx`
- **`handleCompile`**:
  - Automatically invokes `handleSave(false)` first to persist unsaved edits.
  - Inspects `result.status === "success" || result.latest_pdf_url || result.pdf_available`.
  - Downloads the PDF preview blob and updates `pdfBlobUrl`.
  - Automatically switches `setPreviewMode("pdf")`.
  - Revokes any previous object URL via `URL.revokeObjectURL`.
- **Preview Panel UX**:
  - Embedded viewer using `<object data={`${pdfBlobUrl}#toolbar=1&view=FitH`} type="application/pdf">` with `<iframe ... />` fallback.
  - Added "Pop-out" button (`window.open(pdfBlobUrl, "_blank")`) for full-tab examination.
  - Added animated compilation overlay (`Compiling Resume PDF...`) so user gets instant visual progress.
  - Added actionable Error state with a "Retry Compilation" button if invalid data is encountered.
  - Both "Compile PDF" (top bar) and "Compile Now" (preview placeholder) call canonical `handleCompile`.

---

## 4. Verification & Test Results

### Automated Backend Tests
A dedicated comprehensive test suite was created in `backend/tests/test_resume_compilation.py`:

```
backend/tests/test_resume_compilation.py::test_standalone_pdf_renderer_heterogeneous_data PASSED
backend/tests/test_resume_compilation.py::test_compile_resume_success_and_preview_headers PASSED
backend/tests/test_resume_compilation.py::test_compile_and_preview_ownership_isolation PASSED
backend/tests/test_resume_compilation.py::test_invalid_resume_id_returns_404 PASSED
backend/tests/test_resume_compilation.py::test_on_the_fly_preview_for_uncompiled_resume PASSED
backend/tests/test_resume_compilation.py::test_recompilation_after_edits PASSED
backend/tests/test_resume_compilation.py::test_concurrent_compilation_safety PASSED
```

**Full Combined Resume Suite Test Run**:
```
collected 17 items
backend/tests/test_resume_center.py ..........                           [ 58%]
backend/tests/test_resume_compilation.py .......                         [100%]
====================== 17 passed, 431 warnings in 32.89s ======================
```

### TypeScript Validation
```
node node_modules/typescript/bin/tsc --noEmit
Exit code: 0 (Zero errors)
```

### Next.js Production Build
```
▲ Next.js 16.3.8 (Turbopack)
✓ Compiled successfully in 1856ms
✓ Generating static pages using 7 workers (35/35) in 838ms
Finalizing page optimization ...
Routes: 35/35 compiled without errors.
```

---

## 5. Deployment Considerations

| Environment | TeX Live Available? | Resolution |
|---|---|---|
| **Local Dev** | Optional | pdflatex if installed; ReportLab vector renderer if not. |
| **Railway Container** | No (image size limit) | Seamless ReportLab vector renderer generates valid ATS PDF in <120ms. Overleaf-compatible `.tex` source remains available for Overleaf download. |
| **Serverless / Vercel** | No (50MB function limit) | ReportLab vector renderer operates in-memory with zero OS dependencies. |

Candidate isolation is strictly preserved across all endpoints (`403 Forbidden` on unauthorized access), and private storage paths are never exposed to clients.
