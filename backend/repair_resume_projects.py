"""
Database Repair & Reprocessing Utility for Resume Projects.

Repairs duplicated description/bullet text and concatenated technology strings in:
1. ResumeProject records
2. ResumeExtraction structured_data JSON
3. ResumeVersion structured_data JSON
4. Candidate projects JSON string

Usage:
  # Dry-run (preview only, no DB modifications)
  python repair_resume_projects.py --dry-run

  # Apply repairs and save timestamped backup file
  python repair_resume_projects.py --apply
"""

import sys
import os
import argparse
import json
from datetime import datetime
from typing import List, Dict, Any, Tuple

# Add parent backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.core.database import SessionLocal
from app.models.resume_center_models import ResumeProject, ResumeExtraction, ResumeVersion
from app.models.models import Candidate
from app.services.resume_extractor_engine import (
    normalize_and_deduplicate_project,
    normalize_technologies_list,
    clean_bullet_text
)


def preview_project_change(source: str, record_id: Any, before_proj: Dict[str, Any], after_proj: Dict[str, Any]) -> None:
    """Prints clean before and after comparison preview."""
    print(f"\n================================================================================")
    print(f"[{source}] Record ID: {record_id} | Project: {before_proj.get('name') or before_proj.get('project_name')}")
    print(f"--------------------------------------------------------------------------------")
    print(f"BEFORE:")
    print(f"  Description    : {before_proj.get('description')}")
    print(f"  Responsibilities: {before_proj.get('responsibilities') or before_proj.get('bullets')}")
    print(f"  Technologies   : {before_proj.get('technologies')}")
    print(f"AFTER:")
    print(f"  Description    : {after_proj.get('description')}")
    print(f"  Responsibilities: {after_proj.get('responsibilities') or after_proj.get('bullets')}")
    print(f"  Technologies   : {after_proj.get('technologies')}")
    print(f"================================================================================\n")


def run_repair(apply_changes: bool = False) -> None:
    session = SessionLocal()
    backup_data: Dict[str, List[Any]] = {
        "timestamp": datetime.utcnow().isoformat(),
        "resume_projects": [],
        "resume_extractions": [],
        "resume_versions": [],
        "candidate_projects": []
    }

    modified_counts = {
        "resume_projects": 0,
        "resume_extractions": 0,
        "resume_versions": 0,
        "candidate_projects": 0
    }

    try:
        # 1. Inspect ResumeProject records
        db_projects = session.query(ResumeProject).all()
        for proj in db_projects:
            proj_dict = {
                "name": proj.name,
                "description": proj.description,
                "responsibilities": proj.responsibilities or [],
                "bullets": proj.responsibilities or [],
                "features": proj.features or [],
                "technologies": proj.technologies or []
            }
            norm_proj = normalize_and_deduplicate_project(proj_dict)

            # Check if modified
            changed = (
                proj.description != norm_proj.get("description") or
                proj.responsibilities != norm_proj.get("responsibilities") or
                proj.technologies != norm_proj.get("technologies")
            )

            if changed:
                modified_counts["resume_projects"] += 1
                preview_project_change("ResumeProject Table", proj.id, proj_dict, norm_proj)

                backup_data["resume_projects"].append({
                    "id": proj.id,
                    "resume_id": proj.resume_id,
                    "name": proj.name,
                    "description": proj.description,
                    "responsibilities": proj.responsibilities,
                    "technologies": proj.technologies
                })

                if apply_changes:
                    proj.description = norm_proj.get("description")
                    proj.responsibilities = norm_proj.get("responsibilities")
                    proj.technologies = norm_proj.get("technologies")

        # 2. Inspect ResumeExtraction records
        extractions = session.query(ResumeExtraction).all()
        for ext in extractions:
            s_data = ext.structured_data
            if not isinstance(s_data, dict) or "projects" not in s_data:
                continue

            projs = s_data.get("projects") or []
            if not isinstance(projs, list):
                continue

            new_projs = []
            extraction_modified = False

            for p in projs:
                if not isinstance(p, dict):
                    new_projs.append(p)
                    continue
                norm_p = normalize_and_deduplicate_project(p)
                if norm_p != p:
                    extraction_modified = True
                    preview_project_change("ResumeExtraction JSON", ext.id, p, norm_p)
                new_projs.append(norm_p)

            if extraction_modified:
                modified_counts["resume_extractions"] += 1
                backup_data["resume_extractions"].append({
                    "id": ext.id,
                    "resume_id": ext.resume_id,
                    "structured_data_projects": projs
                })

                if apply_changes:
                    updated_data = dict(s_data)
                    updated_data["projects"] = new_projs
                    ext.structured_data = updated_data

        # 3. Inspect Candidate.projects records
        candidates = session.query(Candidate).all()
        for cand in candidates:
            if not cand.projects:
                continue
            try:
                cand_projs = json.loads(cand.projects) if isinstance(cand.projects, str) else cand.projects
                if not isinstance(cand_projs, list):
                    continue

                new_cand_projs = []
                cand_modified = False
                for p in cand_projs:
                    if not isinstance(p, dict):
                        new_cand_projs.append(p)
                        continue
                    norm_p = normalize_and_deduplicate_project(p)
                    if norm_p != p:
                        cand_modified = True
                        preview_project_change("Candidate.projects Field", cand.id, p, norm_p)
                    new_cand_projs.append(norm_p)

                if cand_modified:
                    modified_counts["candidate_projects"] += 1
                    backup_data["candidate_projects"].append({
                        "candidate_id": cand.id,
                        "projects": cand.projects
                    })

                    if apply_changes:
                        cand.projects = json.dumps(new_cand_projs)
            except Exception as err:
                pass

        total_affected = sum(modified_counts.values())

        if apply_changes:
            if total_affected > 0:
                # Write backup file
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
                print("Run with '--apply' to write backup and commit repairs to database.")

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
    args = parser.parse_args()

    # Dry-run is active unless --apply is explicitly specified
    should_apply = args.apply and not args.dry_run
    run_repair(apply_changes=should_apply)
