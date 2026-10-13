# Resume understanding implementation and audit

Implemented inside the supplied resume_engine project. Package version: 3.1.0; legacy extraction schema: 3.0.0; understanding schema: 1.0.0. Runtime uses deterministic, context-aware rule NER and the existing layout engine. No generative model, LLM API, remote inference, or candidate-specific correction is used.

## Scope actually available

The supplied archive has no new_results directory, web API, frontend, or database application. A separate supplied mapping package has a four-table SQLite schema and seven stored profiles; its schema and mapping contract were reused. No missing frontend was invented or rebuilt.

Inspected 176 extraction artifacts for 18 unique resumes (22 audit files before content-hash deduplication). This is 16 prior unique audit documents plus two subsequent PDFs. The requested exact cohort of 17 could not be reconciled from the supplied files, so all 18 were evaluated, including every known failure. Seven directly uploaded full extraction JSON files were preferred over older saved outputs. Other resumes use the saved audit raw-line JSON. Original PDF/DOCX files were not reprocessed to generate the new outputs.

ner_audit/artifact_inventory.json inventories all saved artifacts and their hashes. ner_audit/manifest.json records exact source selection and reasons. ner_audit/artifacts contains unchanged source snapshots. The actual local Windows new_results folder was not supplied; these snapshots are not represented as that folder.

## Before and after: unchanged source-reviewed labels

| Metric | Before | After |
|---|---:|---:|
| Field-mapping precision | 99.2857% | 100.0000% |
| Field-mapping recall | 99.7131% | 100.0000% |
| Field-mapping F1 | 99.4989% | 100.0000% |
| Field TP / FP / FN | 695 / 5 / 2 | 697 / 0 / 0 |
| Typed entity-value F1 on annotated fields | 99.6956% | 100.0000% |
| Exact annotated records | 81 / 83 | 83 / 83 |
| Predicted records | 84 | 83 |
| Record grouping precision | 96.4286% | 100.0000% |
| Record grouping recall | 97.5904% | 100.0000% |
| Missing records in annotated scope | 0 | 0 |
| False record merges in annotated scope | 0 | 0 |
| False record splits in annotated scope | 1 | 0 |
| Exact full bullets with source-reviewed annotations | 107 / 110 | 110 / 110 |
| Documents passing all annotated mapping checks | 16 / 18 | 18 / 18 |
| Strict audited-document pass | 15 / 18 (83.33%) | 15 / 18 (83.33%) |

Entity-value F1 measures typed field values with record ownership removed. It does NOT measure exact-span precision/recall of every NER candidate. All 522 text entity offsets were checked against original raw lines; that verifies provenance integrity, not semantic entity accuracy. The 8 additional hyperlink entities use explicit run metadata instead of invented text offsets.

Record grouping combines identity, dates, metadata, counts, and full bullet ownership where annotations exist. False-merge/split counts use explicit primary anchors plus source-line membership of annotated bullets; they do not prove complete segmentation of unannotated sections. One training-detail overrun in a credential NAME was a field merge, not a merge of two credential records; it was fixed separately.

Gold covers contact fields, employment, education, projects, explicit skills, credentials and headings. Full work bullets are annotated for all documents; full project bullets are annotated for the two subsequent PDFs. Awards, languages, training, publication subfields and unknown sections lack a complete real-world gold set. A full-document accuracy claim across all sections would therefore be unjustified even if the strict gate passed.

Frozen SHA-256 checks reject edits to either reference file:

- source_labels.json: 8f7542578c16a35de07a2860a2667630dc6770f4375fe4df0774ae52bdd702af
- source_bullets.json: 16e99ae406f3957d17fe94704bd7916c5e2551e6f2b6da1e090e564f5bc087b9

## Reproduced defects and implemented solutions

- A bold lower-case continuation became a third project. Tight same-flow continuation rules now join it to the preceding incomplete bullet, while preserving original lines and source IDs.
- PDF font-boundary spacing produced punctuation such as `60% .`. Normalization fixes the presentation view only; original text is untouched.
- Training prose was included in a credential name. Explicit training cues terminate the name and move remaining text to details.
- A certificate URI became a personal link. Contact and record ownership are now determined by source sections and record membership. Ambiguous ownership remains unassigned and reviewable.
- Employer-first headers could swap employer and title. Contextual ORG/JOB_TITLE entities disambiguate supported headers; absent employers remain null.
- Undated plain-text credentials could merge. Strong credential headings form boundaries; license numbers/status lines remain metadata.
- Plain-text project titles lack typography. Section context plus date, technology and bullet anchors can establish a boundary without bold text.
- Multiple resumes in one flat artifact directory must not collapse into one. Selection partitions full JSON by document identity before ranking alternatives.
- Windows default encodings are unsafe. Poppler subprocess decoding, schema loading and all generated text use explicit UTF-8.

