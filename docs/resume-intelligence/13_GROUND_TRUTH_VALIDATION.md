# 13. Ground Truth Validation & Annotation Protocol

## 1. Ground Truth Specification & Schema

To evaluate VidyaMarg AI's extraction engine objectively without guessing or approximations, every fixture in the 41-file corpus is paired with a strictly validated ground truth JSON file in `backend/tests/real_world_corpus/ground_truth/{test_id}_truth.json`.

### Canonical Ground Truth Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "VidyaMargResumeGroundTruth",
  "type": "object",
  "properties": {
    "test_id": { "type": "string" },
    "expected_status": { "type": "string", "enum": ["success", "rejected"] },
    "rejection_reason": { "type": "string" },
    "personal_info": {
      "type": "object",
      "properties": {
        "full_name": { "type": "string" },
        "email": { "type": "string" },
        "phone": { "type": "string" },
        "location": { "type": "string" },
        "professional_title": { "type": "string" },
        "linkedin_url": { "type": "string" },
        "github_url": { "type": "string" },
        "portfolio_url": { "type": "string" }
      },
      "required": ["full_name"]
    },
    "professional_summary": { "type": "string" },
    "work_experience": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "employer": { "type": "string" },
          "designation": { "type": "string" },
          "start_date": { "type": "string" },
          "end_date": { "type": "string" },
          "is_current": { "type": "boolean" },
          "employment_location": { "type": "string" },
          "responsibilities": { "type": "array", "items": { "type": "string" } },
          "technologies": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["employer", "designation"]
      }
    },
    "education": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "institution": { "type": "string" },
          "degree": { "type": "string" },
          "graduation_year": { "type": "string" },
          "gpa": { "type": "string" },
          "location": { "type": "string" }
        },
        "required": ["institution", "degree"]
      }
    },
    "skills": {
      "type": "object",
      "properties": {
        "programming_languages": { "type": "array", "items": { "type": "string" } },
        "frameworks_libraries": { "type": "array", "items": { "type": "string" } },
        "cloud_platforms": { "type": "array", "items": { "type": "string" } },
        "databases": { "type": "array", "items": { "type": "string" } },
        "developer_tools": { "type": "array", "items": { "type": "string" } }
      }
    },
    "projects": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "description": { "type": "string" },
          "technologies": { "type": "array", "items": { "type": "string" } },
          "link": { "type": "string" }
        },
        "required": ["name"]
      }
    },
    "certifications": { "type": "array", "items": { "type": "string" } },
    "hyperlinks": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "url": { "type": "string" },
          "text": { "type": "string" }
        },
        "required": ["url"]
      }
    }
  },
  "required": ["test_id", "expected_status"]
}
```

---

## 2. Ground Truth Construction & Verification Methodology

1. **Source Generation Verification**:
   - Every fixture was synthesized with explicit data tables passed directly to the generator scripts.
   - The exact parameters fed into `fitz.Page.insert_text()`, `docx.Document.add_paragraph()`, and HTML templates were simultaneously serialized into the ground truth JSON files.
2. **Visual & Structural Inspection**:
   - Rendered PDFs and documents were opened and cross-examined to ensure no text collisions, clipping, or font rasterization anomalies occurred.
3. **Hyperlink Coordinate Mapping**:
   - PDF URI link annotations (`fitz.Page.get_links()`) and DOCX relationships (`w:hyperlink r:id="..."`) were verified against the target destination URLs in `ground_truth.json`.

---

## 3. Discrepancy Resolution & Edge Rulebook

| Condition | Annotation Rule | Pipeline Evaluation Metric |
| :--- | :--- | :--- |
| **Absent Information** | If a resume does not mention GPA, end date, or phone number, the field is explicitly omitted or set to `null` in the ground truth. | If the parser hallucinates a placeholder (e.g. "N/A", "0.0"), it is scored as **Incorrect**. If omitted, it is scored as **Correct**. |
| **Ambiguous Date Formats** | E.g. "06/07" (could be June 2007 or June 7th). Annotated as `"2007-06"` if in career context. | Evaluator performs fuzzy year-month matching (e.g. "2007" or "06/2007"). |
| **Promotion within Company** | E.g., Senior Engineer $\rightarrow$ Staff Engineer at Google. Annotated as multiple experience items with the same `employer`. | Evaluator checks employer string and distinct designations without merging into a single job. |
| **Shared Tech Stacks** | When multiple projects cite "Python, AWS", each project ground truth retains its own technology array. | Canonical project normalizer deduplicates tokens per entity. |
| **Unicode Ligatures** | Ligatures like `ﬁ` (U+FB01) in "ﬁnancial" are annotated in normalized ASCII ("financial"). | Parser must perform Unicode NFKD normalization before field assignment. |
| **Split URLs** | E.g., visible text: `linkedin.com/in/john` broken across two lines. Destination: `https://linkedin.com/in/johndoe`. Annotated with destination URL. | Evaluator verifies the extracted target URL matches the ground truth URI destination. |
