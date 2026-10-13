# Structured output guide — version 3

Use `structured.json` for applications and `structured.txt` or `structured.md` for reading. The TXT file uses the same heading-based plain-text structure as Markdown. Keep `resume.json` as the full audit record.

## Correct order

Render `section_order`: contact → summary → experience → education → projects → skills → certifications → other sections. Within each section, preserve array order (`entry_order: source`). This avoids inventing chronology when dates are missing or overlapping. `source_sections` retains the document's actual section order; raw coordinates and reader order remain in `resume.json`.

## Fields

| Key | Contents |
| --- | --- |
| `contact` | Name, email addresses, phone numbers, locations, visible or embedded links |
| `summary` | Source summary paragraphs |
| `experience` | Title, employer, location, source-precision date range, complete bullets and block text |
| `education` | Degree, institution, location, date range, graduation and GPA/CGPA |
| `projects` | Name, date range, explicit technology list, description, bullets and block text |
| `skills` | Explicit category and full source phrases; parenthetical lists remain intact |
| `certifications` | Credential name, details and complete source block |
| `other_sections` | Awards, publications, languages and other source content |
| `source_sections` | Every source section, including content not mapped into a dedicated field |
| `review` | Missing or ambiguous candidates and source-quality problems |

Field values retain their evidence:

```json
{
  "value": {"start": "Sept 2022", "end": "June 2023"},
  "source_line_ids": ["l00012"],
  "confidence": 0.95
}
```

Project `technologies` is an array of field objects. Missing dates use `value: null`; unknown technologies use an empty array. Technology extraction uses explicit labels such as `Tech:` and does not guess a project's stack from unrelated skills. Date strings preserve source precision; no day or missing start year is invented. Scores are heuristic strengths, not calibrated accuracy estimates. A high score is not a correctness guarantee, and review routing can miss errors.

`fields.skills` in the full `resume.json` is a separate, curated mention detector. For the user's actual listed skill categories, use `structured.skills`.

## Run and save new resumes

```bash
python -m resume_extract /path/to/resumes --out new_results
```

For saved extraction JSON with raw line evidence:

```bash
python -m resume_extract old_resume.json --from-result --out reprocessed
```

Reprocessing can improve structure but cannot recover hyperlinks or text absent from the saved input. Re-extract the original PDF to use the new hyperlink reader. The general CLI creates named/hash-suffixed folders; only the supplied benchmark uses R01–R20 IDs.

Keep the source SHA-256, schema version, config SHA-256, extraction result and review history. For relational child tables, save `resume_id`, section, entry ordinal and evidence IDs. Store human corrections separately from machine predictions. Do not silently replace the source values or count reviewed corrections as automated accuracy.

International numbers with `+` use their country code. Other numbers use `fields.default_phone_region` (US by default); configure the expected region explicitly. Contiguous local numbers without a country code are not comprehensively supported. Unusual addresses and websites may require review.

## Reaching 95% on future documents

Freeze a representative holdout containing unseen people and template families. Label contact data, employment, education, project dates/technologies, full skill phrases and full bullet text from original documents; have a second reviewer adjudicate disagreements. Exclude duplicates and related template families from the tuning set. Run the same matching and normalization rules, report per-field and per-template scores, and inspect missing/extra values.

Accept a new release only after the untouched holdout reaches the agreed 95%+ field F1 target, critical groups meet their thresholds, and content/order checks pass. Keep OCR and clean digital-document scores separate. Re-run after rule or configuration changes. A confidence score of 0.95 does not satisfy this gate.

No ML was needed to fix the demonstrated failures. Consider a local layout/section model only if a larger, independently labeled corpus shows persistent failures that rules cannot handle. Train and tune outside the holdout; retain source spans, schema validation, null/abstention behavior and human review. Neither rules nor ML can reconstruct facts missing from the original source.
