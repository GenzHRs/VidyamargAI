"""
Database Repair & Reprocessing Utility for Resume Projects.

Repairs duplicated description/bullet text and concatenated technology strings across:
1. ResumeVersion structured_data JSON & latex_source (the direct source for PDF compilation)
2. ResumeExtraction structured_data JSON
3. ResumeProject database records (responsibilities, features, description, technologies)
4. Candidate.projects JSON
5. Invalidates stale pre-compiled PDFs (resets latest_pdf_url and pdf_file_url)

Usage:
  # Dry-run (preview only, no DB modifications)
  python repair_resume_projects.py --dry-run

  # Apply repairs, save timestamped backup file, and invalidate stale PDF caches
  python repair_resume_projects.py --apply
"""

import sys
import os
import argparse
import json
from datetime import datetime
from typing import List, Dict, Any, Tuple, Set

# Add parent backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.core.database import SessionLocal
from app.models.resume_center_models import (
    Resume, ResumeProject, ResumeExtraction, ResumeVersion, ResumeTemplate
)
from app.models.models import Candidate
from app.services.project_normalizer import (
    canonicalize_project,
    canonicalize_projects_list,
    clean_bullet_text,
    normalize_technologies_list
)
from app.services.latex_service import render_resume_to_latex


def preview_project_change(source: str, record_id: Any, before_proj: Dict[str, Any], after_proj: Dict[str, Any]) -> None:
    """Prints clean before and after comparison preview."""
    p_name = before_proj.get('name') or before_proj.get('title') or before_proj.get('project_name') or "Untitled Project"
    print(f"\n================================================================================")
    print(f"[{source}] Record ID: {record_id} | Project: {p_name}")
    print(f"--------------------------------------------------------------------------------")
    print(f"BEFORE:")
    print(f"  Description    : {before_proj.get('description')}")
    before_bullets = before_proj.get('bullets') or before_proj.get('responsibilities') or []
    print(f"  Bullets ({len(before_bullets)} items):")
    for b in before_bullets:
        print(f"    - {b}")
    print(f"  Features       : {before_proj.get('features')}")
    print(f"  Technologies   : {before_proj.get('technologies') or before_proj.get('tech_stack')}")
    print(f"AFTER:")
    print(f"  Description    : {after_proj.get('description')}")
    after_bullets = after_proj.get('bullets') or []
    print(f"  Bullets ({len(after_bullets)} items):")
    for b in after_bullets:
        print(f"    - {b}")
    print(f"  Features       : {after_proj.get('features')}")
    print(f"  Technologies   : {after_proj.get('tech_stack') or after_proj.get('technologies')}")
    print(f"================================================================================\n")


