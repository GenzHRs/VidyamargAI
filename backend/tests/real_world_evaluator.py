#!/usr/bin/env python3
"""
VidyaMarg AI — Real-World Resume Extraction Evaluator & Benchmark Runner
Executes all 41 registered fixtures in `manifest.json` against the production pipeline:
1. File validation (`validate_resume_upload`)
2. Format-aware layout extraction (`extract_document_content`)
3. OCR processing for scanned content
4. Spatial hyperlink extraction & entity association (`associate_links_with_resume_entities`)
5. Layout-aware reading order & section classification
6. AI / heuristic structured extraction (`extract_structured_with_ai`)
7. Project & technology normalization (`canonicalize_projects_list`, `_normalize_and_validate_extraction`)
8. Database persistence in isolated test DB (`sync_extraction_to_database`)
9. Candidate profile / editor template payload conversion (`convert_to_template_payload`)
10. Resume PDF compilation (`render_structured_data_to_pdf`)
11. Text recovery from compiled PDF and verification of rendered content fidelity.
12. Comprehensive field-by-field classification and quantitative metrics computation.
"""

import os
import sys
import json
import logging
from typing import Dict, Any, List, Tuple
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import fitz  # PyMuPDF
from app.core.database import Base
from app.models.models import Candidate, User
from app.models.resume_center_models import (
    Resume, ResumeVersion, ResumeExtraction, ResumeProfile,
    ResumeExperience, ResumeEducation, ResumeProject, ResumeSkill
)
from app.services.resume_extractor_engine import (
    validate_resume_upload,
    extract_document_content,
    extract_structured_with_ai,
    _normalize_and_validate_extraction
)
from app.services.hyperlink_extractor import associate_links_with_resume_entities
from app.services.project_normalizer import canonicalize_projects_list
from app.api.routers.resume_center import sync_extraction_to_database, convert_to_template_payload
from app.services.latex_service import render_structured_data_to_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluator")

BASE_DIR = os.path.join(backend_dir, "tests", "real_world_corpus")
MANIFEST_PATH = os.path.join(BASE_DIR, "manifest.json")
GROUND_TRUTH_DIR = os.path.join(BASE_DIR, "ground_truth")
RESULTS_PATH = os.path.join(BASE_DIR, "evaluation_results.json")


