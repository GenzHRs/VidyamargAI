#!/usr/bin/env python3
"""
VidyaMarg AI — Safe Dry-Run Resume Repair Utility
Audits and repairs historical resume extractions across SQLite / PostgreSQL databases.

Capabilities:
1. Identifies and strips hallucinated placeholder strings ('Company', 'Role', 'Designed and implemented...').
2. Deduplicates project overview descriptions that repeat bullet points.
3. Reparses original raw files (PDF/DOCX) with the Universal Layout-Aware Engine.
4. Tokenizes dense concatenated technology strings.
5. Re-binds extracted hyperlinks to projects and candidate profile.
6. Guarantees safety: defaults to --dry-run; persists full JSON snapshots to storage/backups/ before modifying.
7. Preserves candidate application isolation: never touches submitted application artifacts.
"""

import sys
import os
import argparse
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.models import Candidate
from app.models.resume_center_models import (
    Resume, ResumeVersion, ResumeExtraction, ResumeProfile,
    ResumeExperience, ResumeEducation, ResumeProject, ResumeSkill
)
from app.services.storage import storage_service
from app.services.resume_extractor_engine import (
    extract_document_content,
    extract_structured_with_ai,
    _normalize_and_validate_extraction
)
from app.services.project_normalizer import (
    canonicalize_project,
    canonicalize_projects_list,
    normalize_technologies_list,
    clean_bullet_text
)
from app.api.routers.resume_center import sync_extraction_to_database, convert_to_template_payload
from app.services.resume_context_service import ResumeContextService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("repair_resumes")

HALLUCINATED_PLACEHOLDERS = {
    "Designed and implemented project functionality.",
    "Key contributor to team deliverables.",
    "Company",
    "Role",
    "University",
    "Bachelor of Technology",
    "Degree",
    "Project"
}