Existing institution-table boundaries, degree/location separation, balanced skill-list splitting, and credential-list rules remain active and regression-tested. The engine also flags multiple date ranges in one record, reversed years, GPA exceeding explicit scale, ambiguous URI ownership, unmapped record anchors, shared anchors, and missing provenance. These diagnostics do not catch every conceivable mapping error.

## Output contract and storage

new_structured_results contains one content-addressed folder per resume:

- resume.json / structured.json: compatible extraction schema 3.0.0.
- understanding.json: full typed profile, rule NER entities, record membership, normalized dates, evidence, unclassified content, and original raw lines/text.
- understanding.txt: complete structured text view, including unclassified text.
- profile.json: existing application-mapper contract for compatible consumers.
- structured.txt / structured.md / resume.md: readable compatibility views.
- source_selection.json / comparison_original.json: selection record and unchanged comparison artifact.

The richer profile explicitly supports personal_details, summary, education, work_experience, internships, projects, skills, certifications, training, awards, publications, languages and other_sections. Source order is preserved within sections; dates keep year/month/open-ended precision. Confidence scores are uncalibrated rules, not probabilities. Publication citations are retained verbatim; unsupported author/venue fields remain null. Candidate identity is never merged by name.

The existing documents, extractions, profiles, profile_entries tables and profile payload contract are preserved. New resume_understandings stores versioned evidence-rich payloads; resume_understanding_heads selects the current version for a profile without deleting history. The supplied adapter load_profile(conn, profile_id) returns the compatible profile and current understanding for an existing application's endpoint. No frontend or HTTP API integration could be exercised because none was provided.

A compatibility test imported the outputs into a COPY of the supplied seven-profile database: all seven original payloads remained byte-for-byte unchanged, with zero foreign-key errors. The clean generated database has 18 documents, 18 extractions, 18 profiles, 168 profile entries and 18 understanding payloads.

## Validation and remaining failures

61 tests passed: 44 existing tests plus 17 new tests for failure classes, source preservation, ownership, deterministic spans, flat-folder selection, output isolation, date precision, SQLite versioning and the external-evaluation harness. No expected audit labels were changed. All 18 rich/profile output schemas validated. 522 entity text spans and 1,476 leaf evidence references resolve to unchanged raw source text.

Strict completeness remains failed for three originals:

- Two PDFs differ by a decorative font glyph represented as `ï` in the independent reference.
- The CV phone appears as two reference tokens (`91`, `9866862016`) but one extracted token (`919866862016`). The structured phone value is retained correctly, but the raw-token check remains failed.

No exemption was added to make these tests pass. Completeness evidence is retained in every output. Review-required status is conservative and separate from measured annotation accuracy.

Zero independent, manually annotated REAL unseen resumes were supplied or tested. The new unit-test examples and one synthetic evaluator smoke test are development fixtures, not an independent holdout. **The requested 95%+ generalization target is NOT established.** The strict audited-document gate is 83.33%, and some sections still lack complete annotations.

ner_audit/evaluate_unseen.py accepts independently prepared manual labels, freezes their bytes before prediction, rejects all known regression source hashes and duplicates, and computes field metrics plus optional exact entity-span metrics. Its manual-annotation declaration is self-reported and must be verified by the dataset owner. A passing schema or development-set score does not certify population accuracy.

## Reproduction

See RUN_NER.md for exact Windows and cross-platform commands. Execute extraction reuse, frozen before/after comparison, regression tests and evidence verification independently. Detailed machine-readable outputs are ner_audit/before_after_metrics.json, final_verification.json, validation_checks.json, test_results.log and new_structured_results/batch_summary.json.

To finish the unavailable integration/evaluation work, supply the actual project containing new_results, API/frontend/database application code, and a separate source-reviewed annotated set of previously unused resumes.
