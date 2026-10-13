# Using the structured resume output

Run the engine on the original PDF or DOCX whenever possible. Plain text and
Markdown cannot recover coordinates, columns, table cells or invisible link
targets. A saved `resume.json` can be reprocessed because it retains raw lines,
page boxes and source provenance.

## Run on new resumes

Open a terminal inside the extracted `resume_engine` directory, install the
requirements once, then run:

```bash
python -m pip install -r requirements.txt
python -m resume_extract "C:/Resumes/candidate.pdf" --out results
python -m resume_extract "C:/Resumes" --out results
```

For Linux/macOS, use the corresponding file or folder path. Each input gets its
own result directory. It contains `structured.json`, `structured.md`,
`resume.json`, `resume.md`, `raw.txt`, `normalized.txt`, `source.txt` and
`quality.json`. The folder root also has `batch_summary.json`.

Reprocess the included saved example, without its original PDF:

```bash
python -m resume_extract tests/samples/uploaded_result.json --from-result --out results/uploaded_sample
```

Set `fields.default_phone_region` to `IN` in root `config.yaml` if you want
national phone numbers interpreted as Indian. Pass `--config config.yaml` to
use those edits. Explicit numbers such as `+919866862016` already contain their
country code. Local contiguous numbers without a country code are not currently
recognized by the supplied pattern; change the configurable pattern and test
it against postal codes and dates before enabling that broader rule.

## Stable application schema

| Key | Type | Contents |
| --- | --- | --- |
| `contact` | object | Name, emails, phones, locations, link targets actually present |
| `summary` | array | Summary paragraphs and evidence |
| `experience` | array | Title, company, location, dates, bullets, complete block text |
| `education` | array | Qualification, institution, date range, graduation, location, GPA |
| `projects` | array | Project name, description, bullets, complete block text |
| `skills` | array | Explicit resume categories and every listed item, without a vocabulary filter |
| `certifications` | array | Credential name, details, complete block text |
| `other_sections` | array | Publications, awards, languages and other sections |
| `source_sections` | array | All sections in corrected source order, including unparsed content |
| `section_order` | array | The order the UI should render sections |
| `review` | array | Missing/ambiguous candidates and source-quality issues |

Render `section_order` explicitly; JSON object key order is not a database
ordering contract. Entries within each section preserve source order, rather
than guessing chronology when dates are absent or overlapping. Raw reader order
and the original line coordinates remain in `resume.json`.

An evidence-backed value has this shape:

```json
{
  "value": "AI/ML Virtual Intern",
  "confidence": 0.65,
  "source_line_ids": ["l00018"]
}
```

These confidence numbers are rule scores, not calibrated probabilities.
`null` means missing or ambiguous, never a fabricated value. Date strings retain
the source's precision. A graduation year stays a graduation year; the engine
does not invent a start date, day, GPA scale, institution or employer.

```python
from resume_extract import extract
result = extract("candidate.pdf")
profile = result["structured"]
for education in profile["education"]:
    print(education["degree"]["value"], education["dates"]["value"])
for issue in profile["review"]:
    print(issue["path"], issue["reason"])
```

Suggested storage: one resume row keyed by the input SHA-256, the complete
`structured` JSON as a document/JSON column, and the full audit result separately.
If using child tables, store `resume_id`, section type, entry ordinal and source
line IDs for each entry. A human correction should preserve the machine result
and record the corrected value and reviewer separately.

## Changes verified in the uploaded example

- Email whitespace around `@` is normalized, with the original spelling retained.
- The international phone number is extracted.
- Three education entries receive their aligned dates and locations from page
  coordinates; their GPAs are attached to the correct entries.
- One internship has May 2023–July 2023 and four complete accomplishment bullets.
- Company remains null: AWS SageMaker is a tool mentioned in duties, not evidence
  of an employer.
- Two projects have five and four bullets respectively.
- Four skill categories retain 15 explicitly listed skills/tools.
- One certification retains the training details.
- LinkedIn/GitHub/CodeChef/HackerRank labels do not turn into invented URLs.

## Correctness and ML

The main observed failure was reading order. The correction moves date/location
fragments only when a metadata-only PDF region aligns with a unique text row;
it does not globally sort all lines by their vertical coordinate, which would
interleave true sidebars. Detached bullet glyphs are attached by geometry.
Tables keep their existing cell and row ownership. All original raw content is
retained. Unresolved content remains available through source sections.

No ML model was added. ML is an option after you supply representative, manually
labelled resumes, particularly if section labels or entry boundaries remain
unreliable. A future local classifier should produce evidence-backed candidates,
be tested on templates/candidates excluded from training, and retain a review
path for ambiguous cases. It cannot reconstruct information absent from an
input text dump or guarantee correctness on every template.

The new structure rules are heuristics. Dense nested layouts, mixed institutions
and credentials, overlapping dates, unusual institution names, undated jobs,
scans, and missing hyperlinks still need review. Do not equate a valid JSON
schema or word-completeness pass with correct field assignment. Use a held-out
labelled set to measure degree/institution/date grouping, job assignment,
project boundaries, section order and field precision/recall separately.
