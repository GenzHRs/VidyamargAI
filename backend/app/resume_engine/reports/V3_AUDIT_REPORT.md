# Resume extraction audit — version 3

Audit date: 2026-10-12. These are automatic, fresh outputs from the original supplied files. No output fields were manually corrected.

**The supplied development set exceeds the 95% target. Unseen-document accuracy has not been established.**

## Measured results

| Measure | Before (v2) | After (v3) |
| --- | ---: | ---: |
| Field precision — all files | 90.07% | 100.00% |
| Field recall — all files | 86.75% | 100.00% |
| Field F1 — all files | 88.38% | 100.00% |
| Field F1 — 16 unique documents | 87.66% | 100.00% |
| Heading F1 | 99.45% | 100.00% |
| Complete reviewed job bullets | 95/104 | 104/104 |
| Schema-valid files | 20/20 | 20/20 |

Field counts: v2 TP 635, FP 70, FN 97; v3 TP 732, FP 0, FN 0. Deduplicated v3: TP 585, FP 0, FN 0. All 20 heading sequences match source labels exactly. All 44 tests pass, including 12 new test methods for generalized failure classes.

## Drawbacks and implemented fixes

| Observed drawback | Implemented solution |
| --- | --- |
| Bold PDF text not recognized | Recognize font families such as subset Computer Modern bold |
| Missing dash bullets and truncated percentages/acronyms | Identify dash markers and join tightly aligned continuation lines without relying on lowercase text |
| Missing embedded contact links and international phone | Read PDF URI annotations, broaden contact URLs and country-code phone patterns |
| Employer mixed with city | Split corporate suffix followed by a location; bound header extraction before bullets |
| Education fields mixed in one table cell | Join only institution continuations; stop at degree/date/graduation/GPA metadata |
| Degree dates and CGPA lost | Strip date ranges from qualification labels and parse CGPA scales |
| Project schema could not represent source data | Add date range and evidence-backed explicit technology array; recognize dated project headers |
| Skills split inside parentheses | Split only outside balanced brackets; keep full phrases and table column categories |
| Mixed awards and credentials | Route credential records separately while preserving award text |
| Several certificates collapsed into one | Split top-level credential lists, preserving parenthetical commas and training prose |

## Per-group exact field F1

| Group | v2 | v3 |
| --- | ---: | ---: |
| certifications | 53.33% | 100.00% |
| contact | 95.57% | 100.00% |
| education | 87.08% | 100.00% |
| experience | 98.70% | 100.00% |
| project technologies | 0.00% | 100.00% |
| projects | 38.10% | 100.00% |
| skills | 83.87% | 100.00% |

## Remaining drawbacks and scope

- This is a small development set: 20 files, 16 distinct source hashes, with related template/persona families. Rules were tuned after inspecting its errors. Labels were assistant-reviewed, not blinded or independently adjudicated. The 100% figure must not be advertised as production or unseen-resume accuracy.
- The field score covers selected non-null scalar claims, category-plus-skill phrases, project technology items, certification labels and bullet counts. It does not score every summary statement, publication, award, certification detail, or inferred meaning. Full job bullet text has an additional separate 104-item check.
- Strict raw word recall is 5065/5066 (99.98%); deduplicated recall is 3918/3919 (99.97%). R01 remains a strict completeness failure because Poppler emits `ï` for a decorative LinkedIn icon while the font-aware reader decodes the icon differently. The real URL is recovered from the PDF annotation. The missing token remains reported; it was not deleted from the denominator.
- Dense nested layouts, unmarked role boundaries, unusual institution/location forms, mixed credential prose, unfamiliar URLs and noisy OCR can still fail. Parentheses and table ownership reduce errors but cannot establish semantics.
- OCR outputs retain conservative scores and an unverifiable completeness status. These digital-document audit scores do not establish OCR accuracy. Real legacy DOC conversion was not integration-tested.
- Confidence scores are heuristics, not calibrated probabilities. Review flags are advisory and are not proven to catch every error.

## Reproducibility and safeguards