def setup_in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def normalize_val(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        return " ".join(normalize_val(x) for x in val).lower().strip()
    return str(val).lower().strip()


def evaluate_single_fixture(fixture_meta: Dict[str, Any], db) -> Dict[str, Any]:
    test_id = fixture_meta["test_id"]
    filepath = fixture_meta["file_path"]
    filename = fixture_meta["file_name"]
    expected_format = fixture_meta["format"]

    truth_path = os.path.join(GROUND_TRUTH_DIR, f"{test_id}_truth.json")
    with open(truth_path, "r", encoding="utf-8") as f:
        truth = json.load(f)

    result = {
        "test_id": test_id,
        "file_name": filename,
        "format": expected_format,
        "layout_category": fixture_meta.get("layout_category", ""),
        "expected_status": truth.get("expected_status", "success"),
        "actual_status": "pending",
        "pipeline_stages_passed": [],
        "field_classifications": {},
        "metrics": {
            "fields_expected": 0,
            "fields_correct": 0,
            "fields_missing": 0,
            "fields_incorrect": 0,
            "fields_duplicated": 0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "strict_precision": 0.0,
            "strict_recall": 0.0,
            "strict_f1": 0.0,
            "normalized_precision": 0.0,
            "normalized_recall": 0.0,
            "normalized_f1": 0.0,
            "exact_match_score": 0.0,
            "hyperlink_precision": 1.0,
            "pdf_retention_rate": 0.0
        },
        "errors": []
    }

    # Load raw bytes
    try:
        with open(filepath, "rb") as f:
            content = f.read()
    except Exception as e:
        result["actual_status"] = "failed"
        result["errors"].append(f"Could not read test file: {e}")
        return result

    # 1. Validation Stage
    is_valid, err_msg, sha256_hash, detected_ext = validate_resume_upload(filename, content)

    if truth.get("expected_status") == "rejected":
        if not is_valid:
            result["actual_status"] = "success"
            result["pipeline_stages_passed"].append("rejection_validation")
            result["field_classifications"]["rejection_handling"] = "Correct"
            result["metrics"]["fields_expected"] = 1
            result["metrics"]["fields_correct"] = 1
            result["metrics"]["precision"] = 1.0
            result["metrics"]["recall"] = 1.0
            result["metrics"]["f1"] = 1.0
            result["metrics"]["strict_precision"] = 1.0
            result["metrics"]["strict_recall"] = 1.0
            result["metrics"]["strict_f1"] = 1.0
            result["metrics"]["normalized_precision"] = 1.0
            result["metrics"]["normalized_recall"] = 1.0
            result["metrics"]["normalized_f1"] = 1.0
            result["metrics"]["exact_match_score"] = 1.0
            return result
        else:
            result["actual_status"] = "failed"
            result["errors"].append(f"Expected file to be rejected, but validate_resume_upload returned is_valid=True")
            return result

    # For valid files:
    if not is_valid:
        result["actual_status"] = "failed"
        result["errors"].append(f"Validation unexpectedly failed: {err_msg}")
        return result
    result["pipeline_stages_passed"].append("file_validation")

    # 2. Document Content Extraction
    try:
        doc_res = extract_document_content(filename, content, detected_ext)
        raw_text = doc_res["raw_text"]
        layout_info = doc_res["layout_info"]
        result["pipeline_stages_passed"].append("document_extraction")
    except Exception as e:
        result["actual_status"] = "failed"
        result["errors"].append(f"extract_document_content error: {e}")
        return result

    # 3. Structured Extraction
    try:
        pdf_bytes = content if detected_ext == ".pdf" else None
        structured = extract_structured_with_ai(raw_text, pdf_bytes, layout_info)
        result["pipeline_stages_passed"].append("structured_extraction")
    except Exception as e:
        result["actual_status"] = "failed"
        result["errors"].append(f"extract_structured_with_ai error: {e}")
        return result

    # 4. Hyperlink Association
    try:
        raw_links = layout_info.get("hyperlinks", [])
        structured, enriched_links = associate_links_with_resume_entities(raw_links, structured)
        result["pipeline_stages_passed"].append("hyperlink_association")
    except Exception as e:
        result["errors"].append(f"Hyperlink association note: {e}")

    # 5. Normalization
    try:
        structured = _normalize_and_validate_extraction(structured, raw_text)
        if "projects" in structured:
            structured["projects"] = canonicalize_projects_list(structured["projects"])
        result["pipeline_stages_passed"].append("normalization")
    except Exception as e:
        result["errors"].append(f"Normalization note: {e}")

    # 6. Database Persistence in isolated test DB
    try:
        candidate = Candidate(id=1, email="test@candidate.com", full_name="Test Candidate")
        resume = Resume(
            id=fixture_meta.get("test_index", 1),
            candidate_id=candidate.id,
            title=filename,
            file_type=detected_ext.lstrip("."),
            file_name=filename,
            original_file_url=f"/storage/resumes/{filename}"
        )
        db.add(resume)
        db.flush()
        sync_extraction_to_database(db, resume, structured, raw_text, layout_info)
        db.commit()
        result["pipeline_stages_passed"].append("db_persistence")
    except Exception as e:
        db.rollback()
        result["errors"].append(f"Database persistence note: {e}")

    # 7. Resume Editor Template Payload
    try:
        template_payload = convert_to_template_payload(structured)
        result["pipeline_stages_passed"].append("template_payload_conversion")
    except Exception as e:
        result["errors"].append(f"Template payload note: {e}")
        template_payload = structured

    # 8. Resume PDF Compilation & Text Verification
    rendered_text = ""
    try:
        compiled_pdf = render_structured_data_to_pdf(template_payload, title=f"Compiled - {filename}")
        if compiled_pdf and compiled_pdf.startswith(b"%PDF"):
            result["pipeline_stages_passed"].append("pdf_compilation")
            # Extract text from rendered PDF
            pdf_doc = fitz.open(stream=compiled_pdf, filetype="pdf")
            rendered_text = "\n".join(page.get_text() for page in pdf_doc)
            pdf_doc.close()
            result["pipeline_stages_passed"].append("pdf_text_recovery")
    except Exception as e:
        result["errors"].append(f"PDF compilation note: {e}")

    # 9. Detailed Field-Level Comparison against Ground Truth
    fc = result["field_classifications"]
    m = result["metrics"]

    # (a) Personal Info
    gt_pi = truth.get("personal_info") or {}
    act_pi = structured.get("personal_info") or {}
    for fld in ["full_name", "email", "phone", "location"]:
        if fld in gt_pi and gt_pi[fld]:
            m["fields_expected"] += 1
            gt_val = normalize_val(gt_pi[fld])
            act_val = normalize_val(act_pi.get(fld))
            if gt_val == act_val:
                fc[f"personal_info.{fld}"] = "Correct"
                m["fields_correct"] += 1
            elif gt_val in act_val or act_val in gt_val:
                fc[f"personal_info.{fld}"] = "Partially Extracted"
                m["fields_correct"] += 0.8
            elif not act_val:
                fc[f"personal_info.{fld}"] = "Missing"
                m["fields_missing"] += 1
            else:
                fc[f"personal_info.{fld}"] = "Incorrect"
                m["fields_incorrect"] += 1

    # (b) Professional Summary
    if "professional_summary" in truth and truth["professional_summary"]:
        m["fields_expected"] += 1
        gt_s = normalize_val(truth["professional_summary"])
        act_s = normalize_val(structured.get("professional_summary") or structured.get("summary"))
        if gt_s and (gt_s[:30] in act_s or act_s[:30] in gt_s):
            fc["professional_summary"] = "Correct"
            m["fields_correct"] += 1
        elif act_s:
            fc["professional_summary"] = "Partially Extracted"
            m["fields_correct"] += 0.7
        else:
            fc["professional_summary"] = "Missing"
            m["fields_missing"] += 1

    # (c) Work Experience
    gt_exp = truth.get("work_experience") or []
    act_exp = structured.get("work_experience") or []
    if gt_exp:
        m["fields_expected"] += len(gt_exp)
        act_employers = [normalize_val(e.get("employer")) for e in act_exp]
        for idx, e in enumerate(gt_exp):
            gt_emp = normalize_val(e.get("employer"))
            f_key = f"experience[{idx}].{gt_emp[:15]}"
            match_found = any(gt_emp in a or a in gt_emp for a in act_employers if a)
            if match_found:
                fc[f_key] = "Correct"
                m["fields_correct"] += 1
            elif act_exp:
                fc[f_key] = "Partially Extracted"
                m["fields_correct"] += 0.5
            else:
                fc[f_key] = "Missing"
                m["fields_missing"] += 1

    # (d) Education
    gt_edu = truth.get("education") or []
    act_edu = structured.get("education") or []
    if gt_edu:
        m["fields_expected"] += len(gt_edu)
        act_insts = [normalize_val(ed.get("institution")) for ed in act_edu]
        for idx, ed in enumerate(gt_edu):
            gt_inst = normalize_val(ed.get("institution"))
            f_key = f"education[{idx}].{gt_inst[:15]}"
            match_found = any(gt_inst in a or a in gt_inst for a in act_insts if a)
            if match_found:
                fc[f_key] = "Correct"
                m["fields_correct"] += 1
            elif act_edu:
                fc[f_key] = "Partially Extracted"
                m["fields_correct"] += 0.5
            else:
                fc[f_key] = "Missing"
                m["fields_missing"] += 1

    # (e) Technical Skills
    gt_skills = (truth.get("skills") or {}).get("technical") or []
    act_skills = (structured.get("skills") or {}).get("technical") or []
    if not act_skills and isinstance(structured.get("skills"), list):
        act_skills = structured.get("skills")
    if gt_skills:
        m["fields_expected"] += 1
        gt_s_set = {normalize_val(s) for s in gt_skills}
        act_s_set = {normalize_val(s) for s in act_skills}
        overlap = len(gt_s_set.intersection(act_s_set))
        recall_rate = overlap / max(1, len(gt_s_set))
        if recall_rate >= 0.7:
            fc["skills.technical"] = "Correct"
            m["fields_correct"] += 1
        elif recall_rate > 0:
            fc["skills.technical"] = "Partially Extracted"
            m["fields_correct"] += recall_rate
        else:
            fc["skills.technical"] = "Missing"
            m["fields_missing"] += 1

    # (f) Hyperlinks
    gt_links = truth.get("hyperlinks") or []
    if gt_links:
        m["fields_expected"] += len(gt_links)
        act_links = layout_info.get("hyperlinks") or []
        act_urls = {normalize_val(l.get("url")) for l in act_links}
        for l in gt_links:
            expected_url = normalize_val(l.get("url"))
            link_key = f"hyperlink.{expected_url[:20]}"
            if any(expected_url in a or a in expected_url for a in act_urls):
                fc[link_key] = "Correct"
                m["fields_correct"] += 1
            else:
                fc[link_key] = "Missing"
                m["fields_missing"] += 1

    # (g) Generated PDF content verification
    if rendered_text and gt_pi.get("full_name"):
        norm_rendered = rendered_text.lower()
        name_present = gt_pi["full_name"].lower() in norm_rendered
        m["pdf_retention_rate"] = 1.0 if name_present else 0.5

    # Calculate overall strict metrics
    exp_f = max(1, m["fields_expected"])
    corr_f = m["fields_correct"]
    m["recall"] = round(corr_f / exp_f, 3)
    m["precision"] = round(corr_f / max(1, corr_f + m["fields_incorrect"]), 3)
    p, r = m["precision"], m["recall"]
    m["f1"] = round((2 * p * r) / max(0.001, (p + r)), 3)
    m["exact_match_score"] = round(corr_f / exp_f, 3)

    # Calculate normalized/fuzzy metrics side-by-side
    norm_m = compute_normalized_metrics(truth, structured, layout_info, rendered_text)
    result["normalized_metrics"] = norm_m
    m["strict_recall"] = m["recall"]
    m["strict_precision"] = m["precision"]
    m["strict_f1"] = m["f1"]
    m["normalized_recall"] = norm_m["recall"]
    m["normalized_precision"] = norm_m["precision"]
    m["normalized_f1"] = norm_m["f1"]

    result["actual_status"] = "success" if m["recall"] >= 0.65 else "partial"
    return result


def compute_normalized_metrics(
    truth: Dict[str, Any],
    structured: Dict[str, Any],
    layout_info: Dict[str, Any],
    rendered_text: str = ""
) -> Dict[str, Any]:
    """
    Computes normalized/fuzzy evaluation metrics.
    - Skills: checks against flattened all_raw_skills and all category lists in structured['skills'].
    - Phone: normalizes by digits (E.164 / last 10 digits).
    - Location: checks city / state / token containment.
    - Work Experience: checks employer, title, and token overlap.
    - Education: checks institution and degree.
    - Projects: checks project names and tech stack.
    - Hyperlinks: URL normalized (scheme & trailing slash agnostic).
    """
    import re
    nm = {
        "fields_expected": 0,
        "fields_correct": 0.0,
        "fields_missing": 0,
        "fields_incorrect": 0,
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0
    }

    if truth.get("expected_status") == "rejected":
        nm["fields_expected"] = 1
        nm["fields_correct"] = 1.0
        nm["precision"] = 1.0
        nm["recall"] = 1.0
        nm["f1"] = 1.0
        return nm

    # 1. Personal Info
    gt_pi = truth.get("personal_info") or {}
    act_pi = structured.get("personal_info") or {}

    if "full_name" in gt_pi and gt_pi["full_name"]:
        nm["fields_expected"] += 1
        gt_name = str(gt_pi["full_name"]).lower().strip()
        act_name = str(act_pi.get("full_name") or "").lower().strip()
        if gt_name == act_name:
            nm["fields_correct"] += 1.0
        elif gt_name in act_name or act_name in gt_name or any(p in act_name for p in gt_name.split() if len(p) > 2):
            nm["fields_correct"] += 0.8
        elif not act_name:
            nm["fields_missing"] += 1
        else:
            nm["fields_incorrect"] += 1

    if "email" in gt_pi and gt_pi["email"]:
        nm["fields_expected"] += 1
        gt_email = str(gt_pi["email"]).lower().strip()
        act_email = str(act_pi.get("email") or "").lower().strip()
        act_all_emails = [str(e).lower().strip() for e in act_pi.get("additional_emails", [])]
        if gt_email == act_email or gt_email in act_all_emails:
            nm["fields_correct"] += 1.0
        elif not act_email:
            nm["fields_missing"] += 1
        else:
            nm["fields_incorrect"] += 1

    if "phone" in gt_pi and gt_pi["phone"]:
        nm["fields_expected"] += 1
        gt_digits = re.sub(r"\D", "", str(gt_pi["phone"]))[-10:]
        act_digits = re.sub(r"\D", "", str(act_pi.get("phone") or ""))[-10:]
        act_add_digits = [re.sub(r"\D", "", str(p))[-10:] for p in act_pi.get("additional_phones", [])]
        if (gt_digits and gt_digits == act_digits) or (gt_digits and gt_digits in act_add_digits):
            nm["fields_correct"] += 1.0
        elif act_digits and (gt_digits in act_digits or act_digits in gt_digits):
            nm["fields_correct"] += 0.8
        elif not act_digits:
            nm["fields_missing"] += 1
        else:
            nm["fields_incorrect"] += 1

    if "location" in gt_pi and gt_pi["location"]:
        nm["fields_expected"] += 1
        gt_loc = str(gt_pi["location"]).lower().strip()
        act_loc = str(act_pi.get("location") or "").lower().strip()
        act_city = str(act_pi.get("city") or "").lower().strip()
        act_state = str(act_pi.get("state") or "").lower().strip()
        combined_act = f"{act_loc} {act_city} {act_state}".strip()
        gt_tokens = [t.strip(" ,.") for t in gt_loc.split() if len(t) > 1]
        match_count = sum(1 for t in gt_tokens if t in combined_act)
        if gt_loc in combined_act or combined_act in gt_loc:
            nm["fields_correct"] += 1.0
        elif match_count >= 1:
            nm["fields_correct"] += 0.8
        elif not act_loc and not act_city:
            nm["fields_missing"] += 1
        else:
            nm["fields_incorrect"] += 1

    # 2. Professional Summary
    if "professional_summary" in truth and truth["professional_summary"]:
        nm["fields_expected"] += 1
        gt_s = str(truth["professional_summary"]).lower().strip()
        act_s = str(structured.get("professional_summary") or structured.get("summary") or "").lower().strip()
        if gt_s[:30] in act_s or act_s[:30] in gt_s:
            nm["fields_correct"] += 1.0
        elif act_s and len(act_s) > 20:
            gt_words = set(re.findall(r"\w+", gt_s))
            act_words = set(re.findall(r"\w+", act_s))
            jaccard = len(gt_words & act_words) / max(1, len(gt_words | act_words))
            if jaccard >= 0.3:
                nm["fields_correct"] += 0.8
            else:
                nm["fields_correct"] += 0.5
        else:
            nm["fields_missing"] += 1

    # 3. Work Experience
    gt_exp = truth.get("work_experience") or []
    act_exp = structured.get("work_experience") or []
    if gt_exp:
        nm["fields_expected"] += len(gt_exp)
        act_employers = [str(e.get("employer") or e.get("company") or "").lower().strip() for e in act_exp]
        act_desigs = [str(e.get("designation") or e.get("role") or "").lower().strip() for e in act_exp]
        for e in gt_exp:
            gt_emp = str(e.get("employer") or e.get("company") or "").lower().strip()
            gt_desig = str(e.get("designation") or e.get("role") or "").lower().strip()
            emp_matched = any(gt_emp in a or a in gt_emp for a in act_employers if a)
            desig_matched = any(gt_desig in d or d in gt_desig for d in act_desigs if d)
            if emp_matched and desig_matched:
                nm["fields_correct"] += 1.0
            elif emp_matched:
                nm["fields_correct"] += 0.8
            elif act_exp:
                nm["fields_correct"] += 0.4
            else:
                nm["fields_missing"] += 1

    # 4. Education
    gt_edu = truth.get("education") or []
    act_edu = structured.get("education") or []
    if gt_edu:
        nm["fields_expected"] += len(gt_edu)
        act_insts = [str(ed.get("institution") or ed.get("school") or "").lower().strip() for ed in act_edu]
        act_degs = [str(ed.get("degree") or "").lower().strip() for ed in act_edu]
        for ed in gt_edu:
            gt_inst = str(ed.get("institution") or ed.get("school") or "").lower().strip()
            gt_deg = str(ed.get("degree") or "").lower().strip()
            inst_matched = any(gt_inst in a or a in gt_inst for a in act_insts if a)
            deg_matched = any(gt_deg in d or d in gt_deg for d in act_degs if d)
            if inst_matched and deg_matched:
                nm["fields_correct"] += 1.0
            elif inst_matched:
                nm["fields_correct"] += 0.8
            elif act_edu:
                nm["fields_correct"] += 0.4
            else:
                nm["fields_missing"] += 1

    # 5. Technical Skills (FLATTEN ALL CATEGORIES + RAW SKILLS)
    gt_skills = (truth.get("skills") or {}).get("technical") or []
    if not gt_skills and isinstance(truth.get("skills"), list):
        gt_skills = truth["skills"]

    extracted_skill_pool = set()
    raw_skills_val = structured.get("skills")
    if isinstance(raw_skills_val, dict):
        for k, v in raw_skills_val.items():
            if isinstance(v, list):
                for s in v:
                    if s:
                        extracted_skill_pool.add(str(s).lower().strip())
    elif isinstance(raw_skills_val, list):
        for s in raw_skills_val:
            if s:
                extracted_skill_pool.add(str(s).lower().strip())

    if gt_skills:
        nm["fields_expected"] += 1
        gt_norm = [str(s).lower().strip() for s in gt_skills]
        matches = 0
        for gs in gt_norm:
            if gs in extracted_skill_pool or any(gs in es or es in gs for es in extracted_skill_pool):
                matches += 1
        recall_rate = matches / max(1, len(gt_norm))
        if recall_rate >= 0.7:
            nm["fields_correct"] += 1.0
        elif recall_rate > 0:
            nm["fields_correct"] += round(recall_rate, 3)
        else:
            nm["fields_missing"] += 1

    # 6. Projects
    gt_projs = truth.get("projects") or []
    act_projs = structured.get("projects") or []
    if gt_projs:
        nm["fields_expected"] += len(gt_projs)
        act_proj_names = [str(p.get("name") or p.get("title") or "").lower().strip() for p in act_projs]
        for gp in gt_projs:
            gp_name = str(gp.get("name") or gp.get("title") or "").lower().strip()
            if any(gp_name in ap or ap in gp_name for ap in act_proj_names if ap):
                nm["fields_correct"] += 1.0
            elif act_projs:
                nm["fields_correct"] += 0.5
            else:
                nm["fields_missing"] += 1

    # 7. Hyperlinks
    gt_links = truth.get("hyperlinks") or []
    if gt_links:
        nm["fields_expected"] += len(gt_links)
        act_links = layout_info.get("hyperlinks") or []
        act_urls = {re.sub(r"^https?://", "", str(l.get("url") or "")).lower().rstrip("/") for l in act_links}
        for l in gt_links:
            exp_u = re.sub(r"^https?://", "", str(l.get("url") or "")).lower().rstrip("/")
            if any(exp_u in au or au in exp_u for au in act_urls if au):
                nm["fields_correct"] += 1.0
            else:
                nm["fields_missing"] += 1

    exp_f = max(1, nm["fields_expected"])
    corr_f = nm["fields_correct"]
    nm["recall"] = round(corr_f / exp_f, 3)
    nm["precision"] = round(corr_f / max(1, corr_f + nm["fields_incorrect"]), 3)
    p, r = nm["precision"], nm["recall"]
    nm["f1"] = round((2 * p * r) / max(0.001, (p + r)), 3)
    return nm


def run_full_evaluation():
    logger.info("=" * 70)
    logger.info("VIDYAMARG AI — REAL-WORLD RESUME EXTRACTION BENCHMARK RUNNER")
    logger.info("=" * 70)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    db = setup_in_memory_db()
    all_results = []
    total_expected = len(manifest)
    total_passed = 0
    total_partial = 0
    total_failed = 0

    format_metrics = {}

    for idx, item in enumerate(manifest, 1):
        item["test_index"] = idx
        res = evaluate_single_fixture(item, db)
        all_results.append(res)

        fmt = res["format"]
        if fmt not in format_metrics:
            format_metrics[fmt] = {
                "count": 0,
                "strict_recalls": [], "strict_precisions": [], "strict_f1s": [],
                "norm_recalls": [], "norm_precisions": [], "norm_f1s": []
            }
        format_metrics[fmt]["count"] += 1
        format_metrics[fmt]["strict_recalls"].append(res["metrics"]["strict_recall"])
        format_metrics[fmt]["strict_precisions"].append(res["metrics"]["strict_precision"])
        format_metrics[fmt]["strict_f1s"].append(res["metrics"]["strict_f1"])
        format_metrics[fmt]["norm_recalls"].append(res["metrics"]["normalized_recall"])
        format_metrics[fmt]["norm_precisions"].append(res["metrics"]["normalized_precision"])
        format_metrics[fmt]["norm_f1s"].append(res["metrics"]["normalized_f1"])

        if res["actual_status"] == "success":
            total_passed += 1
            status_tag = "[PASS]   "
        elif res["actual_status"] == "partial":
            total_partial += 1
            status_tag = "[PARTIAL]"
        else:
            total_failed += 1
            status_tag = "[FAIL]   "

        logger.info(f"{status_tag} {res['test_id']}: {res['file_name']} | Format: {fmt:5s} | Strict Recall: {res['metrics']['strict_recall']:.2f} | Norm Recall: {res['metrics']['normalized_recall']:.2f} | Norm F1: {res['metrics']['normalized_f1']:.2f}")

    db.close()

    # Aggregate Benchmark Report
    avg_strict_recall = sum(r["metrics"]["strict_recall"] for r in all_results) / total_expected
    avg_strict_precision = sum(r["metrics"]["strict_precision"] for r in all_results) / total_expected
    avg_strict_f1 = sum(r["metrics"]["strict_f1"] for r in all_results) / total_expected

    avg_norm_recall = sum(r["metrics"]["normalized_recall"] for r in all_results) / total_expected
    avg_norm_precision = sum(r["metrics"]["normalized_precision"] for r in all_results) / total_expected
    avg_norm_f1 = sum(r["metrics"]["normalized_f1"] for r in all_results) / total_expected

    benchmark_summary = {
        "timestamp": os.path.getmtime(MANIFEST_PATH),
        "total_fixtures": total_expected,
        "total_passed": total_passed,
        "total_partial": total_partial,
        "total_failed": total_failed,
        "pass_rate": round(total_passed / total_expected, 3),
        "overall_precision": round(avg_strict_precision, 3),
        "overall_recall": round(avg_strict_recall, 3),
        "overall_f1": round(avg_strict_f1, 3),
        "overall_strict_precision": round(avg_strict_precision, 3),
        "overall_strict_recall": round(avg_strict_recall, 3),
        "overall_strict_f1": round(avg_strict_f1, 3),
        "overall_normalized_precision": round(avg_norm_precision, 3),
        "overall_normalized_recall": round(avg_norm_recall, 3),
        "overall_normalized_f1": round(avg_norm_f1, 3),
        "format_breakdown": {
            fmt: {
                "count": data["count"],
                "strict_mean_recall": round(sum(data["strict_recalls"]) / data["count"], 3),
                "strict_mean_f1": round(sum(data["strict_f1s"]) / data["count"], 3),
                "normalized_mean_recall": round(sum(data["norm_recalls"]) / data["count"], 3),
                "normalized_mean_f1": round(sum(data["norm_f1s"]) / data["count"], 3)
            } for fmt, data in format_metrics.items()
        },
        "results": all_results
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(benchmark_summary, f, indent=2)

    logger.info("=" * 70)
    logger.info("EVALUATION BENCHMARK SUMMARY (STRICT vs NORMALIZED)")
    logger.info(f"Total Fixtures Tested: {total_expected}")
    logger.info(f"Passed:                {total_passed} ({total_passed/total_expected*100:.1f}%)")
    logger.info(f"Partial:               {total_partial}")
    logger.info(f"Failed:                {total_failed}")
    logger.info(f"Strict Mean Precision: {avg_strict_precision:.3f} | Normalized: {avg_norm_precision:.3f}")
    logger.info(f"Strict Mean Recall:    {avg_strict_recall:.3f} | Normalized: {avg_norm_recall:.3f}")
    logger.info(f"Strict Mean F1 Score:  {avg_strict_f1:.3f} | Normalized: {avg_norm_f1:.3f}")
    logger.info(f"Results saved to:      {RESULTS_PATH}")
    logger.info("=" * 70)

    return benchmark_summary


if __name__ == "__main__":
    run_full_evaluation()
