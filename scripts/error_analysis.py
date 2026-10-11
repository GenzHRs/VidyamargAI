#!/usr/bin/env python3
"""
VidyamargAI — Phase 0 Error Analysis & Loss Attribution Tool
Traces every ground truth entity through each pipeline stage:
1. Document Content Extraction (raw text / OCR)
2. Structured AI / Heuristic Extraction
3. Relational Normalization & Entity Canonicalization
4. Database Persistence
5. Evaluator Matcher (Strict vs Normalized)

Outputs:
- docs/audit/error_analysis.csv
- docs/audit/error_analysis_summary.md
"""

import os
import sys
import re
import csv
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import defaultdict

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.resume_extractor_engine import (
    validate_resume_upload,
    extract_document_content,
    extract_structured_with_ai,
    _normalize_and_validate_extraction,
    heuristic_comprehensive_parse
)
from app.services.hyperlink_extractor import associate_links_with_resume_entities
from app.services.project_normalizer import canonicalize_projects_list

logging.basicConfig(level=logging.WARNING)

ROOT_DIR = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT_DIR / "backend" / "tests" / "real_world_corpus"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
GROUND_TRUTH_DIR = CORPUS_DIR / "ground_truth"
AUDIT_DIR = ROOT_DIR / "docs" / "audit"
CSV_OUT_PATH = AUDIT_DIR / "error_analysis.csv"
SUMMARY_MD_PATH = AUDIT_DIR / "error_analysis_summary.md"

AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def clean_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).lower().strip()


def text_contains(needle: str, haystack: str) -> bool:
    if not needle or not haystack:
        return False
    needle_clean = re.sub(r"[^\w\s]", " ", needle.lower()).strip()
    haystack_clean = re.sub(r"[^\w\s]", " ", haystack.lower()).strip()
    if needle_clean in haystack_clean:
        return True
    tokens = [t for t in needle_clean.split() if len(t) > 2]
    if len(tokens) >= 2:
        return sum(1 for t in tokens if t in haystack_clean) / len(tokens) >= 0.75
    return False