Run `python validation/reproducibility/run_benchmark.py` from the project root. Original hashes are checked before extraction. Frozen reference labels are in `validation/audit/source_labels.json`; original complete-bullet references are in `source_job_bullets.json`. The scoring adapter now reads project date/technology fields, but matching, normalization and reference labels are unchanged. Re-scoring frozen v2 predictions through the updated adapter reproduces the original TP/FP/FN exactly; see `scorer_compatibility.json`.

Exact matching normalizes NFKC, whitespace and trailing label colons; phone punctuation and URL scheme/www/trailing slash are ignored. Wrong values count as both FP and FN. Jobs, education and projects are matched by entry ordinal. Null/null is not counted. Heading order is checked separately. Full bullets normalize NFKC, whitespace and the leading bullet marker only.

No ML model was trained. General parsing rules solved the observed failure classes. The engine does not read filenames, source hashes, benchmark labels or corrected examples to choose field values. Additional tests use different names, institutions, dates, percentages, phone formats, project labels, fonts and nested list contents.

Before claiming 95%+ for future resumes, follow the untouched-holdout workflow in `STRUCTURED_OUTPUT_GUIDE.md`; include unseen template families, duplicate controls, independent review and separate OCR reporting.

## File-by-file results

| ID | Original file | v2 field F1 | v3 field F1 | Duplicate of |
| --- | --- | ---: | ---: | --- |
| R01 | Jayavarapu-Siva-Tejachary-AIML.pdf | 64.06% | 100.00% | — |
| R02 | colorful_resume_templates_bundle/01_DOCX_Vibrant_Coral_Creative_Resume.docx | 94.74% | 100.00% | — |
| R03 | colorful_resume_templates_bundle/02_DOCX_Navy_Teal_Cloud_Architect.docx | 100.00% | 100.00% | — |
| R04 | colorful_resume_templates_bundle/03_PDF_Royal_Purple_Marketing_Resume.pdf | 93.10% | 100.00% | — |
| R05 | colorful_resume_templates_bundle/04_PDF_Emerald_Forest_Operations_Resume.pdf | 67.65% | 100.00% | — |
| R06 | comprehensive_resume_test_suite/01_DOCX_Two_Column_Sidebar_Layout.docx | 94.74% | 100.00% | — |
| R07 | comprehensive_resume_test_suite/02_DOCX_Heavy_Table_Layout_Resume.docx | 90.91% | 100.00% | — |
| R08 | comprehensive_resume_test_suite/03_DOCX_Horizontal_Hero_Two_Blocks.docx | 100.00% | 100.00% | — |
| R09 | comprehensive_resume_test_suite/04_PDF_Two_Column_Sidebar_Layout.pdf | 95.12% | 100.00% | — |
| R10 | comprehensive_resume_test_suite/05_PDF_Strict_Table_Grid_Resume.pdf | 66.67% | 100.00% | — |
| R11 | comprehensive_resume_test_suite/06_PDF_Horizontal_Hero_Two_Blocks.pdf | 100.00% | 100.00% | — |
| R12 | comprehensive_resume_test_suite/07_DOCX_Modern_Tech_Software_Engineer.docx | 92.98% | 100.00% | — |
| R13 | comprehensive_resume_test_suite/08_DOCX_Executive_Corporate_Director.docx | 95.52% | 100.00% | — |
| R14 | comprehensive_resume_test_suite/09_DOCX_Academic_Research_CV.docx | 81.08% | 100.00% | — |
| R15 | comprehensive_resume_test_suite/10_DOCX_Entry_Level_Business_Analyst.docx | 89.47% | 100.00% | — |
| R16 | resume_templates_test_bundle/01_Modern_Tech_Software_Engineer.docx | 92.98% | 100.00% | R12 |
| R17 | resume_templates_test_bundle/02_Executive_Corporate_Director.docx | 95.52% | 100.00% | R13 |
| R18 | resume_templates_test_bundle/03_Creative_Product_UX_Designer.docx | 91.67% | 100.00% | — |
| R19 | resume_templates_test_bundle/04_Academic_Research_CV.docx | 81.08% | 100.00% | R14 |
| R20 | resume_templates_test_bundle/05_Entry_Level_Business_Analyst.docx | 89.47% | 100.00% | R15 |
