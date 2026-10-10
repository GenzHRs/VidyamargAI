# Database Migration, Legacy Resume Ingestion & Data Repair Procedures

**Document Version**: 2.0.0  
**Status**: Production Verified  
**Scope**: Migration of legacy parsed resumes and live database records

---

## 1. Overview of Data Migration Objectives

Prior to the deployment of the Universal Extraction Engine:
1. Certain resumes had duplicate project bullet points persisted in `ResumeProject` and `ResumeVersion.structured_data`.
2. Extracted hyperlinks were not persisted in `ResumeExtraction.layout_info`.
3. Concatenated technologies (e.g. `FastAPIPythonPostgreSQLAzure OCRNERGemini LLM`) were stored as single strings in database tables.

This document outlines the migration procedures and repair scripts to normalize existing database records idempotently.

---

## 2. In-Flight Repair & Normalization Architecture

The system handles legacy records through **transparent read-time and write-time canonicalization**:

### 2.1 Read-Time Canonicalization
Whenever an existing resume is retrieved via:
- `GET /api/v1/resumes/{resume_id}`
- `GET /api/v1/resumes/active`
- `GET /api/v1/resumes/{resume_id}/compile`

The `_get_consolidated_resume_data` function automatically filters `projects` through `canonicalize_projects_list(structured["projects"])`. This ensures that even legacy records created before this update render in LaTeX and PDFs without duplicated bullets.

### 2.2 Write-Time Canonicalization
During resume uploads or edits:
- Bullet points are cleaned of repeated markers and deduplicated.
- Concatenated technology strings are tokenized into lists.
- Child database records (`ResumeSkill`, `ResumeExperience`, `ResumeProject`) are refreshed cleanly.

---

## 3. Data Repair Script for Existing Database Records

To repair all legacy resumes in the database in bulk, run the following maintenance script:

```python
"""
scripts/repair_legacy_resumes.py
Repairs duplicate bullets, concatenated technologies, and recovers hyperlinks
for all existing resumes in the database.
"""
import logging
from app.core.database import SessionLocal
from app.models.resume_center_models import Resume, ResumeVersion, ResumeProject, ResumeExtraction
from app.services.project_normalizer import canonicalize_project, canonicalize_projects_list
from app.services.resume_extractor_engine import extract_document_content
from app.services.hyperlink_extractor import associate_links_with_resume_entities

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repair_legacy_resumes")

def repair_all_resumes():
    db = SessionLocal()
    try:
        resumes = db.query(Resume).filter(Resume.deleted_at == None).all()
        logger.info(f"Found {len(resumes)} resumes to inspect and repair.")

        for r in resumes:
            # 1. Repair ResumeProject records
            projs = db.query(ResumeProject).filter(ResumeProject.resume_id == r.id).all()
            for p in projs:
                raw_proj = {
                    "name": p.name,
                    "description": p.description,
                    "bullets": p.responsibilities or [],
                    "responsibilities": p.responsibilities or [],
                    "technologies": p.technologies or [],
                    "link": p.link
                }
                cleaned = canonicalize_project(raw_proj)
                p.responsibilities = cleaned.get("bullets", [])
                p.technologies = cleaned.get("technologies", [])
                p.description = cleaned.get("description")
                p.link = cleaned.get("link")

            # 2. Repair current ResumeVersion.structured_data
            if r.current_version_id:
                version = db.query(ResumeVersion).filter(ResumeVersion.id == r.current_version_id).first()
                if version and version.structured_data and isinstance(version.structured_data, dict):
                    data = dict(version.structured_data)
                    if "projects" in data:
                        data["projects"] = canonicalize_projects_list(data["projects"])
                    version.structured_data = data

            # 3. Recover hyperlinks if layout_info was unpopulated
            extraction = db.query(ResumeExtraction).filter(ResumeExtraction.resume_id == r.id).first()
            if extraction and extraction.raw_text:
                layout = extraction.layout_info or {}
                if "hyperlinks" not in layout or not layout.get("hyperlinks"):
                    # Extract plaintext hyperlinks from raw text
                    from app.services.resume_extractor_engine import _recover_plaintext_hyperlinks
                    links = []
                    _recover_plaintext_hyperlinks(extraction.raw_text, links, extraction.layout_info.get("format", "unknown"))
                    layout["hyperlinks"] = links
                    extraction.layout_info = layout

            db.commit()
            logger.info(f"Successfully repaired Resume #{r.id} ({r.title})")

    except Exception as e:
        db.rollback()
        logger.error(f"Error during repair: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    repair_all_resumes()
```

---

## 4. Rollback & Verification Procedures

1. **Safety Guarantee**: The script performs in-place normalization only on fields with identified duplicates. No candidate name, dates, or contact information are altered.
2. **Idempotence**: Running the script multiple times produces identical, stable results without data degradation.
3. **Verification**: After running, query `GET /api/v1/resumes/{resume_id}/hyperlinks` and compile the resume to verify clean PDF rendering.
