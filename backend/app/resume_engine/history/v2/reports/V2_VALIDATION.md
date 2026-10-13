# Version 2 validation — 12 October 2026

- Automated tests: 32 passed. See `v2_tests.log`.
- Existing labelled development corpus: 19 files, 15 distinct personas.
- Raw word multiset completeness: passed for all 19 digital files.
- Existing heading mapping benchmark: 86 true positives, 0 false positives,
  0 false negatives; precision/recall/F1 = 100%.
- Existing atomic-field benchmark: 570 true positives, 0 false positives,
  0 false negatives; precision/recall/F1 = 100%.
- All 19 batch outputs passed the shipped schema validation.
- New regression tests cover the uploaded result, real sidebar preservation,
  ambiguous dates, inline education and graduation, wrapped table institutions,
  credentials in education tables, inline date separators, and undated jobs.

These are development-set results using existing task-authored labels. They are
not independently adjudicated, held-out measurements. The 570 atomic fields
belong to the existing evaluator; that metric does NOT measure every new
education/project/certification field or all possible layouts. No broad accuracy
percentage is asserted for the new schema. See `v2_accuracy.json` for counts and
per-file errors, and `tests/test_13_structure.py` for the new assertions.

The uploaded sample was reprocessed from saved raw lines and bounding boxes.
Its raw text and raw line records remain identical. Its original PDF is absent;
independent source completeness remains unverifiable and is explicitly flagged.
No ML model was trained, added or called. All extraction remains offline.

To reproduce:

```bash
python -m unittest discover -s tests -q
python tools/evaluate.py tests/corpus --gold tests/gold --out reports/v2_accuracy.json
python -m resume_extract tests/corpus --out outputs
python -m resume_extract tests/samples/uploaded_result.json --from-result --out results/uploaded_sample
```
