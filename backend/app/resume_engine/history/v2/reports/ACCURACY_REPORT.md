# Accuracy report

## Scope and label provenance

All three supplied archives were unpacked and all 19 resumes were processed: 14 DOCX and 5 digital PDFs. Four files are byte-identical duplicates across bundles, leaving 15 unique files/personas. The three README/benchmark guides are not resumes and were excluded.

**No labelled gold JSON was present in the uploads.** Gold records were explicitly authored from source content for this task, and the rules were developed against this corpus. These are development-set results. They do not certify accuracy on a user-labelled held-out set or on arbitrary future templates. Each gold file is bound to the original file SHA-256. A second-person annotation review is still required for independent acceptance.

## Final measured results

| Measure | Result | Denominator |
| --- | ---: | --- |
| Raw text word recall | 100.00% | 4615/4615 source words |
| Raw text word precision | 100.00% | Zero extra words |
| Strict file completeness | 19/19 pass | Missing or extra words both fail |
| H1 detection and canonical mapping F1 | 100.00% | 86 expected heading boundaries |
| Field micro precision / recall / F1 | 100.00% / 100.00% / 100.00% | 570 explicit atomic field items |
| Experience entry exact matches | 38/38 | Title + company + start + end + bullet count |
| Unique-file field F1 | 100.00% | 441 atomic items, 15 unique files |
| Automated tests | 25/25 pass | Including 19-file offline, schema and determinism subtests |
| Clean synthetic OCR transcript | 41/41 words | One separate English rasterized page, not supplied corpus |

The configured digital-text target is 100% word recall with zero extras; heading target is 98% F1; field target is 95% micro F1. These development-set targets pass. No independent held-out target claim is made. OCR never uses its own output as completeness truth: ordinary OCR quality reports say `unverifiable`; only this fixture has a known transcript.

## Metric definitions

- Text: case-sensitive Unicode word-token multiset equality against independent DOCX XML text traversal or `pdftotext -raw`. Repeated tokens count separately. Punctuation, whitespace and visual reading order are not measured by word equality. PDF CID bullet decoding occurs before the raw comparison; original undecoded run tokens are retained.
- Headings: exact original H1 heading text paired with the canonical section key. TITLE/SUBTITLE/H2/BULLET/TEXT tagging is covered by fixtures, not the 86-heading corpus score.
- Fields: exact strings or exact structured values with multiset precision/recall/F1. Experience title/company/start/end/bullet-count pairs are keyed by entry order. Entry tuple accuracy is reported separately and is not double-counted in micro F1.
- Skill labels use the declared seed vocabulary across document text, apply alias normalization and longest-phrase preference, and measure mentions rather than proficiency. This is not recall against the full ESCO/O*NET universe.
- Degrees are source mentions; an explicit expanded MBA and its parenthetical abbreviation are both labelled. Contacts include LinkedIn/GitHub URLs only. Arbitrary portfolios, institutions, certification entities, publication details and full per-bullet text assignment are not included in the field denominator.
- Confidence numbers are rule scores, not calibrated probabilities. Invalid dummy phones, fallback names and OCR candidates remain available and are routed for review. A review flag is not itself an extraction error.

## Per-field metrics

| Field | TP | FP | FN | Precision | Recall | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| headings | 86 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| heading_detection | 86 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| name | 19 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| emails | 19 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| phones | 19 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| locations | 19 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| urls | 19 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| date_ranges | 49 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| degrees | 30 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| gpas | 4 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| skills | 202 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| experience_entries | 38 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| experience_title | 38 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| experience_company | 38 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| experience_start | 38 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| experience_end | 38 | 0 | 0 | 100.00% | 100.00% | 100.00% |
| experience_bullet_count | 38 | 0 | 0 | 100.00% | 100.00% | 100.00% |

## Per-resume completeness