def run_repair(apply_changes: bool = False, target_resume_id: int = None) -> None:
    session = SessionLocal()
    backup_data: Dict[str, List[Any]] = {
        "timestamp": datetime.utcnow().isoformat(),
        "resume_versions": [],
        "resume_projects": [],
        "resume_extractions": [],
        "candidate_projects": [],
        "invalidated_resumes": []
    }

    modified_counts = {
        "resume_versions": 0,
        "resume_projects": 0,
        "resume_extractions": 0,
        "candidate_projects": 0,
        "invalidated_resumes": 0
    }

    affected_resume_ids: Set[int] = set()

    try:
        # 1. Inspect ResumeVersion records (The direct data source consumed by PDF compilation)
        v_query = session.query(ResumeVersion)
        if target_resume_id:
            v_query = v_query.filter(ResumeVersion.resume_id == target_resume_id)
        versions = v_query.all()

        for ver in versions:
            s_data = ver.structured_data
            if not isinstance(s_data, dict) or "projects" not in s_data:
                continue

            raw_projs = s_data.get("projects") or []
            if not isinstance(raw_projs, list):
                continue

            canon_projs = canonicalize_projects_list(raw_projs)
            if canon_projs != raw_projs:
                modified_counts["resume_versions"] += 1
                affected_resume_ids.add(ver.resume_id)

                # Show preview for each changed project in this version
                for orig_p, new_p in zip(raw_projs, canon_projs):
                    if orig_p != new_p:
                        preview_project_change(f"ResumeVersion (v{ver.version_number})", ver.id, orig_p, new_p)

                backup_data["resume_versions"].append({
                    "version_id": ver.id,
                    "resume_id": ver.resume_id,
                    "version_number": ver.version_number,
                    "structured_data": ver.structured_data,
                    "latex_source": ver.latex_source,
                    "pdf_file_url": ver.pdf_file_url
                })

                if apply_changes:
                    updated_sd = dict(s_data)
                    updated_sd["projects"] = canon_projs
                    ver.structured_data = updated_sd

                    # Re-render LaTeX source for this version
                    resume_rec = session.query(Resume).filter(Resume.id == ver.resume_id).first()
                    tmpl = session.query(ResumeTemplate).filter(ResumeTemplate.id == resume_rec.template_id).first() if resume_rec else None
                    ver.latex_source = render_resume_to_latex(updated_sd, tmpl.latex_template if tmpl else "")

                    # Invalidate cached compiled PDF for this version
                    ver.pdf_file_url = None

        # 2. Inspect ResumeProject table records
        p_query = session.query(ResumeProject)
        if target_resume_id:
            p_query = p_query.filter(ResumeProject.resume_id == target_resume_id)
        db_projects = p_query.all()

        for proj in db_projects:
            proj_dict = {
                "name": proj.name,
                "description": proj.description,
                "responsibilities": proj.responsibilities or [],
                "bullets": proj.responsibilities or [],
                "features": proj.features or [],
                "technologies": proj.technologies or []
            }
            norm_proj = canonicalize_project(proj_dict)

            changed = (
                proj.description != norm_proj.get("description") or
                proj.responsibilities != norm_proj.get("bullets") or
                proj.features != [] or
                proj.technologies != norm_proj.get("technologies")
            )

            if changed:
                modified_counts["resume_projects"] += 1
                affected_resume_ids.add(proj.resume_id)
                preview_project_change("ResumeProject Table", proj.id, proj_dict, norm_proj)

                backup_data["resume_projects"].append({
                    "id": proj.id,
                    "resume_id": proj.resume_id,
                    "name": proj.name,
                    "description": proj.description,
                    "responsibilities": proj.responsibilities,
                    "features": proj.features,
                    "technologies": proj.technologies
                })

                if apply_changes:
                    proj.description = norm_proj.get("description")
                    proj.responsibilities = norm_proj.get("bullets")
                    proj.features = []
                    proj.technologies = norm_proj.get("technologies")

        # 3. Inspect ResumeExtraction records
        ext_query = session.query(ResumeExtraction)
        if target_resume_id:
            ext_query = ext_query.filter(ResumeExtraction.resume_id == target_resume_id)
        extractions = ext_query.all()

        for ext in extractions:
            s_data = ext.structured_data
            if not isinstance(s_data, dict) or "projects" not in s_data:
                continue

            projs = s_data.get("projects") or []
            if not isinstance(projs, list):
                continue

            canon_projs = canonicalize_projects_list(projs)
            if canon_projs != projs:
                modified_counts["resume_extractions"] += 1
                affected_resume_ids.add(ext.resume_id)

                for orig_p, new_p in zip(projs, canon_projs):
                    if orig_p != new_p:
                        preview_project_change("ResumeExtraction JSON", ext.id, orig_p, new_p)

                backup_data["resume_extractions"].append({
                    "id": ext.id,
                    "resume_id": ext.resume_id,
                    "structured_data_projects": projs
                })

                if apply_changes:
                    updated_data = dict(s_data)
                    updated_data["projects"] = canon_projs
                    ext.structured_data = updated_data

        # 4. Inspect Candidate.projects records
        if not target_resume_id:
            candidates = session.query(Candidate).all()
            for cand in candidates:
                if not cand.projects:
                    continue
                try:
                    cand_projs = json.loads(cand.projects) if isinstance(cand.projects, str) else cand.projects
                    if not isinstance(cand_projs, list):
                        continue

                    canon_cand_projs = canonicalize_projects_list(cand_projs)
                    if canon_cand_projs != cand_projs:
                        modified_counts["candidate_projects"] += 1
                        for orig_p, new_p in zip(cand_projs, canon_cand_projs):
                            if orig_p != new_p:
                                preview_project_change("Candidate.projects Field", cand.id, orig_p, new_p)

                        backup_data["candidate_projects"].append({
                            "candidate_id": cand.id,
                            "projects": cand.projects
                        })

                        if apply_changes:
                            cand.projects = json.dumps(canon_cand_projs)
                except Exception:
                    pass

        # 5. Invalidate cached generated PDF for affected resumes
        for r_id in affected_resume_ids:
            res_rec = session.query(Resume).filter(Resume.id == r_id).first()
            if res_rec and res_rec.latest_pdf_url:
                modified_counts["invalidated_resumes"] += 1
                backup_data["invalidated_resumes"].append({
                    "resume_id": res_rec.id,
                    "latest_pdf_url": res_rec.latest_pdf_url
                })
                print(f"[CACHE INVALIDATION] Resume ID {r_id}: invalidating stale latest_pdf_url ({res_rec.latest_pdf_url})")
                if apply_changes:
                    res_rec.latest_pdf_url = None
                    res_rec.status = "DRAFT"

        total_affected = sum(modified_counts.values())

        if apply_changes:
            if total_affected > 0:
                backup_dir = os.path.join(os.path.dirname(__file__), "backups")
                os.makedirs(backup_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = os.path.join(backup_dir, f"resume_projects_backup_{timestamp}.json")
                with open(backup_file, "w", encoding="utf-8") as f:
                    json.dump(backup_data, f, indent=2)

                session.commit()
                print(f"\n[APPLIED REPAIRS SUCCESSFULLY]")
                print(f"Saved backup of original data to: {backup_file}")
                print(f"Summary of modified records: {json.dumps(modified_counts, indent=2)}")
            else:
                print("\n[NO AFFECTED RECORDS FOUND] All existing records are already normalized and clean.")
        else:
            print(f"\n[DRY RUN COMPLETED]")
            print(f"Total affected records identified: {total_affected}")
            print(f"Breakdown by category: {json.dumps(modified_counts, indent=2)}")
            if total_affected > 0:
                print("Run with '--apply' to write backup, apply repairs, and invalidate stale PDF caches.")

    except Exception as e:
        session.rollback()
        print(f"Error during repair execution: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Repair duplicated project content & concatenated technologies in existing database records.")
    parser.add_argument("--apply", action="store_true", help="Apply changes to the database and write a backup file. Default is dry-run mode.")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode (default). Shows before/after previews without changing the database.")
    parser.add_argument("--resume-id", type=int, default=None, help="Optional specific resume ID to repair.")
    args = parser.parse_args()

    should_apply = args.apply and not args.dry_run
    run_repair(apply_changes=should_apply, target_resume_id=args.resume_id)