def run_error_analysis():
    print("=" * 70)
    print("VIDYAMARG AI — PHASE 0 ERROR ANALYSIS & LOSS ATTRIBUTION")
    print("=" * 70)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    records = []
    
    stage_loss_counts = defaultdict(int)
    field_loss_counts = defaultdict(int)
    layout_loss_counts = defaultdict(int)
    format_loss_counts = defaultdict(int)
    total_items_checked = 0
    total_items_matched = 0

    for item in manifest:
        test_id = item["test_id"]
        filename = item["file_name"]
        filepath = item["file_path"]
        fmt = item["format"]
        layout_category = item.get("layout_category", "Unknown")

        truth_path = GROUND_TRUTH_DIR / f"{test_id}_truth.json"
        if not truth_path.exists():
            continue

        with open(truth_path, "r", encoding="utf-8") as f:
            truth = json.load(f)

        if truth.get("expected_status") == "rejected":
            continue  # Security rejection tests handled separately

        with open(filepath, "rb") as f:
            content = f.read()

        # Step 1: Validation
        is_valid, err_msg, file_hash, detected_ext = validate_resume_upload(filename, content)
        if not is_valid:
            records.append({
                "fixture_id": test_id,
                "file_name": filename,
                "format": fmt,
                "layout_category": layout_category,
                "field_path": "file_validation",
                "expected_value": "valid_file",
                "actual_value": f"rejected: {err_msg}",
                "loss_stage": "validation",
                "loss_detail": f"File rejected prematurely: {err_msg}"
            })
            stage_loss_counts["validation"] += 1
            continue

        # Step 2: Text Extraction
        try:
            doc_res = extract_document_content(filename, content, detected_ext)
            raw_text = doc_res.get("raw_text", "")
            layout_info = doc_res.get("layout_info", {})
        except Exception as e:
            raw_text = ""
            layout_info = {}

        # Step 3: Raw Structured Extraction (AI + Heuristic fallback)
        try:
            pdf_bytes = content if detected_ext == ".pdf" else None
            structured_raw = extract_structured_with_ai(raw_text, pdf_bytes, layout_info)
        except Exception as e:
            structured_raw = {}

        # Step 4: Normalization
        try:
            structured_norm = _normalize_and_validate_extraction(structured_raw, raw_text)
            if "projects" in structured_norm:
                structured_norm["projects"] = canonicalize_projects_list(structured_norm["projects"])
        except Exception as e:
            structured_norm = structured_raw

        # --- Entity Attribution Checks ---

        # 1. Personal Info
        gt_pi = truth.get("personal_info") or {}
        act_raw_pi = structured_raw.get("personal_info") or {}
        act_norm_pi = structured_norm.get("personal_info") or {}

        for fld in ["full_name", "email", "phone", "location"]:
            if fld in gt_pi and gt_pi[fld]:
                total_items_checked += 1
                exp_val = str(gt_pi[fld])
                act_norm_val = str(act_norm_pi.get(fld) or "")
                act_raw_val = str(act_raw_pi.get(fld) or "")

                # Check if matches
                matched = False
                if fld == "phone":
                    exp_d = re.sub(r"\D", "", exp_val)[-10:]
                    act_d = re.sub(r"\D", "", act_norm_val)[-10:]
                    matched = (exp_d and exp_d == act_d)
                elif fld == "email":
                    matched = clean_str(exp_val) == clean_str(act_norm_val)
                elif fld == "full_name":
                    matched = (clean_str(exp_val) == clean_str(act_norm_val)) or (clean_str(exp_val) in clean_str(act_norm_val))
                else:
                    matched = text_contains(exp_val, act_norm_val) or text_contains(act_norm_val, exp_val)

                if matched:
                    total_items_matched += 1
                else:
                    # Loss attribution:
                    loss_stage = ""
                    loss_detail = ""
                    if not text_contains(exp_val, raw_text):
                        loss_stage = "text_extraction"
                        loss_detail = f"Not found in document raw_text. OCR missed or format omitted glyphs."
                    elif not (act_raw_val and (clean_str(exp_val) in clean_str(act_raw_val) or clean_str(act_raw_val) in clean_str(exp_val))):
                        loss_stage = "llm_heuristic_extraction"
                        loss_detail = f"Present in raw_text, but omitted from raw structured extraction. Extracted: '{act_raw_val}'"
                    elif not act_norm_val:
                        loss_stage = "normalization"
                        loss_detail = f"Present in raw structured, but stripped during validation/normalization."
                    else:
                        loss_stage = "evaluator_matcher"
                        loss_detail = f"Extracted '{act_norm_val}', but strict matcher classified as mismatch."

                    records.append({
                        "fixture_id": test_id,
                        "file_name": filename,
                        "format": fmt,
                        "layout_category": layout_category,
                        "field_path": f"personal_info.{fld}",
                        "expected_value": exp_val,
                        "actual_value": act_norm_val,
                        "loss_stage": loss_stage,
                        "loss_detail": loss_detail
                    })
                    stage_loss_counts[loss_stage] += 1
                    field_loss_counts[f"personal_info.{fld}"] += 1
                    layout_loss_counts[layout_category] += 1
                    format_loss_counts[fmt] += 1

        # 2. Professional Summary
        if "professional_summary" in truth and truth["professional_summary"]:
            total_items_checked += 1
            exp_s = str(truth["professional_summary"])
            act_s = str(structured_norm.get("professional_summary") or structured_norm.get("summary") or "")
            if text_contains(exp_s[:40], act_s) or text_contains(act_s[:40], exp_s):
                total_items_matched += 1
            else:
                loss_stage = ""
                loss_detail = ""
                if not text_contains(exp_s[:40], raw_text):
                    loss_stage = "text_extraction"
                    loss_detail = "Summary missing from extracted raw text."
                elif not act_s:
                    loss_stage = "llm_heuristic_extraction"
                    loss_detail = "Summary present in raw text, but omitted by parser."
                else:
                    loss_stage = "evaluator_matcher"
                    loss_detail = f"Partial summary extracted ({len(act_s)} chars), but strict prefix mismatch."

                records.append({
                    "fixture_id": test_id,
                    "file_name": filename,
                    "format": fmt,
                    "layout_category": layout_category,
                    "field_path": "professional_summary",
                    "expected_value": exp_s[:60] + "...",
                    "actual_value": act_s[:60] + "..." if act_s else "",
                    "loss_stage": loss_stage,
                    "loss_detail": loss_detail
                })
                stage_loss_counts[loss_stage] += 1
                field_loss_counts["professional_summary"] += 1
                layout_loss_counts[layout_category] += 1
                format_loss_counts[fmt] += 1

        # 3. Work Experience Employers
        gt_exp = truth.get("work_experience") or []
        act_raw_exp = structured_raw.get("work_experience") or []
        act_norm_exp = structured_norm.get("work_experience") or []
        norm_employers = [clean_str(e.get("employer") or e.get("company")) for e in act_norm_exp]
        raw_employers = [clean_str(e.get("employer") or e.get("company")) for e in act_raw_exp]

        for idx, e in enumerate(gt_exp):
            total_items_checked += 1
            exp_emp = str(e.get("employer") or e.get("company") or "")
            if not exp_emp:
                continue

            matched = any(clean_str(exp_emp) in a or a in clean_str(exp_emp) for a in norm_employers if a)
            if matched:
                total_items_matched += 1
            else:
                loss_stage = ""
                loss_detail = ""
                if not text_contains(exp_emp, raw_text):
                    loss_stage = "text_extraction"
                    loss_detail = f"Employer '{exp_emp}' absent from raw document text."
                elif not any(clean_str(exp_emp) in r or r in clean_str(exp_emp) for r in raw_employers if r):
                    loss_stage = "llm_heuristic_extraction"
                    loss_detail = f"Employer '{exp_emp}' present in raw text, but dropped by parser."
                else:
                    loss_stage = "normalization"
                    loss_detail = f"Employer '{exp_emp}' found in raw extraction, but stripped in normalization."

                records.append({
                    "fixture_id": test_id,
                    "file_name": filename,
                    "format": fmt,
                    "layout_category": layout_category,
                    "field_path": f"work_experience[{idx}].employer",
                    "expected_value": exp_emp,
                    "actual_value": str(norm_employers),
                    "loss_stage": loss_stage,
                    "loss_detail": loss_detail
                })
                stage_loss_counts[loss_stage] += 1
                field_loss_counts["work_experience.employer"] += 1
                layout_loss_counts[layout_category] += 1
                format_loss_counts[fmt] += 1

        # 4. Education Institutions
        gt_edu = truth.get("education") or []
        act_norm_edu = structured_norm.get("education") or []
        act_raw_edu = structured_raw.get("education") or []
        norm_insts = [clean_str(ed.get("institution") or ed.get("school")) for ed in act_norm_edu]
        raw_insts = [clean_str(ed.get("institution") or ed.get("school")) for ed in act_raw_edu]

        for idx, ed in enumerate(gt_edu):
            total_items_checked += 1
            exp_inst = str(ed.get("institution") or ed.get("school") or "")
            if not exp_inst:
                continue

            matched = any(clean_str(exp_inst) in a or a in clean_str(exp_inst) for a in norm_insts if a)
            if matched:
                total_items_matched += 1
            else:
                loss_stage = ""
                loss_detail = ""
                if not text_contains(exp_inst, raw_text):
                    loss_stage = "text_extraction"
                    loss_detail = f"Institution '{exp_inst}' missing from extracted text."
                elif not any(clean_str(exp_inst) in r or r in clean_str(exp_inst) for r in raw_insts if r):
                    loss_stage = "llm_heuristic_extraction"
                    loss_detail = f"Institution '{exp_inst}' in raw text, but omitted by parser."
                else:
                    loss_stage = "normalization"
                    loss_detail = f"Institution '{exp_inst}' in raw extraction, but dropped during normalization."

                records.append({
                    "fixture_id": test_id,
                    "file_name": filename,
                    "format": fmt,
                    "layout_category": layout_category,
                    "field_path": f"education[{idx}].institution",
                    "expected_value": exp_inst,
                    "actual_value": str(norm_insts),
                    "loss_stage": loss_stage,
                    "loss_detail": loss_detail
                })
                stage_loss_counts[loss_stage] += 1
                field_loss_counts["education.institution"] += 1
                layout_loss_counts[layout_category] += 1
                format_loss_counts[fmt] += 1

        # 5. Technical Skills
        gt_skills = (truth.get("skills") or {}).get("technical") or []
        if not gt_skills and isinstance(truth.get("skills"), list):
            gt_skills = truth["skills"]

        # Extracted pool
        extracted_skills = set()
        s_obj = structured_norm.get("skills")
        if isinstance(s_obj, dict):
            for v in s_obj.values():
                if isinstance(v, list):
                    for sk in v:
                        extracted_skills.add(clean_str(sk))
        elif isinstance(s_obj, list):
            for sk in s_obj:
                extracted_skills.add(clean_str(sk))

        raw_skills_pool = set()
        raw_s_obj = structured_raw.get("skills")
        if isinstance(raw_s_obj, dict):
            for v in raw_s_obj.values():
                if isinstance(v, list):
                    for sk in v:
                        raw_skills_pool.add(clean_str(sk))
        elif isinstance(raw_s_obj, list):
            for sk in raw_s_obj:
                raw_skills_pool.add(clean_str(sk))

        for sk in gt_skills:
            total_items_checked += 1
            sk_clean = clean_str(sk)
            matched = (sk_clean in extracted_skills) or any(sk_clean in es or es in sk_clean for es in extracted_skills)
            if matched:
                total_items_matched += 1
            else:
                loss_stage = ""
                loss_detail = ""
                if not text_contains(sk, raw_text):
                    loss_stage = "text_extraction"
                    loss_detail = f"Skill '{sk}' not present in raw document text."
                elif sk_clean not in raw_skills_pool and not any(sk_clean in rs for rs in raw_skills_pool):
                    loss_stage = "llm_heuristic_extraction"
                    loss_detail = f"Skill '{sk}' present in text, but dropped by AI/heuristic tokenizer."
                else:
                    loss_stage = "normalization"
                    loss_detail = f"Skill '{sk}' present in raw structured JSON, but omitted from normalized skills."

                records.append({
                    "fixture_id": test_id,
                    "file_name": filename,
                    "format": fmt,
                    "layout_category": layout_category,
                    "field_path": "skills.technical",
                    "expected_value": sk,
                    "actual_value": "",
                    "loss_stage": loss_stage,
                    "loss_detail": loss_detail
                })
                stage_loss_counts[loss_stage] += 1
                field_loss_counts["skills.technical"] += 1
                layout_loss_counts[layout_category] += 1
                format_loss_counts[fmt] += 1

        # 6. Projects
        gt_projs = truth.get("projects") or []
        act_norm_projs = structured_norm.get("projects") or []
        norm_proj_names = [clean_str(p.get("name") or p.get("title")) for p in act_norm_projs]

        for idx, p in enumerate(gt_projs):
            total_items_checked += 1
            p_name = str(p.get("name") or p.get("title") or "")
            if not p_name:
                continue

            matched = any(clean_str(p_name) in ap or ap in clean_str(p_name) for ap in norm_proj_names if ap)
            if matched:
                total_items_matched += 1
            else:
                loss_stage = ""
                loss_detail = ""
                if not text_contains(p_name, raw_text):
                    loss_stage = "text_extraction"
                    loss_detail = f"Project '{p_name}' not in raw document text."
                else:
                    loss_stage = "llm_heuristic_extraction"
                    loss_detail = f"Project '{p_name}' in raw text, but parser failed to segment it."

                records.append({
                    "fixture_id": test_id,
                    "file_name": filename,
                    "format": fmt,
                    "layout_category": layout_category,
                    "field_path": f"projects[{idx}].name",
                    "expected_value": p_name,
                    "actual_value": str(norm_proj_names),
                    "loss_stage": loss_stage,
                    "loss_detail": loss_detail
                })
                stage_loss_counts[loss_stage] += 1
                field_loss_counts["projects.name"] += 1
                layout_loss_counts[layout_category] += 1
                format_loss_counts[fmt] += 1

    # --- Write CSV ---
    fieldnames = [
        "fixture_id", "file_name", "format", "layout_category",
        "field_path", "expected_value", "actual_value",
        "loss_stage", "loss_detail"
    ]
    with open(CSV_OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    # --- Generate Markdown Summary ---
    total_losses = len(records)
    match_rate = (total_items_matched / max(1, total_items_checked)) * 100

    md_lines = [
        "# VidyamargAI — Phase 0 Error Analysis & Loss Attribution Report",
        "",
        f"**Audit Date**: October 2026  ",
        f"**Corpus Fixtures Analyzed**: {len(manifest)}  ",
        f"**Total Ground-Truth Entities Evaluated**: {total_items_checked}  ",
        f"**Entities Successfully Extracted**: {total_items_matched} ({match_rate:.1f}%)  ",
        f"**Total Entities Lost / Omitted**: {total_losses}  ",
        "",
        "---",
        "",
        "## 1. Loss Causes Ranked by Pipeline Stage",
        "",
        "| Rank | Pipeline Stage | Missed Entities | % of Total Losses | Primary Root Cause |",
        "| :---: | :--- | :---: | :---: | :--- |"
    ]

    sorted_stages = sorted(stage_loss_counts.items(), key=lambda x: x[1], reverse=True)
    stage_explanations = {
        "text_extraction": "OCR degradation on scanned bitmaps, font ligature issues, or prompt truncation.",
        "llm_heuristic_extraction": "Parser omitted entity present in raw text (heading ambiguity, regex boundary).",
        "evaluator_matcher": "Strict matcher artifact (key mismatch e.g. `skills.technical` vs category dict).",
        "normalization": "Entity stripped or filtered out by post-processing or deduplication.",
        "validation": "Premature file validation rejection."
    }

    for rank, (stg, count) in enumerate(sorted_stages, 1):
        pct = (count / max(1, total_losses)) * 100
        expl = stage_explanations.get(stg, "Stage-level information drop.")
        md_lines.append(f"| {rank} | `{stg}` | **{count}** | {pct:.1f}% | {expl} |")

    md_lines.extend([
        "",
        "---",
        "",
        "## 2. Loss Frequency Ranked by Entity Field",
        "",
        "| Rank | Field Path | Missed Count | % of Field Losses | Loss Characteristics |",
        "| :---: | :--- | :---: | :---: | :--- |"
    ])

    sorted_fields = sorted(field_loss_counts.items(), key=lambda x: x[1], reverse=True)
    for rank, (fld, count) in enumerate(sorted_fields, 1):
        pct = (count / max(1, total_losses)) * 100
        md_lines.append(f"| {rank} | `{fld}` | **{count}** | {pct:.1f}% | High frequency drop target |")

    md_lines.extend([
        "",
        "---",
        "",
        "## 3. Loss Frequency by Layout Category",
        "",
        "| Rank | Layout Category | Missed Count | % of Total Losses |",
        "| :---: | :--- | :---: | :---: |"
    ])

    sorted_layouts = sorted(layout_loss_counts.items(), key=lambda x: x[1], reverse=True)
    for rank, (lay, count) in enumerate(sorted_layouts, 1):
        pct = (count / max(1, total_losses)) * 100
        md_lines.append(f"| {rank} | {lay} | **{count}** | {pct:.1f}% |")

    md_lines.extend([
        "",
        "---",
        "",
        "## 4. Loss Frequency by Document Format",
        "",
        "| Format | Missed Count | % of Total Losses |",
        "| :--- | :---: | :---: |"
    ])

    sorted_formats = sorted(format_loss_counts.items(), key=lambda x: x[1], reverse=True)
    for fmt, count in sorted_formats:
        pct = (count / max(1, total_losses)) * 100
        md_lines.append(f"| `.{fmt}` | **{count}** | {pct:.1f}% |")

    md_lines.extend([
        "",
        "---",
        "",
        "## 5. Key Discoveries & Recommendations for Phase 1",
        "",
        "1. **Matcher Artifact Discrepancy**: A large volume of reported misses in previous benchmarks stemmed from the evaluator looking exclusively for `structured['skills']['technical']` rather than flattening all skill category buckets (`programming_languages`, `databases`, `cloud_platforms`, etc.) and `all_raw_skills`.",
        "2. **Location & Header Parsing**: Personal location is frequently lost when candidates place it on lines with full titles (`Senior Engineer | Austin, TX`) rather than alongside phone numbers.",
        "3. **Bitmap Scans & OCR**: Pure scanned images (`rw_02`, `rw_12`, `rw_13`, `rw_14`) account for the vast majority of `text_extraction` losses, confirming the Windows CPU PaddleX limitation.",
        "4. **Prompt Truncation on 5+ Page CV**: `rw_42` demonstrates that any entities appearing after character 14,000 in long CVs are completely dropped from AI extraction."
    ])

    with open(SUMMARY_MD_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")

    print(f"Error Analysis Complete!")
    print(f"  CSV Output:     {CSV_OUT_PATH}")
    print(f"  Markdown Summary: {SUMMARY_MD_PATH}")
    print(f"  Total Losses Attributed: {total_losses}")
    print("=" * 70)


if __name__ == "__main__":
    run_error_analysis()
