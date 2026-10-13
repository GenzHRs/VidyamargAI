# Run the offline resume understanding engine

Run from the extracted `resume_engine` directory. Python 3.10+ is required.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-test.txt
python -m pip install -e . --no-deps
```

On Linux/macOS activate with `source .venv/bin/activate`. Saved-artifact understanding needs no Poppler, Tesseract, network service or model download. The complete legacy PDF/OCR test suite also requires locally installed Poppler and Tesseract, as documented in the original README.

## Process your existing local new_results folder

```powershell
python -m resume_extract.understand_cli ".\new_results" --out ".\new_structured_results" --db ".\new_structured_results\resumes.sqlite"
```

The ZIP supplied in this conversation did not contain new_results. Use that command when running beside your actual folder. The output and database must be outside the input tree. The command refuses overlapping paths. It reads every artifact, selects raw-line JSON by source identity, and uses raw/natural text only when layout-rich JSON is unavailable. Structured-only JSON is never selected as source. Missing natural text or layout evidence is reported rather than guessed.

For a single saved JSON:

```powershell
python -m resume_extract.understand_cli ".\new_results\example\resume.json" --out ".\new_structured_results"
```

Plain UTF-8 `.txt` is accepted; lack of independent completeness/layout information is explicitly marked. No original PDF or DOCX is re-extracted by this command.

Exit codes: 0 = processing succeeded (may still need review); 1 = processing/schema/evidence failure; 2 = invalid arguments or, with `--strict`, any review-required document. The saved review/completeness flags remain visible even without `--strict`.

## Reproduce the included 18-resume audit

```powershell
python -m resume_extract.understand_cli ner_audit/artifacts --out new_structured_results --db new_structured_results/resumes.sqlite
python ner_audit/evaluate.py --results new_structured_results
python -m unittest discover -s tests -v
python ner_audit/verify_outputs.py --results new_structured_results
```

The evaluator checks frozen label hashes and the original artifact hashes. It does not modify reference labels. Adding source-reviewed annotations requires a separately versioned evaluation set; do not change expected values to fit output.

## Independent unseen evaluation

Prepare manual labels from previously unused original resumes, with this envelope:

```json
{
  "annotation_method": "manual_source_review",
  "documents": [
    {
      "artifact": "artifacts/unseen_01/resume.json",
      "source_sha256": "SHA256_OF_ORIGINAL_RESUME",
      "gold": {
        "contact": {"name": "SOURCE NAME", "emails": [], "phones": [], "locations": [], "links": []},
        "experience": [], "education": [], "projects": [],
        "skills": [], "certifications": [], "headings": []
      }
    }
  ]
}
```

This is a format illustration, not an annotated example: replace placeholders and fully annotate every supported section. Use the record shapes in ner_audit/source_labels.json. Review originals, not generated JSON. Annotators should be independent of rule development. Add complete `entity_spans` for each selected label type if exact-span NER metrics are needed; see evaluate_unseen.py's docstring. The engine does not read gold labels during extraction.

```powershell
python ner_audit/evaluate_unseen.py path/to/manual_labels.json --out independent_evaluation
```

Known audit hashes and duplicate documents are rejected. Annotation bytes are frozen before predictions. This tool records self-declared manual provenance; it cannot certify independence or annotation completeness. No independent real unseen result is included in this package.

## Existing application integration

```python
from resume_extract.understanding import understand_artifact
from resume_extract.understand_cli import store, load_profile
import sqlite3

compatible, understanding = understand_artifact("new_results/example/resume.json")
with sqlite3.connect("application.sqlite") as conn:
    mapped = store(conn, compatible, understanding)
    response = load_profile(conn, mapped["record_id"])
```

The adapter supports the supplied SQLite mapping schema. It creates only absent compatible tables plus the two new understanding tables and inserts new versioned rows. It does not migrate an unknown database schema, recreate a frontend, or provide an HTTP service. If your actual app uses another schema, wire this adapter into that app after reviewing its code.

Use `response["profile"]` for the existing mapper contract and `response["understanding"]["profile"]` for the richer sections. Render each field with its evidence references and review status. Do not equate `mapped_unverified` with human-verified accuracy.