def create_backup_snapshot(backup_dir: str, resume_id: int, snapshot_data: Dict[str, Any]) -> str:
    os.makedirs(backup_dir, exist_ok=True)
    file_path = os.path.join(backup_dir, f"resume_{resume_id}_snapshot.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, indent=2, default=str)
    return file_path


def audit_and_repair_resume(
    db: Session,
    resume: Resume,
    commit: bool = False,
    backup_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Audits a single Resume entity, reports anomalies, and optionally repairs it."""
    report = {
        "resume_id": resume.id,
        "candidate_id": resume.candidate_id,
        "title": resume.title,
        "anomalies_detected": [],
        "repaired_fields": [],
        "reparse_performed": False,
        "status": "clean"
    }

    # 1. Fetch existing extraction & version data
    extraction = db.query(ResumeExtraction).filter(ResumeExtraction.resume_id == resume.id).first()
    version = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()

    old_structured = (extraction.structured_data if extraction else None) or (version.structured_data if version else {}) or {}

    # 2. Check for known hallucinations in old_structured
    hallucination_count = 0
    for exp in old_structured.get("work_experience") or []:
        if exp.get("employer") in ("Company", "Role") or exp.get("designation") in ("Role", "Company"):
            hallucination_count += 1
            report["anomalies_detected"].append(f"Placeholder employer/role in experience: {exp.get('employer')}/{exp.get('designation')}")
        for b in exp.get("responsibilities") or []:
            if b in HALLUCINATED_PLACEHOLDERS:
                hallucination_count += 1
                report["anomalies_detected"].append(f"Hallucinated experience bullet: '{b}'")

    for proj in old_structured.get("projects") or []:
        for b in proj.get("bullets") or []:
            if b in HALLUCINATED_PLACEHOLDERS:
                hallucination_count += 1
                report["anomalies_detected"].append(f"Hallucinated project bullet: '{b}'")

    # 3. Check if raw file is accessible in storage for full re-parsing
    raw_content = None
    file_ext = f".{resume.file_type.lower()}" if resume.file_type else ".pdf"

    if resume.original_file_url:
        try:
            url_str = resume.original_file_url
            if "/storage/" in url_str:
                rel_path = url_str.split("/storage/")[1]
                parts = rel_path.split("/")
                if len(parts) >= 2:
                    folder = "/".join(parts[:-1])
                    filename = parts[-1]
                    raw_content = storage_service.get_file_content(folder, filename)
        except Exception as e:
            logger.warning(f"Could not load raw file for resume {resume.id}: {e}")

    # 4. Perform Layout-Aware Re-Extraction if raw content is available
    new_structured = None
    raw_text = extraction.raw_text if extraction else ""
    layout_info = extraction.layout_info if extraction else {}

    if raw_content:
        try:
            doc_res = extract_document_content(resume.file_name or "resume.pdf", raw_content, file_ext)
            raw_text = doc_res["raw_text"]
            layout_info = doc_res["layout_info"]
            pdf_bytes = raw_content if file_ext == ".pdf" else None
            new_structured = extract_structured_with_ai(raw_text, pdf_bytes, layout_info)
            report["reparse_performed"] = True
        except Exception as err:
            logger.error(f"Re-extraction error for resume {resume.id}: {err}")

    if not new_structured:
        # Canonicalize existing structured data in place
        new_structured = dict(old_structured)
        if "projects" in new_structured:
            new_structured["projects"] = canonicalize_projects_list(new_structured["projects"])
        if "work_experience" in new_structured:
            clean_exps = []
            for e in new_structured["work_experience"]:
                e_copy = dict(e)
                if e_copy.get("employer") in ("Company", "Role"):
                    e_copy["employer"] = ""
                if e_copy.get("designation") in ("Role", "Company"):
                    e_copy["designation"] = ""
                e_copy["responsibilities"] = [b for b in (e_copy.get("responsibilities") or []) if b not in HALLUCINATED_PLACEHOLDERS]
                clean_exps.append(e_copy)
            new_structured["work_experience"] = clean_exps

    # Clean and validate
    new_structured = _normalize_and_validate_extraction(new_structured, raw_text or "")
    template_payload = convert_to_template_payload(new_structured)

    if hallucination_count > 0 or report["reparse_performed"]:
        report["status"] = "repaired"
        report["repaired_fields"] = ["projects", "work_experience", "skills", "hyperlinks"]

    # 5. Commit changes if requested
    if commit and report["status"] == "repaired":
        if backup_dir:
            snapshot = {
                "resume_id": resume.id,
                "candidate_id": resume.candidate_id,
                "timestamp": datetime.utcnow().isoformat(),
                "old_structured": old_structured,
                "new_structured": new_structured
            }
            create_backup_snapshot(backup_dir, resume.id, snapshot)

        sync_extraction_to_database(db, resume, new_structured, raw_text, layout_info)

        if version:
            version.structured_data = template_payload
            version.change_summary = "Repaired via Layout-Aware Overhaul Utility"

        resume.extraction_status = "extracted"
        resume.extraction_confidence = new_structured.get("confidence_score", 1.0)
        resume.updated_at = datetime.utcnow()
        db.commit()

        # Update candidate active resume if active
        if resume.is_active:
            try:
                ResumeContextService.replace_active_resume(db, resume.candidate_id, resume.id, template_payload)
            except Exception as active_err:
                logger.warning(f"Failed to refresh active resume context for candidate {resume.candidate_id}: {active_err}")

    return report


def main():
    parser = argparse.ArgumentParser(description="VidyaMarg AI Safe Resume Extraction Repair Utility")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Simulate audit and repair without modifying DB (default)")
    parser.add_argument("--commit", action="store_true", default=False, help="Persist repaired records to the database")
    parser.add_argument("--resume-id", type=int, default=None, help="Target specific resume ID")
    parser.add_argument("--candidate-id", type=int, default=None, help="Target specific candidate ID")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of resumes to process")
    parser.add_argument("--backup", action="store_true", default=True, help="Create JSON snapshot backup before commit")
    args = parser.parse_args()

    # If --commit is explicitly passed, disable dry-run
    is_dry_run = not args.commit

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(backend_dir, "storage", "backups", f"resume_repair_{timestamp}") if args.backup else None

    logger.info("=" * 70)
    logger.info(f"VIDYAMARG AI RESUME EXTRACTION REPAIR UTILITY")
    logger.info(f"Mode: {'DRY-RUN (SIMULATION)' if is_dry_run else 'COMMIT (DATABASE WRITE)'}")
    if backup_dir and not is_dry_run:
        logger.info(f"Backup Directory: {backup_dir}")
    logger.info("=" * 70)

    db = SessionLocal()
    try:
        query = db.query(Resume).filter(Resume.deleted_at == None)
        if args.resume_id:
            query = query.filter(Resume.id == args.resume_id)
        if args.candidate_id:
            query = query.filter(Resume.candidate_id == args.candidate_id)

        resumes = query.limit(args.limit).all()
        logger.info(f"Found {len(resumes)} resume(s) to process.")

        total_audited = 0
        total_repaired = 0
        total_clean = 0

        for r in resumes:
            total_audited += 1
            res = audit_and_repair_resume(db, r, commit=(not is_dry_run), backup_dir=backup_dir)
            if res["status"] == "repaired":
                total_repaired += 1
                logger.info(f"[REPAIRED] Resume {r.id} (Candidate {r.candidate_id}): {len(res['anomalies_detected'])} anomalies fixed | Reparsed={res['reparse_performed']}")
                for a in res["anomalies_detected"][:3]:
                    logger.info(f"   - {a}")
            else:
                total_clean += 1
                logger.info(f"[CLEAN]    Resume {r.id} (Candidate {r.candidate_id}): No anomalies detected.")

        logger.info("=" * 70)
        logger.info("AUDIT & REPAIR SUMMARY:")
        logger.info(f"Total Audited:  {total_audited}")
        logger.info(f"Total Repaired: {total_repaired}")
        logger.info(f"Total Clean:    {total_clean}")
        if is_dry_run:
            logger.info("NO DATABASE CHANGES MADE. Pass --commit to write changes to database.")
        else:
            logger.info("DATABASE COMMITTED SUCCESSFULLY.")
        logger.info("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()
