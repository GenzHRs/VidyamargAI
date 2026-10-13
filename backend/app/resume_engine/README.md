# Version 3.1: offline NER understanding added

Start with [RUN_NER.md](RUN_NER.md) and [NER_IMPLEMENTATION_REPORT.md](NER_IMPLEMENTATION_REPORT.md). Existing extraction commands and schema remain compatible. New results are in `new_structured_results/`. The 95% unseen-accuracy target is not established.

# Resume extraction engine — version 3

This update fixes the failure classes found in the supplied resume audit. It runs locally using layout and text rules, with local OCR fallback. No language model, external API or runtime network request is used.

**Measured development-set field F1: 100.00%, up from 88.38%.** The 20 supplied files contain 16 byte-distinct documents. All 732 labeled field claims match, all 104 reviewed job bullets match in full, and all 44 tests pass. These files guided development: this result does **not** establish 95% accuracy on unseen resumes. See `reports/V3_AUDIT_REPORT.md` for scope, evidence and remaining limitations.

## Open your results

- `results/INDEX.md` maps each original resume to its result folder.
- `results/R01/structured.txt` is the current Jayavarapu PDF in readable structured text.
- Each `results/R01` through `results/R20` folder contains `structured.json`, `structured.txt`, `structured.md`, `resume.json`, `resume.md`, `raw.txt`, `normalized.txt`, `source.txt` and `quality.json`.
- `STRUCTURED_OUTPUT_GUIDE.md` describes fields, order and database use.
- `history/v2/` retains prior outputs and reports for comparison. They are historical, not the current results. The earlier saved Jayavarapu JSON describes a different resume version and is retained separately there.

## Run on another resume

Python 3.10+ is required; validation used Python 3.12.

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m resume_extract /path/to/resume.pdf --out new_results
python -m resume_extract /path/to/resume_folder --out new_results
```

The CLI accepts PDF, DOCX, legacy DOC and text. Add `--include-txt` for a folder of text files. Unpack ZIPs first. Each input receives a separate output directory and a record in `batch_summary.json`. Use the original PDF/DOCX when available: text/Markdown cannot recover missing coordinates or invisible link destinations.

System dependencies: Poppler (`pdftotext`, `pdffonts`, `pdftoppm`); Tesseract with the configured language for scanned PDFs; LibreOffice for legacy DOC conversion. Real legacy DOC conversion was not integration-tested because LibreOffice was unavailable. OCR is flagged as not independently verifiable.

You can also install with `python -m pip install .` and run `resume-extract`. Pass `--config config.yaml` to use edited settings; otherwise packaged defaults are used. The two shipped configurations are identical.

A strict completeness failure returns exit status 1 while still saving results and continuing the batch. The supplied R01 has one known decorative PDF icon mismatch and remains flagged; the threshold has not been weakened.

## Reproduce validation

```bash
python -m unittest discover -s tests
python validation/reproducibility/run_benchmark.py
```

The benchmark verifies original input SHA-256 hashes, performs fresh extraction, scores frozen labels, and separately checks complete bullet strings. Its field acceptance gate is 95% F1 on both all-file and deduplicated aggregates, plus zero schema errors. Raw completeness remains a separate reported gate; the known icon mismatch is not converted to a pass.

To score saved outputs only:

```bash
python validation/reproducibility/score_audit.py --min-f1 0.95
python validation/reproducibility/score_bullets.py
```

The engine never imports audit labels. Scoring reads the new project date/technology fields while preserving the prior audit's exact matching method. `validation/audit/scorer_compatibility.json` shows that the updated adapter reproduces the original v2 score exactly.

## Changes

- Recognize Computer Modern bold fonts, dash bullets, and wrapped bullet endings beginning with numbers or capital letters.
- Recover PDF hyperlink destinations and broader portfolio URLs; handle country-code phone formatting and CGPA.
- Separate employer/location and institution/location fields while keeping source evidence.
- Keep education degree, institution, graduation and GPA apart in layout tables.
- Preserve balanced parentheses in lists and associate skills with their table-column category.
- Extract project names, dates and explicit technologies; distinguish mixed awards/certifications and inline credentials.
- Preserve raw text, source section order, ambiguous values and review flags.

Schema version is `3.0.0`. Projects now require `dates` and `technologies`; URL kinds include `website`; section types include `awards_and_certifications`. Review `resume_extract/schema.json` when upgrading a strict consumer. Confidence values remain heuristic rule scores, not probabilities of correctness.