| File | Source words | Missing | Extra | Status |
| --- | ---: | ---: | ---: | --- |
| colorful_resume_templates_bundle/01_DOCX_Vibrant_Coral_Creative_Resume.docx | 197 | 0 | 0 | pass |
| colorful_resume_templates_bundle/02_DOCX_Navy_Teal_Cloud_Architect.docx | 217 | 0 | 0 | pass |
| colorful_resume_templates_bundle/03_PDF_Royal_Purple_Marketing_Resume.pdf | 228 | 0 | 0 | pass |
| colorful_resume_templates_bundle/04_PDF_Emerald_Forest_Operations_Resume.pdf | 188 | 0 | 0 | pass |
| comprehensive_resume_test_suite/01_DOCX_Two_Column_Sidebar_Layout.docx | 209 | 0 | 0 | pass |
| comprehensive_resume_test_suite/02_DOCX_Heavy_Table_Layout_Resume.docx | 181 | 0 | 0 | pass |
| comprehensive_resume_test_suite/03_DOCX_Horizontal_Hero_Two_Blocks.docx | 204 | 0 | 0 | pass |
| comprehensive_resume_test_suite/04_PDF_Two_Column_Sidebar_Layout.pdf | 206 | 0 | 0 | pass |
| comprehensive_resume_test_suite/05_PDF_Strict_Table_Grid_Resume.pdf | 211 | 0 | 0 | pass |
| comprehensive_resume_test_suite/06_PDF_Horizontal_Hero_Two_Blocks.pdf | 219 | 0 | 0 | pass |
| comprehensive_resume_test_suite/07_DOCX_Modern_Tech_Software_Engineer.docx | 357 | 0 | 0 | pass |
| comprehensive_resume_test_suite/08_DOCX_Executive_Corporate_Director.docx | 339 | 0 | 0 | pass |
| comprehensive_resume_test_suite/09_DOCX_Academic_Research_CV.docx | 204 | 0 | 0 | pass |
| comprehensive_resume_test_suite/10_DOCX_Entry_Level_Business_Analyst.docx | 247 | 0 | 0 | pass |
| resume_templates_test_bundle/01_Modern_Tech_Software_Engineer.docx | 357 | 0 | 0 | pass |
| resume_templates_test_bundle/02_Executive_Corporate_Director.docx | 339 | 0 | 0 | pass |
| resume_templates_test_bundle/03_Creative_Product_UX_Designer.docx | 261 | 0 | 0 | pass |
| resume_templates_test_bundle/04_Academic_Research_CV.docx | 204 | 0 | 0 | pass |
| resume_templates_test_bundle/05_Entry_Level_Business_Analyst.docx | 247 | 0 | 0 | pass |

## Layer test output

Actual detailed logs are shipped under `reports/layer_*.log`. Final layer totals:

| Layer | Tests | Result |
| --- | ---: | --- |
| Ingest | 2 | PASS |
| DOCX reader | 1 | PASS |
| PDF reader | 2 | PASS |
| Normalization | 3 | PASS |
| Classification | 1 | PASS |
| Sections | 1 | PASS |
| Fields | 2 | PASS |
| Validation | 3 | PASS |
| Pipeline | 1 | PASS |
| Regressions | 4 | PASS |
| Layout and OCR fixtures | 4 | PASS |
| Supplied corpus | 1 | PASS |

## Development findings and corrections

Initial corpus extraction preserved source words but surfaced PDF CID bullet placeholders as extra tokens. The reader now decodes them to bullets and retains their original glyph text. Bold role titles and table category labels were initially over-promoted to H1; date adjacency, separators and table-row context now keep them below section level. Contact false positives in credential-bearing names, publication page intervals mistaken for dates, and ambiguous skill aliases have explicit regression coverage.

One annotation error was corrected after consulting the original text: Sophia’s CV contains “Deep Learning” and the journal title “Nature Machine Intelligence”, not the phrase “Machine Learning”. This was a gold correction, not an extraction success. The annotation generator records literal reviewed expectations and never imports predictions.

The first synthetic scan was malformed by proportional-font substitution during fixture rasterization and scored 16/41 matched words (39.02% recall). The fixture was regenerated with a monospaced source font to avoid overlapping/substituted glyph spacing; the final clean fixture scores 41/41. No OCR autocorrection rule or external model was added. This small clean fixture is not evidence of robust low-quality-scan accuracy.

Legacy DOC conversion remains untested because LibreOffice was not installed. More limitations and proposed rules are in `REMAINING_FAILURE_CASES.md`.

## Reproduce

```bash
python tools/run_layers.py
python tools/evaluate.py tests/corpus --gold tests/gold --out reports/accuracy.json
python -m resume_extract tests/corpus --out outputs/
python tools/make_report.py
```

Execution environment: Python 3.12.14, Linux. Library pins are in `requirements.txt`. Poppler and Tesseract versions are recorded in `reports/environment.txt`. No runtime socket calls were permitted during supplied-corpus regression testing.
