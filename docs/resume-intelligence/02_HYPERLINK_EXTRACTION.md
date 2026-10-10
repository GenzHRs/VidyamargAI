# Hyperlink Preservation, Categorization & Entity Association Engine

**Document Version**: 2.0.0  
**Status**: Production Verified  
**Engine Reference**: `backend/app/services/hyperlink_extractor.py`

---

## 1. Problem Statement

Modern technical candidates frequently include critical portfolio links, code repositories, demo links, and credential verifications in their resumes:
- In PDFs, links are often embedded behind visual anchor text (e.g. text displays *"GitHub"*, but points to `https://github.com/candidate/repo`).
- Traditional text extractors discard annotation layers and only output the word *"GitHub"*, causing loss of the target URL.
- Other extractors extract raw URLs as flat text but fail to determine which project, company, or certification the link belongs to.

The VidyaMarg AI engine treats hyperlinks as **first-class structured entities** across all formats.

---

## 2. Canonical Hyperlink Schema

Every link discovered across PDF, DOCX, ODT, HTML, RTF, or plain text is standardized into the following record:

```json
{
  "url": "https://github.com/johndoe/distributed-cache",
  "label": "Source Code",
  "link_type": "project_repo",
  "source_format": "pdf",
  "source_page": 1,
  "nearby_text": "High-Throughput Distributed Cache | Built Raft consensus in Rust",
  "extraction_method": "pdf_uri_annotation",
  "validation_status": "valid",
  "associated_entity": "projects[High-Throughput Distributed Cache].link"
}
```

### Schema Attributes

1. `url` *(string)*: Standardized target URL. Guaranteed to include schema (`https://`), with stripped trailing punctuation and spaces.
2. `label` *(string)*: Exact visible text displayed on the resume page that candidate clicked.
3. `link_type` *(string)*: Semantic category derived from domain and context.
4. `source_format` *(string)*: Document format where the link was found (`pdf`, `docx`, `odt`, `html`, `rtf`, `txt`, `image`).
5. `source_page` *(integer)*: Page number where the link is located.
6. `nearby_text` *(string)*: Surrounding paragraph/block text (up to 300 characters) used for entity mapping.
7. `extraction_method` *(string)*: Detection technique (`pdf_uri_annotation`, `docx_relationship`, `odt_anchor`, `html_anchor`, `rtf_field`, `plaintext_regex`).
8. `validation_status` *(string)*: Syntactic and network security validation status (`valid`, `untrusted`, `malformed`, `empty`).
9. `associated_entity` *(string)*: Dot-notation pointer to the structured resume entity this link enriches (e.g., `personal_info.linkedin_url`, `projects[0].link`).

---

## 3. Semantic Link Classification

The engine classifies URLs into 9 distinct semantic types using domain intelligence and surrounding textual hints:

| `link_type` | Trigger Domain / Patterns | Label / Context Keywords | Destination Entity |
| :--- | :--- | :--- | :--- |
| `linkedin` | `linkedin.com/in/*`, `linkedin.com/pub/*` | "LinkedIn", "Profile" | `personal_info.linkedin_url` |
| `github` | `github.com/<username>` (profile root) | "GitHub", "Code" | `personal_info.github_url` |
| `portfolio` | `*.github.io`, `*.dev`, `*.me`, `*.vercel.app` | "Portfolio", "Website", "Personal Site" | `personal_info.portfolio_url` |
| `project_repo` | `github.com/<user>/<repo>`, `gitlab.com`, `bitbucket.org` | "Repo", "Source", "Code", "Repository" | `projects[<name>].link` or `repo_url` |
| `project_demo` | `*.vercel.app`, `*.netlify.app`, `*.render.com`, `*.live` | "Demo", "Live", "Preview", "App" | `projects[<name>].link` or `demo_url` |
| `credential` | `credly.com/*`, `coursera.org/verify/*`, `udemy.com/*` | "Credential", "Certificate", "Verify" | `certifications[<name>].credential_url` |
| `email` | `mailto:*`, raw regex emails | "Email", candidate email | `personal_info.email` |
| `phone` | `tel:*`, raw phone strings | "Phone", candidate phone | `personal_info.phone` |
| `social_profile` | `twitter.com`, `x.com`, `medium.com`, `kaggle.com`, `leetcode.com` | "Twitter", "LeetCode", "Kaggle" | `personal_info.custom_links` |

---

## 4. Extraction Mechanics by Format

### 4.1 PDF Spatial Bounding Box Clipping
PyMuPDF (`fitz`) exposes page-level URI annotations via `page.get_links()`. To recover the visible anchor text:
```python
link_rect = annotation["from"] # Rect(x0, y0, x1, y1)
padded_rect = fitz.Rect(
    max(0, link_rect.x0 - 2),
    max(0, link_rect.y0 - 2),
    min(page_width, link_rect.x1 + 2),
    min(page_height, link_rect.y1 + 2)
)
visible_label = page.get_text("text", clip=padded_rect).strip()
```
The ±2pt padding captures font descenders and anti-aliasing bounds.

### 4.2 DOCX OpenXML Relationship Resolution
In Word documents, hyperlinks are stored as `<w:hyperlink r:id="rId5">`. The relationship ID (`rId5`) is mapped against `document.part.rels` to retrieve the target URL, while run elements `<w:t>` inside the hyperlink tag provide the label.

### 4.3 ODT OpenDocument XML Linking
In OpenDocument XML, `<text:a xlink:href="https://...">label</text:a>` provides both the URL and the label in a single node.

### 4.4 HTML Semantic Anchor Tag Recovery
BeautifulSoup extracts `a[href]` attributes, decodes HTML entities, and extracts parent block text (`parent.get_text()`) for nearby context.

---

## 5. Entity Association Algorithm

The `associate_links_with_resume_entities` function runs automatically after extraction:
1. **Candidate Profile**: Unassigned `linkedin`, `github`, `portfolio`, and `email` links are assigned to `personal_info` if not already populated.
2. **Projects**: Links with type `project_repo` or `project_demo` are checked against candidate project titles using fuzzy name matching across `label` and `nearby_text`. Matching projects receive `project["link"] = url`.
3. **Certifications**: Credential URLs (e.g. Credly badges) are mapped to certifications whose names appear in the link label or nearby text.
4. **Custom Links**: Any remaining unique, valid link is attached to `personal_info["custom_links"]` as `{"label": label, "url": url}`.

---

## 6. Diagnostic API Endpoint

The platform exposes a dedicated diagnostic endpoint for inspecting extracted links:

```http
GET /api/v1/resumes/{resume_id}/hyperlinks
Authorization: Bearer <token>
```

### Response Example
```json
{
  "resume_id": 42,
  "total_hyperlinks": 4,
  "by_type": {
    "linkedin": 1,
    "github": 1,
    "project_repo": 1,
    "credential": 1
  },
  "by_validation_status": {
    "valid": 4
  },
  "hyperlinks": [
    {
      "url": "https://linkedin.com/in/alexrivera",
      "label": "LinkedIn Profile",
      "link_type": "linkedin",
      "source_format": "pdf",
      "source_page": 1,
      "validation_status": "valid",
      "associated_entity": "personal_info.linkedin_url"
    },
    {
      "url": "https://github.com/alexrivera/distributed-cache",
      "label": "GitHub Source",
      "link_type": "project_repo",
      "source_format": "pdf",
      "source_page": 1,
      "validation_status": "valid",
      "associated_entity": "projects[High-Throughput Distributed Cache].link"
    }
  ]
}
```
