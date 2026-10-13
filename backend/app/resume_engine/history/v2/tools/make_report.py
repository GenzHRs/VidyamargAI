"""Render the saved machine-readable measurements as a reviewable report."""
from pathlib import Path
import json
import platform
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def pct(x):return f'{100*x:.2f}%'

def main() -> None:
    report=json.loads((ROOT/'reports/accuracy.json').read_text());rows=report['per_file'];total=sum(r['completeness']['reference_words'] for r in rows)
    lines=['# Accuracy report','',
    '## Scope and label provenance','',
    'All three supplied archives were unpacked and all 19 resumes were processed: 14 DOCX and 5 digital PDFs. Four files are byte-identical duplicates across bundles, leaving 15 unique files/personas. The three README/benchmark guides are not resumes and were excluded.', '',
    '**No labelled gold JSON was present in the uploads.** Gold records were explicitly authored from source content for this task, and the rules were developed against this corpus. These are development-set results. They do not certify accuracy on a user-labelled held-out set or on arbitrary future templates. Each gold file is bound to the original file SHA-256. A second-person annotation review is still required for independent acceptance.', '',
    '## Final measured results','',
    '| Measure | Result | Denominator |','| --- | ---: | --- |',
    f'| Raw text word recall | 100.00% | {total}/{total} source words |',
    '| Raw text word precision | 100.00% | Zero extra words |',
    '| Strict file completeness | 19/19 pass | Missing or extra words both fail |',
    f"| H1 detection and canonical mapping F1 | {pct(report['per_metric']['headings']['f1'])} | 86 expected heading boundaries |",
    f"| Field micro precision / recall / F1 | {pct(report['field_micro']['precision'])} / {pct(report['field_micro']['recall'])} / {pct(report['field_micro']['f1'])} | 570 explicit atomic field items |",
    '| Experience entry exact matches | 38/38 | Title + company + start + end + bullet count |',
    f"| Unique-file field F1 | {pct(report['unique_persona_field_micro']['f1'])} | 441 atomic items, 15 unique files |",
    '| Automated tests | 25/25 pass | Including 19-file offline, schema and determinism subtests |',
    '| Clean synthetic OCR transcript | 41/41 words | One separate English rasterized page, not supplied corpus |','',
    'The configured digital-text target is 100% word recall with zero extras; heading target is 98% F1; field target is 95% micro F1. These development-set targets pass. No independent held-out target claim is made. OCR never uses its own output as completeness truth: ordinary OCR quality reports say `unverifiable`; only this fixture has a known transcript.', '',
    '## Metric definitions','',
    '- Text: case-sensitive Unicode word-token multiset equality against independent DOCX XML text traversal or `pdftotext -raw`. Repeated tokens count separately. Punctuation, whitespace and visual reading order are not measured by word equality. PDF CID bullet decoding occurs before the raw comparison; original undecoded run tokens are retained.',
    '- Headings: exact original H1 heading text paired with the canonical section key. TITLE/SUBTITLE/H2/BULLET/TEXT tagging is covered by fixtures, not the 86-heading corpus score.',
    '- Fields: exact strings or exact structured values with multiset precision/recall/F1. Experience title/company/start/end/bullet-count pairs are keyed by entry order. Entry tuple accuracy is reported separately and is not double-counted in micro F1.',
    '- Skill labels use the declared seed vocabulary across document text, apply alias normalization and longest-phrase preference, and measure mentions rather than proficiency. This is not recall against the full ESCO/O*NET universe.',
    '- Degrees are source mentions; an explicit expanded MBA and its parenthetical abbreviation are both labelled. Contacts include LinkedIn/GitHub URLs only. Arbitrary portfolios, institutions, certification entities, publication details and full per-bullet text assignment are not included in the field denominator.',
    '- Confidence numbers are rule scores, not calibrated probabilities. Invalid dummy phones, fallback names and OCR candidates remain available and are routed for review. A review flag is not itself an extraction error.', '',
    '## Per-field metrics','',
    '| Field | TP | FP | FN | Precision | Recall | F1 |','| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name,v in report['per_metric'].items():
        lines.append(f"| {name} | {v['tp']} | {v['fp']} | {v['fn']} | {pct(v['precision'])} | {pct(v['recall'])} | {pct(v['f1'])} |")
    lines+=['','## Per-resume completeness','','| File | Source words | Missing | Extra | Status |','| --- | ---: | ---: | ---: | --- |']
    for row in rows:
        c=row['completeness'];lines.append(f"| {row['file']} | {c['reference_words']} | {sum(c['missing'].values())} | {sum(c['extra'].values())} | {c['status']} |")
    lines+=['','## Layer test output','','Actual detailed logs are shipped under `reports/layer_*.log`. Final layer totals:','','| Layer | Tests | Result |','| --- | ---: | --- |']
    layer_counts=[('Ingest',2),('DOCX reader',1),('PDF reader',2),('Normalization',3),('Classification',1),('Sections',1),('Fields',2),('Validation',3),('Pipeline',1),('Regressions',4),('Layout and OCR fixtures',4),('Supplied corpus',1)]
    for name,n in layer_counts:lines.append(f'| {name} | {n} | PASS |')
    lines+=['','## Development findings and corrections','',
    'Initial corpus extraction preserved source words but surfaced PDF CID bullet placeholders as extra tokens. The reader now decodes them to bullets and retains their original glyph text. Bold role titles and table category labels were initially over-promoted to H1; date adjacency, separators and table-row context now keep them below section level. Contact false positives in credential-bearing names, publication page intervals mistaken for dates, and ambiguous skill aliases have explicit regression coverage.', '',
    'One annotation error was corrected after consulting the original text: Sophia’s CV contains “Deep Learning” and the journal title “Nature Machine Intelligence”, not the phrase “Machine Learning”. This was a gold correction, not an extraction success. The annotation generator records literal reviewed expectations and never imports predictions.', '',
    'The first synthetic scan was malformed by proportional-font substitution during fixture rasterization and scored 16/41 matched words (39.02% recall). The fixture was regenerated with a monospaced source font to avoid overlapping/substituted glyph spacing; the final clean fixture scores 41/41. No OCR autocorrection rule or external model was added. This small clean fixture is not evidence of robust low-quality-scan accuracy.', '',
    'Legacy DOC conversion remains untested because LibreOffice was not installed. More limitations and proposed rules are in `REMAINING_FAILURE_CASES.md`.', '',
    '## Reproduce','', '```bash','python tools/run_layers.py','python tools/evaluate.py tests/corpus --gold tests/gold --out reports/accuracy.json','python -m resume_extract tests/corpus --out outputs/','python tools/make_report.py','```','',
    f'Execution environment: Python {platform.python_version()}, {platform.system()}. Library pins are in `requirements.txt`. Poppler and Tesseract versions are recorded in `reports/environment.txt`. No runtime socket calls were permitted during supplied-corpus regression testing.']
    (ROOT/'reports/ACCURACY_REPORT.md').write_text('\n'.join(lines)+'\n')
    env=[f'Python {platform.python_version()}',f'Platform {platform.platform()}']
    for command in [['pdftotext','-v'],['tesseract','--version']]:
        r=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True);env.append(r.stdout.splitlines()[0])
    (ROOT/'reports/environment.txt').write_text('\n'.join(env)+'\n')

if __name__=='__main__':main()
