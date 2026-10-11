"""
Resume Center API Router — Complete production endpoints for:
- Resumes CRUD and multi-resume management
- Multi-format file upload (PDF, DOCX, TXT, TEX)
- Overleaf-compatible LaTeX templates
- Versioning, autosave, diff comparison, and version restore
- Secure LaTeX compilation and private PDF/TeX downloads
- JD-based tailoring with strict zero-hallucination guarantees and explicit approval
"""
import io
import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from urllib.parse import quote

logger = logging.getLogger("app.resume_center")

from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request, Response, status
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.limiter import limiter
from app.core.security import get_current_user
from app.models.models import User, Candidate
from app.models.resume_center_models import (
    Resume, ResumeVersion, ResumeTemplate, JobDescription,
    ResumeExtraction, ResumeProfile, ResumeSkill, ResumeExperience,
    ResumeEducation, ResumeProject, ResumeCertification, ResumeSection,
    ResumeOptimization, ResumeOptimizationEvidence
)
from app.models.job_models import ResumeAIAnalysis
from app.services.storage import storage_service, get_user_folder_name
from app.services.latex_service import (
    escape_latex, render_resume_to_latex, compile_latex_to_pdf, is_latex_installed,
    render_structured_data_to_pdf
)
from app.services.ats_optimizer import run_full_jd_optimization, generate_optimized_docx
from app.services.resume_parser import (
    validate_resume_file, extract_text_from_file, parse_resume_to_structured
)
from app.services.resume_extractor_engine import (
    validate_resume_upload, extract_document_content,
    extract_structured_with_ai, heuristic_comprehensive_parse
)
from app.services.resume_tailor_service import (
    tailor_resume_to_jd, generate_jd_tailored_resume, TailoredResumeOutput
)
from app.services.resume_templates_data import seed_resume_templates
from app.services.resume_context_service import ResumeContextService
from app.services.project_normalizer import canonicalize_project, canonicalize_projects_list

router = APIRouter(tags=["Resume Center"])


# ─────────────────────────────────────────────────────────────────────────────
# PYDANTIC SCHEMAS
# ─────────────────────────────────────────────────────────────────────────────

class ResumeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255, default="My Professional Resume")
    template_id: Optional[int] = None
    structured_data: Dict[str, Any]


class ResumeUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    template_id: Optional[int] = None
    status: Optional[str] = None
    structured_data: Optional[Dict[str, Any]] = None
    change_summary: Optional[str] = None
    create_new_version: bool = False  # If false, updates current version in draft mode


class ResumeVersionCreateRequest(BaseModel):
    structured_data: Dict[str, Any]
    change_summary: Optional[str] = "Manual update"


class AnalyzeJDRequest(BaseModel):
    job_title: str = Field(min_length=1, max_length=255)
    company: str = Field(default="", max_length=255)
    job_description: str = Field(min_length=10)
    resume_id: Optional[int] = None


class GenerateTailoredResumeRequest(BaseModel):
    resume_id: int
    job_title: str = Field(min_length=1, max_length=255)
    company: str = Field(default="", max_length=255)
    job_description: str = Field(min_length=10)
    location: Optional[str] = None
    seniority: Optional[str] = None
    template_id: Optional[int] = None


class ApproveTailoringRequest(BaseModel):
    approved_resume_data: Dict[str, Any]
    change_summary: Optional[str] = "Approved tailored changes"
    create_new_resume: bool = True  # Default true: preserves original resume
    new_title: Optional[str] = None


class RenderTailoredTemplateRequest(BaseModel):
    source_resume_id: int
    selected_template_id: int
    tailored_resume_data: Dict[str, Any]


class SaveTailoredResumeRequest(BaseModel):
    source_resume_id: int
    selected_template_id: int
    tailored_resume_data: Dict[str, Any]
    job_title: str
    company_name: str
    job_description: str
    custom_title: Optional[str] = None


class SectionEnhanceRequest(BaseModel):
    section: str = Field(description="summary, experience_bullet, or project_description")
    text: str = Field(min_length=3, description="Original user text to enhance")
    context: Optional[str] = Field(default="", description="Role or project title context")


# ─────────────────────────────────────────────────────────────────────────────
# AUTHORIZATION & ACCESS HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_or_create_candidate(user: User, db: Session) -> Candidate:
    """Returns candidate profile for authenticated user, creating one if not present."""
    if user.candidate:
        return user.candidate
    cand = db.query(Candidate).filter(Candidate.user_id == user.id).first()
    if not cand:
        cand = Candidate(user_id=user.id, status="Active")
        db.add(cand)
        db.commit()
        db.refresh(cand)
    return cand


def _verify_resume_ownership(resume: Resume, user: User, candidate: Candidate) -> None:
    """Ensures resume belongs to candidate or user is administrator."""
    if user.role in ("admin", "super_admin"):
        return
    if resume.candidate_id != candidate.id or resume.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resume"
        )


def _sanitize_filename(name: str) -> str:
    """Strips path characters and keeps safe alphanumeric filename characters."""
    clean = re.sub(r"[^\w\s-]", "", name).strip().replace(" ", "_")
    return clean or "resume"


# ─────────────────────────────────────────────────────────────────────────────
# RESUME TEMPLATES ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/resume-templates")
def list_resume_templates(db: Session = Depends(get_db)):
    """Returns all active Overleaf-compatible LaTeX templates with metadata."""
    templates = db.query(ResumeTemplate).filter(ResumeTemplate.is_active == True).order_by(ResumeTemplate.id).all()
    if not templates:
        seed_resume_templates(db)
        templates = db.query(ResumeTemplate).filter(ResumeTemplate.is_active == True).order_by(ResumeTemplate.id).all()

    return [
        {
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "description": t.description,
            "category": t.category,
            "ats_score": t.ats_score,
            "license_name": t.license_name,
            "license_url": t.license_url,
            "preview_image": t.preview_image,
            "is_active": t.is_active,
        }
        for t in templates
    ]


@router.get("/resume-templates/{template_id}")
def get_resume_template(template_id: int, db: Session = Depends(get_db)):
    """Returns details and full LaTeX template source for a specific template."""
    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Resume template not found")
    return {
        "id": tmpl.id,
        "name": tmpl.name,
        "slug": tmpl.slug,
        "description": tmpl.description,
        "category": tmpl.category,
        "ats_score": tmpl.ats_score,
        "license_name": tmpl.license_name,
        "license_url": tmpl.license_url,
        "preview_image": tmpl.preview_image,
        "latex_template": tmpl.latex_template,
        "is_active": tmpl.is_active,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SINGLE ACTIVE RESUME ENDPOINTS (GLOBAL FOR ENTIRE PLATFORM)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/resumes/active")
def get_active_candidate_resume(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns candidate's SINGLE active resume context used across all features (Jobs, AI Agent, AI Mentor, Interview Room, Applications).
    """
    candidate = _get_or_create_candidate(current_user, db)
    resume, version, structured_data = ResumeContextService.get_active_resume(db, candidate.id)
    if not resume:
        return {
            "has_resume": False,
            "message": "Please upload or create your resume to continue.",
            "active_resume": None,
            "structured_data": None
        }

    target_roles_list = []
    if candidate.target_roles:
        try:
            target_roles_list = json.loads(candidate.target_roles)
        except Exception:
            target_roles_list = [candidate.primary_designation] if candidate.primary_designation else []

    role_evidence_list = []
    if candidate.role_evidence:
        try:
            role_evidence_list = json.loads(candidate.role_evidence)
        except Exception:
            role_evidence_list = []

    return {
        "has_resume": True,
        "active_resume": {
            "id": resume.id,
            "title": resume.title,
            "source_type": resume.source_type,
            "template_id": resume.template_id,
            "current_version_id": resume.current_version_id,
            "file_name": resume.file_name,
            "original_file_url": resume.original_file_url,
            "latest_pdf_url": resume.latest_pdf_url,
            "is_active": True,
            "status": resume.status,
            "created_at": resume.created_at.isoformat() if resume.created_at else None,
            "updated_at": resume.updated_at.isoformat() if resume.updated_at else None,
        },
        "primary_designation": candidate.primary_designation,
        "target_roles": target_roles_list,
        "role_evidence": role_evidence_list,
        "structured_data": structured_data,
        "version_number": version.version_number if version else 1,
        "candidate_id": candidate.id
    }


@router.post("/resumes/active/set/{resume_id}")
def set_active_candidate_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Explicitly sets a specific resume as the candidate's single active resume across the platform.
    """
    candidate = _get_or_create_candidate(current_user, db)
    try:
        updated_resume = ResumeContextService.set_active_resume(db, candidate.id, resume_id)
        return {
            "status": "success",
            "active_resume_id": updated_resume.id,
            "message": "Active resume updated and set globally across VidyamargAI"
        }
    except Exception as err:
        raise HTTPException(status_code=400, detail=str(err))


# ─────────────────────────────────────────────────────────────────────────────
# RESUMES CRUD & UPLOAD ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/resumes")
def list_candidate_resumes(
    search: Optional[str] = None,
    status_filter: Optional[str] = None,
    candidate_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns resumes owned by the authenticated candidate.
    Administrators may optionally filter by candidate_id.
    """
    candidate = _get_or_create_candidate(current_user, db)
    target_candidate_id = candidate.id
    if current_user.role in ("admin", "super_admin") and candidate_id:
        target_candidate_id = candidate_id

    query = db.query(Resume).filter(
        Resume.candidate_id == target_candidate_id,
        Resume.deleted_at == None
    ).options(
        joinedload(Resume.template),
        selectinload(Resume.versions)
    )

    if search:
        query = query.filter(Resume.title.ilike(f"%{search}%"))
    if status_filter:
        query = query.filter(Resume.status == status_filter)

    resumes = query.order_by(Resume.updated_at.desc()).all()

    response_list = []
    for r in resumes:
        latest_version = r.versions[0] if r.versions else None
        response_list.append({
            "id": r.id,
            "title": r.title,
            "source_type": r.source_type,
            "template_id": r.template_id,
            "template_name": r.template.name if r.template else "Standard",
            "current_version_id": r.current_version_id,
            "version_number": latest_version.version_number if latest_version else 1,
            "original_file_url": r.original_file_url,
            "latest_pdf_url": r.latest_pdf_url,
            "latest_tex_url": r.latest_tex_url,
            "status": r.status,
            "is_active": bool(r.is_active or (candidate.active_resume_id == r.id)),
            "is_verified": bool(r.is_verified),
            "extraction_status": r.extraction_status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })

    return Response(
        content=import_json_dumps(response_list),
        media_type="application/json",
        headers={"Cache-Control": "private, no-store, max-age=0"}
    )


def import_json_dumps(data: Any) -> str:
    import json
    return json.dumps(data)


def convert_to_template_payload(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Converts deep extracted JSON into template-compatible StructuredResumeData."""
    pi = extracted.get("personal_info") or {}
    ps = extracted.get("professional_summary") or {}
    summary_text = ps.get("summary") if isinstance(ps, dict) else str(ps or "")

    # Group skills into clean categories for template rendering
    skills_in = extracted.get("skills") or {}
    mapped_skills: Dict[str, List[str]] = {}
    label_map = {
        "programming_languages": "Programming Languages",
        "frameworks_libraries": "Frameworks & Libraries",
        "databases": "Databases",
        "cloud_platforms": "Cloud & DevOps",
        "developer_tools": "Developer Tools",
        "ai_ml_technologies": "AI & Machine Learning",
        "soft_skills": "Core Competencies",
        "domain_knowledge": "Domain Knowledge",
        "other_skills": "Technologies & Tools"
    }
    for k, v in skills_in.items():
        if k != "all_raw_skills" and isinstance(v, list) and v:
            display_name = label_map.get(k, k.replace("_", " ").title())
            mapped_skills[display_name] = [str(item).strip() for item in v if str(item).strip()]

    if not mapped_skills and skills_in.get("all_raw_skills"):
        mapped_skills["Technical Skills"] = skills_in["all_raw_skills"]

    # Work experience
    exp_list = []
    for e in extracted.get("work_experience") or []:
        bullets = list(e.get("responsibilities", []) or []) + list(e.get("achievements", []) or [])
        if not bullets and e.get("original_text"):
            bullets = [e.get("original_text")]
        title = e.get("designation") or e.get("title") or e.get("role") or e.get("job_title") or ""
        company = e.get("employer") or e.get("company") or ""
        exp_list.append({
            "title": title,
            "designation": title,
            "company": company,
            "employer": company,
            "location": e.get("employment_location") or e.get("location") or "",
            "start_date": e.get("start_date") or "",
            "end_date": e.get("end_date") or ("Present" if e.get("is_current") else ""),
            "bullets": bullets or []
        })

    # Education
    edu_list = []
    for ed in extracted.get("education") or []:
        edu_list.append({
            "degree": ed.get("degree") or "",
            "institution": ed.get("institution") or "",
            "location": ed.get("location") or "",
            "graduation_year": ed.get("graduation_year") or ed.get("end_date") or "",
            "gpa": ed.get("grade") or ""
        })

    # Projects
    proj_list = []
    for p in extracted.get("projects") or []:
        norm_p = canonicalize_project(p)
        proj_link = norm_p.get("link") or p.get("link") or p.get("repo_url") or p.get("demo_url") or ""
        proj_list.append({
            "name": norm_p.get("name") or "",
            "title": norm_p.get("name") or "",
            "tech_stack": norm_p.get("tech_stack") or "",
            "technologies": norm_p.get("technologies") or [],
            "start_date": norm_p.get("start_date") or "",
            "end_date": norm_p.get("end_date") or "",
            "dates": norm_p.get("dates") or "",
            "description": norm_p.get("description"),
            "bullets": norm_p.get("bullets") or [],
            "responsibilities": norm_p.get("bullets") or [],
            "features": [],
            "link": proj_link,
            "repo_url": norm_p.get("repo_url") or p.get("repo_url") or "",
            "demo_url": norm_p.get("demo_url") or p.get("demo_url") or ""
        })

    # Certifications
    certs_list = []
    for c in extracted.get("certifications") or []:
        if isinstance(c, dict):
            cert_name = c.get("name") or "Certification"
            issuer = c.get("issuer") or c.get("issuing_organization") or ""
            cred_url = c.get("credential_url") or ""
            if cred_url:
                certs_list.append(f"{cert_name} ({issuer}) - {cred_url}" if issuer else f"{cert_name} - {cred_url}")
            elif issuer:
                certs_list.append(f"{cert_name} - {issuer}")
            else:
                certs_list.append(cert_name)
        else:
            certs_list.append(str(c))

    # Custom / unknown sections
    custom_list = []
    for sec in extracted.get("custom_sections") or []:
        custom_list.append({
            "title": sec.get("section_title") or "Additional Section",
            "content": sec.get("original_content") or ""
        })

    return {
        "personal_info": {
            "full_name": pi.get("full_name") or pi.get("name") or "",
            "professional_title": pi.get("professional_title") or pi.get("title") or "",
            "title": pi.get("professional_title") or pi.get("title") or "",
            "email": pi.get("email") or "",
            "phone": pi.get("phone") or "",
            "location": pi.get("location") or "",
            "linkedin": pi.get("linkedin_url") or pi.get("linkedin") or "",
            "linkedin_url": pi.get("linkedin_url") or pi.get("linkedin") or "",
            "github": pi.get("github_url") or pi.get("github") or "",
            "github_url": pi.get("github_url") or pi.get("github") or "",
            "portfolio": pi.get("portfolio_url") or pi.get("portfolio") or "",
            "portfolio_url": pi.get("portfolio_url") or pi.get("portfolio") or "",
            "custom_links": pi.get("custom_links") or []
        },
        "summary": summary_text,
        "professional_summary": ps if isinstance(ps, dict) else {"summary": summary_text},
        "skills": mapped_skills,
        "raw_skills": skills_in,
        "experience": exp_list,
        "work_experience": exp_list,
        "education": edu_list,
        "projects": proj_list,
        "certifications": certs_list,
        "custom_sections": custom_list
    }


def _get_consolidated_resume_data(resume: Resume, db: Session) -> Tuple[Dict[str, Any], str]:
    """
    Consolidates structured resume data and raw text across:
    1. Latest ResumeVersion.structured_data
    2. ResumeExtraction (structured_data and raw_text)
    3. Normalized ResumeProfile/ResumeSkill/etc. tables
    Guarantees returning valid non-empty structured data if any exists.
    """
    version = db.query(ResumeVersion).filter(ResumeVersion.id == resume.current_version_id).first()
    if not version:
        version = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()

    raw_text = ""
    extraction = db.query(ResumeExtraction).filter(ResumeExtraction.resume_id == resume.id).first()
    if extraction:
        raw_text = extraction.raw_text or ""

    structured = None
    if version and version.structured_data and isinstance(version.structured_data, dict) and any(version.structured_data.values()):
        structured = dict(version.structured_data)
        if "projects" in structured:
            structured["projects"] = canonicalize_projects_list(structured["projects"])
    elif extraction and extraction.structured_data and isinstance(extraction.structured_data, dict):
        structured = convert_to_template_payload(extraction.structured_data)

    if not structured:
        profile = db.query(ResumeProfile).filter(ResumeProfile.resume_id == resume.id).first()
        if profile:
            skills = db.query(ResumeSkill).filter(ResumeSkill.resume_id == resume.id).all()
            skills_dict: Dict[str, List[str]] = {}
            for s in skills:
                cat = s.category or "Technical"
                skills_dict.setdefault(cat, []).append(s.name)

            exps = db.query(ResumeExperience).filter(ResumeExperience.resume_id == resume.id).order_by(ResumeExperience.sort_order.asc()).all()
            exp_list = [
                {
                    "title": e.designation,
                    "designation": e.designation,
                    "company": e.employer,
                    "employer": e.employer,
                    "location": e.employment_location or "",
                    "dates": f"{e.start_date or ''} - {e.end_date or 'Present'}",
                    "bullets": e.responsibilities or []
                }
                for e in exps
            ]

            edus = db.query(ResumeEducation).filter(ResumeEducation.resume_id == resume.id).order_by(ResumeEducation.sort_order.asc()).all()
            edu_list = [
                {
                    "degree": ed.degree,
                    "institution": ed.institution,
                    "location": ed.location or "",
                    "dates": f"{ed.start_date or ''} - {ed.end_date or ''}",
                    "gpa": ed.grade or ""
                }
                for ed in edus
            ]

            projs = db.query(ResumeProject).filter(ResumeProject.resume_id == resume.id).order_by(ResumeProject.sort_order.asc()).all()
            proj_list = [
                canonicalize_project({
                    "name": p.name,
                    "technologies": p.technologies or [],
                    "description": p.description or "",
                    "link": p.project_url or "",
                    "bullets": p.responsibilities or []
                })
                for p in projs
            ]

            structured = {
                "personal_info": {
                    "full_name": profile.full_name or "",
                    "email": profile.email or "",
                    "phone": profile.phone or "",
                    "location": profile.location or "",
                    "linkedin": profile.linkedin_url or "",
                    "github": profile.github_url or "",
                    "portfolio": profile.portfolio_url or ""
                },
                "summary": profile.professional_summary or "",
                "skills": skills_dict,
                "experience": exp_list,
                "education": edu_list,
                "projects": proj_list,
                "certifications": [],
                "custom_sections": []
            }

    return structured or {}, raw_text


def sync_extraction_to_database(
    db: Session,
    resume: Resume,
    structured_data: Dict[str, Any],
    raw_text: str,
    layout_info: Optional[Dict[str, Any]] = None
) -> None:
    """Synchronizes full extraction and populates normalized companion database tables."""
    # 1. Update or create ResumeExtraction
    extraction = db.query(ResumeExtraction).filter(ResumeExtraction.resume_id == resume.id).first()
    if not extraction:
        extraction = ResumeExtraction(
            resume_id=resume.id,
            raw_text=raw_text,
            layout_info=layout_info or {},
            structured_data=structured_data,
            confidence_score=structured_data.get("confidence_score", 1.0),
            missing_fields=structured_data.get("missing_fields", []),
            warnings=structured_data.get("extraction_warnings", []),
            parser_pipeline="Layout-Aware PyMuPDF/DOCX + AI Structured",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(extraction)
    else:
        if raw_text:
            extraction.raw_text = raw_text
        if layout_info:
            extraction.layout_info = layout_info
        extraction.structured_data = structured_data
        extraction.confidence_score = structured_data.get("confidence_score", 1.0)
        extraction.missing_fields = structured_data.get("missing_fields", [])
        extraction.warnings = structured_data.get("extraction_warnings", [])
        extraction.updated_at = datetime.utcnow()

    # 2. Update or create ResumeProfile
    pi = structured_data.get("personal_info") or {}
    ps = structured_data.get("professional_summary") or {}
    profile = db.query(ResumeProfile).filter(ResumeProfile.resume_id == resume.id).first()
    if not profile:
        profile = ResumeProfile(
            resume_id=resume.id,
            full_name=pi.get("full_name"),
            first_name=pi.get("first_name"),
            middle_name=pi.get("middle_name"),
            last_name=pi.get("last_name"),
            professional_title=pi.get("professional_title"),
            email=pi.get("email"),
            additional_emails=pi.get("additional_emails", []),
            phone=pi.get("phone"),
            additional_phones=pi.get("additional_phones", []),
            location=pi.get("location"),
            city=pi.get("city"),
            state=pi.get("state"),
            country=pi.get("country"),
            linkedin_url=pi.get("linkedin_url"),
            github_url=pi.get("github_url"),
            portfolio_url=pi.get("portfolio_url"),
            custom_links=pi.get("custom_links", []),
            professional_summary=ps.get("summary") if isinstance(ps, dict) else str(ps or ""),
            career_objective=ps.get("career_objective") if isinstance(ps, dict) else None,
            years_of_experience=ps.get("years_of_experience") if isinstance(ps, dict) else None,
            areas_of_specialization=ps.get("areas_of_specialization", []) if isinstance(ps, dict) else [],
            career_interests=ps.get("career_interests", []) if isinstance(ps, dict) else [],
            is_verified=resume.is_verified,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(profile)
    else:
        profile.full_name = pi.get("full_name")
        profile.first_name = pi.get("first_name")
        profile.middle_name = pi.get("middle_name")
        profile.last_name = pi.get("last_name")
        profile.professional_title = pi.get("professional_title")
        profile.email = pi.get("email")
        profile.additional_emails = pi.get("additional_emails", [])
        profile.phone = pi.get("phone")
        profile.additional_phones = pi.get("additional_phones", [])
        profile.location = pi.get("location")
        profile.city = pi.get("city")
        profile.state = pi.get("state")
        profile.country = pi.get("country")
        profile.linkedin_url = pi.get("linkedin_url")
        profile.github_url = pi.get("github_url")
        profile.portfolio_url = pi.get("portfolio_url")
        profile.custom_links = pi.get("custom_links", [])
        profile.professional_summary = ps.get("summary") if isinstance(ps, dict) else str(ps or "")
        profile.career_objective = ps.get("career_objective") if isinstance(ps, dict) else None
        profile.years_of_experience = ps.get("years_of_experience") if isinstance(ps, dict) else None
        profile.areas_of_specialization = ps.get("areas_of_specialization", []) if isinstance(ps, dict) else []
        profile.career_interests = ps.get("career_interests", []) if isinstance(ps, dict) else []
        profile.is_verified = resume.is_verified
        profile.updated_at = datetime.utcnow()

    # Clear old normalized child rows before re-populating to prevent duplicates
    db.query(ResumeSkill).filter(ResumeSkill.resume_id == resume.id).delete()
    db.query(ResumeExperience).filter(ResumeExperience.resume_id == resume.id).delete()
    db.query(ResumeEducation).filter(ResumeEducation.resume_id == resume.id).delete()
    db.query(ResumeProject).filter(ResumeProject.resume_id == resume.id).delete()
    db.query(ResumeCertification).filter(ResumeCertification.resume_id == resume.id).delete()
    db.query(ResumeSection).filter(ResumeSection.resume_id == resume.id).delete()

    # 3. Populate ResumeSkill
    skills_dict = structured_data.get("skills") or {}
    for cat_name, skill_list in skills_dict.items():
        if cat_name == "all_raw_skills" or not isinstance(skill_list, list):
            continue
        for s in skill_list:
            if s and str(s).strip():
                db.add(ResumeSkill(
                    resume_id=resume.id,
                    name=str(s).strip(),
                    category=cat_name,
                    source_text=str(s).strip(),
                    is_verified=resume.is_verified,
                    created_at=datetime.utcnow()
                ))

    # 4. Populate ResumeExperience
    for idx, exp in enumerate(structured_data.get("work_experience") or []):
        db.add(ResumeExperience(
            resume_id=resume.id,
            employer=exp.get("employer") or exp.get("company") or "",
            designation=exp.get("designation") or exp.get("role") or "",
            employment_location=exp.get("employment_location"),
            start_date=exp.get("start_date"),
            end_date=exp.get("end_date"),
            is_current=bool(exp.get("is_current")),
            employment_type=exp.get("employment_type", "Full-time"),
            responsibilities=exp.get("responsibilities", []),
            achievements=exp.get("achievements", []),
            technologies=exp.get("technologies", []),
            metrics=exp.get("metrics", []),
            original_text=exp.get("original_text"),
            sort_order=idx,
            is_verified=resume.is_verified
        ))

    # 5. Populate ResumeEducation
    for idx, edu in enumerate(structured_data.get("education") or []):
        db.add(ResumeEducation(
            resume_id=resume.id,
            degree=edu.get("degree") or "",
            field_of_study=edu.get("field_of_study"),
            institution=edu.get("institution") or "",
            location=edu.get("location"),
            start_date=edu.get("start_date"),
            end_date=edu.get("end_date"),
            graduation_year=edu.get("graduation_year"),
            grade=edu.get("grade"),
            relevant_coursework=edu.get("relevant_coursework", []),
            achievements=edu.get("achievements", []),
            thesis=edu.get("thesis"),
            sort_order=idx,
            is_verified=resume.is_verified
        ))

    # 6. Populate ResumeProject
    for idx, proj in enumerate(structured_data.get("projects") or []):
        canon_p = canonicalize_project(proj)
        db.add(ResumeProject(
            resume_id=resume.id,
            name=canon_p.get("name") or canon_p.get("title") or "",
            description=canon_p.get("description"),
            problem=canon_p.get("problem"),
            solution=canon_p.get("solution"),
            technologies=canon_p.get("technologies") or canon_p.get("tech_stack", []),
            responsibilities=canon_p.get("bullets") or canon_p.get("responsibilities", []),
            features=[],
            results_metrics=canon_p.get("results_metrics", []),
            duration=canon_p.get("dates") or canon_p.get("duration"),
            link=canon_p.get("link"),
            project_type=canon_p.get("project_type"),
            sort_order=idx,
            is_verified=resume.is_verified
        ))

    # 7. Populate ResumeCertification
    for idx, cert in enumerate(structured_data.get("certifications") or []):
        db.add(ResumeCertification(
            resume_id=resume.id,
            name=cert.get("name") if isinstance(cert, dict) else str(cert),
            issuing_organization=cert.get("issuing_organization") if isinstance(cert, dict) else None,
            issue_date=cert.get("issue_date") if isinstance(cert, dict) else None,
            expiration_date=cert.get("expiration_date") if isinstance(cert, dict) else None,
            credential_id=cert.get("credential_id") if isinstance(cert, dict) else None,
            credential_url=cert.get("credential_url") if isinstance(cert, dict) else None,
            training_type=cert.get("training_type") if isinstance(cert, dict) else "Certification",
            sort_order=idx,
            is_verified=resume.is_verified
        ))

    # 8. Populate ResumeSection (Custom/Unknown sections)
    for idx, sec in enumerate(structured_data.get("custom_sections") or []):
        db.add(ResumeSection(
            resume_id=resume.id,
            section_title=sec.get("section_title") or f"Section {idx + 1}",
            original_content=sec.get("original_content") or "",
            structured_content=sec.get("structured_content"),
            section_order=idx,
            section_category="custom",
            is_verified=resume.is_verified
        ))


@router.post("/resumes/upload")
async def upload_resume_file(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    template_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accepts PDF, DOCX, TXT, or LaTeX (.tex) upload:
    - Validates file size (max 10MB) and file magic signature
    - Computes SHA-256 integrity hash for duplicate detection
    - Preserves original file untouched in secure user storage
    - Executes layout-aware multi-column extraction & OCR fallback
    - AI-based comprehensive structured parsing (with zero-hallucination heuristic fallback)
    - Saves dual representations: raw extraction + normalized database records
    - Creates initial ResumeVersion ready for Overleaf LaTeX compilation
    """
    candidate = _get_or_create_candidate(current_user, db)
    filename = file.filename or "uploaded_resume.pdf"
    content = await file.read()

    # 1. Validation & Integrity
    is_valid, error_msg, file_hash, ext = validate_resume_upload(filename, content, file.content_type)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # 2. Check for duplicate upload
    existing_duplicate = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.file_hash == file_hash,
        Resume.deleted_at == None
    ).first()

    # 3. Store original file safely in private user storage (never altered)
    user_folder = get_user_folder_name(current_user)
    safe_base = _sanitize_filename(filename.rsplit(".", 1)[0])
    saved_name = f"orig_{int(datetime.utcnow().timestamp())}_{safe_base}{ext}"

    original_file_url = storage_service.upload_file(
        folder=f"{user_folder}/resumes",
        filename=saved_name,
        content=content,
        mime_type=file.content_type
    )

    # 4. Multi-column, layout-aware document extraction
    doc_res = extract_document_content(filename, content, ext)
    raw_text = doc_res["raw_text"]
    page_count = doc_res["page_count"]
    layout_info = doc_res["layout_info"]

    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Could not extract readable text or characters from uploaded file.")

    # 5. Comprehensive structured extraction
    pdf_bytes = content if ext == ".pdf" else None
    structured_data = extract_structured_with_ai(raw_text, pdf_bytes, layout_info)
    if "hyperlinks" in structured_data:
        layout_info["hyperlinks"] = structured_data["hyperlinks"]

    # 6. Resolve template
    chosen_template_id = template_id
    if not chosen_template_id:
        classic_tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.slug == "classic-ats").first()
        if not classic_tmpl:
            classic_tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.is_active == True).first()
        chosen_template_id = classic_tmpl.id if classic_tmpl else 1

    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == chosen_template_id).first()

    # 7. Convert to template-compatible structured JSON for instant LaTeX compilation
    template_structured_data = convert_to_template_payload(structured_data)
    latex_source = render_resume_to_latex(template_structured_data, tmpl.latex_template if tmpl else "")

    # 8. Create Resume entity
    resume_title = title or f"Uploaded: {safe_base}"
    resume = Resume(
        candidate_id=candidate.id,
        title=resume_title,
        source_type="upload",
        template_id=chosen_template_id,
        original_file_url=original_file_url,
        file_name=filename,
        file_type=ext.lstrip(".").upper(),
        file_size=len(content),
        file_hash=file_hash,
        page_count=page_count,
        status="active",
        extraction_status="extracted",
        extraction_confidence=structured_data.get("confidence_score", 1.0),
        parser_version="v2.0-hybrid",
        is_verified=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(resume)
    db.flush()

    # 9. Sync full extraction & normalized tables to DB
    sync_extraction_to_database(db, resume, structured_data, raw_text, layout_info)

    # 10. Create initial ResumeVersion
    version = ResumeVersion(
        resume_id=resume.id,
        version_number=1,
        structured_data=template_structured_data,
        latex_source=latex_source,
        change_summary="Original uploaded resume extraction",
        created_by=current_user.id,
        created_at=datetime.utcnow()
    )
    db.add(version)
    db.flush()

    resume.current_version_id = version.id
    db.commit()
    db.refresh(resume)

    # 11. Execute Atomic Active Resume Replacement & Role Generation
    role_res = {}
    try:
        active_resume, role_res = ResumeContextService.replace_active_resume(
            db, candidate.id, resume.id, template_structured_data
        )
    except Exception as err:
        logger.error(f"Active resume replacement failed: {err}")
        ResumeContextService.handle_extraction_failure(db, candidate.id, resume.id, str(err))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New resume could not be processed. Your current resume is still active."
        )

    return {
        "message": "Resume updated successfully. Your new resume is now the active resume.",
        "resume_id": resume.id,
        "version_id": version.id,
        "title": resume.title,
        "file_name": filename,
        "file_size": len(content),
        "file_hash": file_hash,
        "page_count": page_count,
        "original_file_url": original_file_url,
        "extraction_status": resume.extraction_status,
        "confidence_score": structured_data.get("confidence_score", 1.0),
        "missing_fields": structured_data.get("missing_fields", []),
        "warnings": structured_data.get("extraction_warnings", []),
        "raw_text_preview": raw_text[:2000],
        "layout_info": layout_info,
        "active_resume_id": resume.id,
        "primary_designation": role_res.get("primary_designation"),
        "target_roles": role_res.get("target_roles", []),
        "role_evidence": role_res.get("role_evidence", []),
        "structured_data": structured_data,
        "template_compatible_data": template_structured_data,
        "is_active": True,
        "previous_resume_status": "archived"
    }


@router.get("/resumes/{resume_id}/extraction")
def get_resume_extraction(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns complete extraction records, raw text, normalized components, and diagnostics."""
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    _verify_resume_ownership(resume, current_user, candidate)

    extraction = db.query(ResumeExtraction).filter(ResumeExtraction.resume_id == resume.id).first()
    profile = db.query(ResumeProfile).filter(ResumeProfile.resume_id == resume.id).first()
    skills = db.query(ResumeSkill).filter(ResumeSkill.resume_id == resume.id).all()
    experiences = db.query(ResumeExperience).filter(ResumeExperience.resume_id == resume.id).order_by(ResumeExperience.sort_order.asc()).all()
    educations = db.query(ResumeEducation).filter(ResumeEducation.resume_id == resume.id).order_by(ResumeEducation.sort_order.asc()).all()
    projects = db.query(ResumeProject).filter(ResumeProject.resume_id == resume.id).order_by(ResumeProject.sort_order.asc()).all()
    certifications = db.query(ResumeCertification).filter(ResumeCertification.resume_id == resume.id).order_by(ResumeCertification.sort_order.asc()).all()
    sections = db.query(ResumeSection).filter(ResumeSection.resume_id == resume.id).order_by(ResumeSection.section_order.asc()).all()

    return {
        "resume_id": resume.id,
        "title": resume.title,
        "file_name": resume.file_name,
        "file_type": resume.file_type,
        "file_size": resume.file_size,
        "page_count": resume.page_count,
        "file_hash": resume.file_hash,
        "original_file_url": resume.original_file_url,
        "extraction_status": resume.extraction_status,
        "extraction_confidence": resume.extraction_confidence,
        "is_verified": resume.is_verified,
        "raw_text": extraction.raw_text if extraction else "",
        "layout_info": extraction.layout_info if extraction else {},
        "confidence_score": extraction.confidence_score if extraction else 1.0,
        "missing_fields": extraction.missing_fields if extraction else [],
        "warnings": extraction.warnings if extraction else [],
        "structured_data": extraction.structured_data if extraction else {},
        "normalized": {
            "profile": {
                "full_name": profile.full_name if profile else None,
                "email": profile.email if profile else None,
                "phone": profile.phone if profile else None,
                "location": profile.location if profile else None,
                "professional_title": profile.professional_title if profile else None,
                "linkedin_url": profile.linkedin_url if profile else None,
                "github_url": profile.github_url if profile else None,
                "portfolio_url": profile.portfolio_url if profile else None,
                "custom_links": profile.custom_links if profile else [],
                "professional_summary": profile.professional_summary if profile else None,
                "career_objective": profile.career_objective if profile else None,
                "years_of_experience": profile.years_of_experience if profile else None
            },
            "skills": [{"id": s.id, "name": s.name, "category": s.category, "is_verified": s.is_verified} for s in skills],
            "experiences": [
                {
                    "id": e.id, "employer": e.employer, "designation": e.designation,
                    "employment_location": e.employment_location, "start_date": e.start_date,
                    "end_date": e.end_date, "is_current": e.is_current, "responsibilities": e.responsibilities,
                    "achievements": e.achievements, "technologies": e.technologies
                } for e in experiences
            ],
            "educations": [
                {
                    "id": ed.id, "degree": ed.degree, "field_of_study": ed.field_of_study,
                    "institution": ed.institution, "location": ed.location, "start_date": ed.start_date,
                    "end_date": ed.end_date, "graduation_year": ed.graduation_year, "grade": ed.grade,
                    "relevant_coursework": ed.relevant_coursework
                } for ed in educations
            ],
            "projects": [
                {
                    "id": p.id, "name": p.name, "description": p.description, "technologies": p.technologies,
                    "responsibilities": p.responsibilities, "link": p.link
                } for p in projects
            ],
            "certifications": [
                {
                    "id": c.id, "name": c.name, "issuing_organization": c.issuing_organization,
                    "issue_date": c.issue_date, "credential_id": c.credential_id
                } for c in certifications
            ],
            "sections": [
                {
                    "id": sec.id, "section_title": sec.section_title, "original_content": sec.original_content,
                    "structured_content": sec.structured_content
                } for sec in sections
            ]
        }
    }


@router.get("/resumes/{resume_id}/hyperlinks")
def get_resume_hyperlinks(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns extracted hyperlinks for a resume with classifications,
    validation status, and entity associations.
    """
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    _verify_resume_ownership(resume, current_user, candidate)

    extraction = db.query(ResumeExtraction).filter(ResumeExtraction.resume_id == resume.id).first()
    layout_info = (extraction.layout_info if extraction else {}) or {}
    links = layout_info.get("hyperlinks", [])
    if not links and extraction and extraction.structured_data:
        links = extraction.structured_data.get("hyperlinks", [])

    by_type: Dict[str, int] = {}
    by_validation: Dict[str, int] = {}
    for link in links:
        t = link.get("link_type", "other")
        v = link.get("validation_status", "valid")
        by_type[t] = by_type.get(t, 0) + 1
        by_validation[v] = by_validation.get(v, 0) + 1

    return {
        "resume_id": resume.id,
        "total_hyperlinks": len(links),
        "by_type": by_type,
        "by_validation_status": by_validation,
        "hyperlinks": links
    }


@router.put("/resumes/{resume_id}/extraction/verify")
def verify_resume_extraction(
    resume_id: int,
    payload: Dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Accepts candidate corrections, marks extraction as verified,
    updates normalized database records, and syncs current ResumeVersion.
    """
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    _verify_resume_ownership(resume, current_user, candidate)

    # Updated structured data provided by candidate
    corrected_data = payload.get("structured_data") or payload
    raw_text = payload.get("raw_text") or ""

    resume.is_verified = True
    resume.extraction_status = "verified"
    resume.updated_at = datetime.utcnow()

    # Sync back to DB
    sync_extraction_to_database(db, resume, corrected_data, raw_text, layout_info=None)

    # Also update template payload on current ResumeVersion
    template_data = convert_to_template_payload(corrected_data)
    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == resume.template_id).first()
    latex_source = render_resume_to_latex(template_data, tmpl.latex_template if tmpl else "")

    current_v = db.query(ResumeVersion).filter(ResumeVersion.id == resume.current_version_id).first()
    if current_v:
        current_v.structured_data = template_data
        current_v.latex_source = latex_source
        current_v.change_summary = "Candidate verified & corrected extraction"

    db.commit()
    db.refresh(resume)

    return {
        "message": "Resume data verified and saved successfully",
        "resume_id": resume.id,
        "is_verified": True,
        "extraction_status": "verified",
        "structured_data": corrected_data
    }


@router.get("/candidate/profile-data")
def get_candidate_saved_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns candidate's latest verified or extracted profile for pre-filling builder workflows."""
    candidate = _get_or_create_candidate(current_user, db)
    latest_resume = db.query(Resume).filter(
        Resume.candidate_id == candidate.id,
        Resume.deleted_at == None
    ).order_by(Resume.is_verified.desc(), Resume.updated_at.desc()).first()

    if not latest_resume:
        return {"has_profile": False, "profile_data": None}

    extraction = db.query(ResumeExtraction).filter(ResumeExtraction.resume_id == latest_resume.id).first()
    if extraction and extraction.structured_data:
        data = extraction.structured_data
    else:
        latest_v = db.query(ResumeVersion).filter(ResumeVersion.resume_id == latest_resume.id).order_by(ResumeVersion.version_number.desc()).first()
        data = latest_v.structured_data if latest_v else {}

    return {
        "has_profile": True,
        "resume_id": latest_resume.id,
        "resume_title": latest_resume.title,
        "is_verified": latest_resume.is_verified,
        "profile_data": data,
        "template_compatible_data": convert_to_template_payload(data) if data else None
    }


@router.post("/resumes")
def create_new_resume(
    payload: ResumeCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Creates a new resume from builder with chosen template and structured data."""
    candidate = _get_or_create_candidate(current_user, db)

    # Resolve template
    template_id = payload.template_id
    if not template_id:
        tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.slug == "ats-classic").first()
        if not tmpl:
            seed_resume_templates(db)
            tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.slug == "ats-classic").first()
        template_id = tmpl.id if tmpl else 1

    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == template_id).first()
    latex_source = render_resume_to_latex(payload.structured_data, tmpl.latex_template if tmpl else "")

    resume = Resume(
        candidate_id=candidate.id,
        title=payload.title,
        source_type="builder",
        template_id=template_id,
        status="active",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(resume)
    db.flush()

    version = ResumeVersion(
        resume_id=resume.id,
        version_number=1,
        structured_data=payload.structured_data,
        latex_source=latex_source,
        change_summary="Initial resume creation",
        created_by=current_user.id,
        created_at=datetime.utcnow()
    )
    db.add(version)
    db.flush()

    resume.current_version_id = version.id
    db.commit()
    db.refresh(resume)

    return {
        "id": resume.id,
        "title": resume.title,
        "template_id": resume.template_id,
        "current_version_id": resume.current_version_id,
        "status": resume.status,
        "created_at": resume.created_at.isoformat(),
        "structured_data": payload.structured_data
    }


@router.get("/resumes/{resume_id}")
def get_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieves resume details and active version structured data."""
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    # Fetch current version
    version = None
    if resume.current_version_id:
        version = db.query(ResumeVersion).filter(ResumeVersion.id == resume.current_version_id).first()
    if not version:
        version = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()

    return {
        "id": resume.id,
        "candidate_id": resume.candidate_id,
        "title": resume.title,
        "source_type": resume.source_type,
        "template_id": resume.template_id,
        "template_name": resume.template.name if resume.template else None,
        "template_slug": resume.template.slug if resume.template else None,
        "current_version_id": resume.current_version_id,
        "original_file_url": resume.original_file_url,
        "latest_pdf_url": resume.latest_pdf_url,
        "latest_tex_url": resume.latest_tex_url,
        "status": resume.status,
        "created_at": resume.created_at.isoformat() if resume.created_at else None,
        "updated_at": resume.updated_at.isoformat() if resume.updated_at else None,
        "version_number": version.version_number if version else 1,
        "structured_data": version.structured_data if version else {},
        "change_summary": version.change_summary if version else None,
    }


@router.patch("/resumes/{resume_id}")
def update_resume(
    resume_id: int,
    payload: ResumeUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Updates resume title, template, or structured data (either as new version or in-place draft)."""
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    if payload.title is not None:
        resume.title = payload.title
    if payload.template_id is not None:
        resume.template_id = payload.template_id
    if payload.status is not None:
        resume.status = payload.status

    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == resume.template_id).first()

    if payload.structured_data is not None:
        if isinstance(payload.structured_data, dict) and "projects" in payload.structured_data:
            payload.structured_data["projects"] = canonicalize_projects_list(payload.structured_data["projects"])
        latex_source = render_resume_to_latex(payload.structured_data, tmpl.latex_template if tmpl else "")

        if payload.create_new_version:
            # Determine next version number
            latest_v = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()
            next_num = (latest_v.version_number + 1) if latest_v else 1

            new_version = ResumeVersion(
                resume_id=resume.id,
                version_number=next_num,
                structured_data=payload.structured_data,
                latex_source=latex_source,
                change_summary=payload.change_summary or f"Version {next_num} update",
                created_by=current_user.id,
                created_at=datetime.utcnow()
            )
            db.add(new_version)
            db.flush()
            resume.current_version_id = new_version.id
        else:
            # In-place update of current version (draft / autosave)
            current_v = db.query(ResumeVersion).filter(ResumeVersion.id == resume.current_version_id).first()
            if current_v:
                current_v.structured_data = payload.structured_data
                current_v.latex_source = latex_source
                if payload.change_summary:
                    current_v.change_summary = payload.change_summary

    resume.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(resume)

    return {
        "message": "Resume updated successfully",
        "id": resume.id,
        "title": resume.title,
        "template_id": resume.template_id,
        "current_version_id": resume.current_version_id
    }


@router.delete("/resumes/{resume_id}")
def delete_resume(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Soft deletes resume from candidate list."""
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    resume.deleted_at = datetime.utcnow()
    db.commit()
    return {"message": "Resume deleted successfully", "id": resume_id}


# ─────────────────────────────────────────────────────────────────────────────
# VERSIONS & RESTORE ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/resumes/{resume_id}/versions")
def list_resume_versions(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns version history for a resume."""
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    versions = db.query(ResumeVersion).filter(
        ResumeVersion.resume_id == resume.id
    ).order_by(ResumeVersion.version_number.desc()).all()

    return [
        {
            "id": v.id,
            "version_number": v.version_number,
            "change_summary": v.change_summary,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "is_current": (v.id == resume.current_version_id),
            "pdf_file_url": v.pdf_file_url,
            "structured_data": v.structured_data
        }
        for v in versions
    ]


@router.post("/resumes/{resume_id}/versions")
def create_resume_version(
    resume_id: int,
    payload: ResumeVersionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Explicitly commits a new version snapshot of the resume."""
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    latest_v = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()
    next_num = (latest_v.version_number + 1) if latest_v else 1

    if payload.structured_data and isinstance(payload.structured_data, dict) and "projects" in payload.structured_data:
        payload.structured_data["projects"] = canonicalize_projects_list(payload.structured_data["projects"])

    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == resume.template_id).first()
    latex_source = render_resume_to_latex(payload.structured_data, tmpl.latex_template if tmpl else "")

    version = ResumeVersion(
        resume_id=resume.id,
        version_number=next_num,
        structured_data=payload.structured_data,
        latex_source=latex_source,
        change_summary=payload.change_summary or f"Version {next_num}",
        created_by=current_user.id,
        created_at=datetime.utcnow()
    )
    db.add(version)
    db.flush()

    resume.current_version_id = version.id
    resume.updated_at = datetime.utcnow()
    db.commit()

    return {
        "message": f"Version {next_num} created successfully",
        "version_id": version.id,
        "version_number": next_num
    }


@router.post("/resumes/{resume_id}/versions/{version_id}/restore")
def restore_resume_version(
    resume_id: int,
    version_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Restores an older version by creating a new version snapshot containing that older data.
    Never deletes or overwrites existing history.
    """
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    target_v = db.query(ResumeVersion).filter(
        ResumeVersion.id == version_id,
        ResumeVersion.resume_id == resume.id
    ).first()
    if not target_v:
        raise HTTPException(status_code=404, detail="Version not found")

    latest_v = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()
    next_num = (latest_v.version_number + 1) if latest_v else 1

    new_v = ResumeVersion(
        resume_id=resume.id,
        version_number=next_num,
        structured_data=target_v.structured_data,
        latex_source=target_v.latex_source,
        change_summary=f"Restored from Version {target_v.version_number}",
        created_by=current_user.id,
        created_at=datetime.utcnow()
    )
    db.add(new_v)
    db.flush()

    resume.current_version_id = new_v.id
    resume.updated_at = datetime.utcnow()
    db.commit()

    return {
        "message": f"Successfully restored Version {target_v.version_number} as Version {next_num}",
        "new_version_id": new_v.id,
        "new_version_number": next_num
    }


# ─────────────────────────────────────────────────────────────────────────────
# LATEX COMPILATION & DOWNLOAD ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/resumes/{resume_id}/compile")
@limiter.limit("20/minute")
def compile_resume(
    request: Request,
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Compiles active resume version to PDF using sandboxed LaTeX service.
    Stores generated PDF and .tex privately and updates asset URLs.
    """
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    version = db.query(ResumeVersion).filter(ResumeVersion.id == resume.current_version_id).first()
    if not version:
        version = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()
    if not version:
        raise HTTPException(status_code=400, detail="No structured data found for resume")

    # If version.structured_data is empty or missing, fallback to consolidated extraction/profile data
    if not version.structured_data or not isinstance(version.structured_data, dict) or not any(version.structured_data.values()):
        consolidated_data, _ = _get_consolidated_resume_data(resume, db)
        if consolidated_data:
            version.structured_data = consolidated_data
            db.commit()

    # Guarantee canonical project normalization and deduplication in version.structured_data
    if version.structured_data and isinstance(version.structured_data, dict):
        raw_projs = version.structured_data.get("projects")
        if raw_projs:
            canon_projs = canonicalize_projects_list(raw_projs)
            if canon_projs != raw_projs:
                updated_sd = dict(version.structured_data)
                updated_sd["projects"] = canon_projs
                version.structured_data = updated_sd
                db.commit()

    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == resume.template_id).first()
    latex_source = render_resume_to_latex(version.structured_data, tmpl.latex_template if tmpl else "")
    version.latex_source = latex_source

    user_folder = get_user_folder_name(current_user)
    safe_base = _sanitize_filename(resume.title)
    tex_filename = f"resume_{resume.id}_v{version.version_number}_{safe_base}.tex"

    # Always save generated .tex file privately
    tex_url = storage_service.upload_file(
        folder=f"{user_folder}/resumes",
        filename=tex_filename,
        content=latex_source.encode("utf-8"),
        mime_type="application/x-tex"
    )
    resume.latest_tex_url = tex_url

    # Compile PDF (using pdflatex if available, or high-fidelity ReportLab engine)
    pdf_bytes = None
    compiler_used = "latex" if is_latex_installed() else "reportlab"
    compile_err = None

    if is_latex_installed():
        success, pdf_bytes, compile_err = compile_latex_to_pdf(latex_source)
        if not success or not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
            logger.warning(f"pdflatex compilation failed ({compile_err}), falling back to ReportLab generator")
            try:
                tmpl_slug = tmpl.slug if tmpl else "ats-classic"
                pdf_bytes = render_structured_data_to_pdf(version.structured_data, resume.title, template_slug=tmpl_slug)
                compiler_used = "reportlab_fallback"
            except Exception as e:
                db.commit()
                raise HTTPException(
                    status_code=500,
                    detail=f"Resume PDF compilation failed: {compile_err or str(e)}"
                )
    else:
        try:
            tmpl_slug = tmpl.slug if tmpl else "ats-classic"
            pdf_bytes = render_structured_data_to_pdf(version.structured_data, resume.title, template_slug=tmpl_slug)
        except Exception as e:
            logger.error(f"Standalone PDF fallback generation error: {e}", exc_info=True)
            db.commit()
            raise HTTPException(
                status_code=500,
                detail=f"PDF rendering error: {str(e)}"
            )

    if not pdf_bytes or len(pdf_bytes) < 100 or not pdf_bytes.startswith(b"%PDF"):
        db.commit()
        raise HTTPException(
            status_code=500,
            detail="PDF compilation generated an invalid or empty document artifact."
        )

    # Save PDF privately in user-isolated storage
    pdf_filename = f"resume_{resume.id}_v{version.version_number}_{safe_base}.pdf"
    pdf_url = storage_service.upload_file(
        folder=f"{user_folder}/resumes",
        filename=pdf_filename,
        content=pdf_bytes,
        mime_type="application/pdf"
    )

    resume.latest_pdf_url = pdf_url
    resume.status = "COMPILED"
    version.pdf_file_url = pdf_url
    db.commit()

    return {
        "status": "success",
        "latex_available": is_latex_installed(),
        "pdf_available": True,
        "compiler": compiler_used,
        "message": "Resume compiled successfully",
        "latest_pdf_url": pdf_url,
        "latest_tex_url": tex_url,
        "pdf_size_bytes": len(pdf_bytes)
    }


@router.get("/resumes/{resume_id}/download/pdf")
def download_resume_pdf(
    resume_id: int,
    preview: bool = Query(False, description="Whether to serve inline for browser preview"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Authenticated endpoint to download or preview compiled PDF."""
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    version = db.query(ResumeVersion).filter(ResumeVersion.id == resume.current_version_id).first()
    if not version:
        version = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()

    pdf_bytes = None
    safe_name = _sanitize_filename(resume.title)

    # 1. If PDF exists in storage, retrieve it
    if resume.latest_pdf_url:
        user_folder = get_user_folder_name(current_user)
        filename = resume.latest_pdf_url.split("/")[-1]
        pdf_bytes = storage_service.get_file_content(f"{user_folder}/resumes", filename)

    # 2. If not yet in storage, attempt on-the-fly compilation
    if not pdf_bytes and version:
        if not version.structured_data or not isinstance(version.structured_data, dict) or not any(version.structured_data.values()):
            consolidated_data, _ = _get_consolidated_resume_data(resume, db)
            if consolidated_data:
                version.structured_data = consolidated_data
                db.commit()

        if version.structured_data:
            try:
                if isinstance(version.structured_data, dict) and version.structured_data.get("projects"):
                    raw_p = version.structured_data.get("projects")
                    canon_p = canonicalize_projects_list(raw_p)
                    if canon_p != raw_p:
                        updated_sd = dict(version.structured_data)
                        updated_sd["projects"] = canon_p
                        version.structured_data = updated_sd
                        db.commit()

                tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == resume.template_id).first()
                if is_latex_installed():
                    latex_source = render_resume_to_latex(version.structured_data, tmpl.latex_template if tmpl else "")
                    success, pdf_bytes, _ = compile_latex_to_pdf(latex_source)
                    if not success or not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
                        tmpl_slug = tmpl.slug if tmpl else "ats-classic"
                        pdf_bytes = render_structured_data_to_pdf(version.structured_data, resume.title, template_slug=tmpl_slug)
                else:
                    tmpl_slug = tmpl.slug if tmpl else "ats-classic"
                    pdf_bytes = render_structured_data_to_pdf(version.structured_data, resume.title, template_slug=tmpl_slug)

                if pdf_bytes and len(pdf_bytes) > 100 and pdf_bytes.startswith(b"%PDF"):
                    # Cache in storage
                    user_folder = get_user_folder_name(current_user)
                    safe_base = _sanitize_filename(resume.title)
                    pdf_filename = f"resume_{resume.id}_v{version.version_number}_{safe_base}.pdf"
                    pdf_url = storage_service.upload_file(
                        folder=f"{user_folder}/resumes",
                        filename=pdf_filename,
                        content=pdf_bytes,
                        mime_type="application/pdf"
                    )
                    resume.latest_pdf_url = pdf_url
                    resume.status = "COMPILED"
                    version.pdf_file_url = pdf_url
                    db.commit()
            except Exception as e:
                logger.warning(f"On-the-fly PDF compilation failed: {e}")

    if not pdf_bytes or len(pdf_bytes) < 100 or not pdf_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=404,
            detail="Resume PDF could not be generated. Please compile the resume from the editor."
        )

    disposition = f'inline; filename="{safe_name}.pdf"' if preview else f'attachment; filename="{safe_name}.pdf"'
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": disposition,
            "Content-Type": "application/pdf",
            "Cache-Control": "private, no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.get("/resumes/{resume_id}/preview/pdf")
def preview_resume_pdf(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Authenticated endpoint to preview compiled PDF inline."""
    return download_resume_pdf(resume_id=resume_id, preview=True, current_user=current_user, db=db)


@router.get("/resumes/{resume_id}/download/latex")
def download_resume_latex(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Authenticated endpoint to download Overleaf-compatible .tex source file."""
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    version = db.query(ResumeVersion).filter(ResumeVersion.id == resume.current_version_id).first()
    if not version:
        version = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()

    if not version or not version.structured_data:
        raise HTTPException(status_code=400, detail="Resume has no data to export")

    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == resume.template_id).first()
    latex_source = version.latex_source or render_resume_to_latex(version.structured_data, tmpl.latex_template if tmpl else "")

    safe_name = _sanitize_filename(resume.title)
    return Response(
        content=latex_source.encode("utf-8"),
        media_type="application/x-tex",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.tex"',
            "Cache-Control": "private, no-store, max-age=0"
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# JD TAILORING ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/resume-tailoring/source/{resume_id}")
def get_source_resume_for_tailoring(
    resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves and validates source resume structured data for JD tailoring.
    Consolidates versions, extractions, and companion tables.
    Returns 400 with actionable error if resume has no usable data.
    """
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    structured_data, raw_text = _get_consolidated_resume_data(resume, db)
    if not structured_data or not any(structured_data.values()):
        raise HTTPException(
            status_code=400,
            detail="Source resume has no structured data. Please upload a valid document or add resume details before tailoring."
        )

    return {
        "resume_id": resume.id,
        "title": resume.title,
        "template_id": resume.template_id,
        "structured_data": structured_data,
        "raw_text_length": len(raw_text),
        "source_type": resume.source_type
    }


@router.post("/resume-tailoring/analyze-jd")
@limiter.limit("15/minute")
def analyze_job_description(
    request: Request,
    payload: AnalyzeJDRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Extracts key skills, ATS requirements, and matches against existing candidate resume.
    """
    candidate = _get_or_create_candidate(current_user, db)

    resume_data = {}
    source_raw_text = ""
    if payload.resume_id:
        resume = db.query(Resume).filter(Resume.id == payload.resume_id, Resume.deleted_at == None).first()
        if resume:
            _verify_resume_ownership(resume, current_user, candidate)
            resume_data, source_raw_text = _get_consolidated_resume_data(resume, db)

    # Save JD record
    jd_record = JobDescription(
        candidate_id=candidate.id,
        title=payload.job_title,
        company=payload.company,
        raw_text=payload.job_description,
        created_at=datetime.utcnow()
    )
    db.add(jd_record)
    db.commit()

    analysis = generate_jd_tailored_resume(
        source_resume_id=payload.resume_id or 0,
        source_resume_data=resume_data,
        job_title=payload.job_title,
        company_name=payload.company,
        job_description=payload.job_description,
        source_resume_text=source_raw_text
    )

    return analysis.model_dump()


@router.post("/resume-tailoring/generate")
@limiter.limit("10/minute")
def generate_tailored_resume_endpoint(
    request: Request,
    payload: GenerateTailoredResumeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Operation A: Tailors resume content specifically to the target JD.
    Returns matching skills, missing requirements, itemized diffs, and warnings.
    Strictly forbids fabricating candidate employment, projects, or degrees.
    """
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == payload.resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Source resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    structured_data, raw_text = _get_consolidated_resume_data(resume, db)
    if not structured_data or not any(structured_data.values()):
        raise HTTPException(status_code=400, detail="Source resume has no structured data to tailor.")

    analysis = generate_jd_tailored_resume(
        source_resume_id=resume.id,
        source_resume_data=structured_data,
        job_title=payload.job_title,
        company_name=payload.company,
        job_description=payload.job_description,
        source_resume_text=raw_text,
        selected_template_id=payload.template_id or resume.template_id,
        location=payload.location,
        seniority=payload.seniority
    )

    # Record intelligence run audit log
    try:
        audit_record = ResumeAIAnalysis(
            candidate_id=candidate.id,
            source_type="TAILOR_JD",
            raw_response=json.dumps({"job_title": payload.job_title, "company": payload.company}),
            parsed_json=analysis.model_dump(),
            confidence_score="HIGH",
            created_at=datetime.utcnow()
        )
        db.add(audit_record)
        db.commit()
    except Exception as e:
        logger.warning(f"Could not record tailoring audit log: {e}")
        db.rollback()

    return {
        "analysis": analysis.model_dump(),
        "source_resume_id": resume.id,
        "job_title": payload.job_title,
        "company": payload.company,
        "original_resume": structured_data,
        "tailored_resume_data": analysis.final_resume_data,
        "matching_skills": analysis.matching_skills,
        "missing_requirements": analysis.missing_requirements,
        "transferable_skills": analysis.transferable_skills,
        "suggested_changes": [c.model_dump() for c in analysis.suggested_changes],
        "ats_keywords": analysis.ats_keywords,
        "warnings": analysis.warnings
    }


@router.post("/resume-tailoring/render-template")
def render_tailored_template(
    payload: RenderTailoredTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Operation B: Renders tailored resume data through a selected Overleaf template.
    Generates exact LaTeX source and compiles to real PDF without re-running AI tailoring.
    """
    candidate = _get_or_create_candidate(current_user, db)
    source_resume = db.query(Resume).filter(Resume.id == payload.source_resume_id, Resume.deleted_at == None).first()
    if not source_resume:
        raise HTTPException(status_code=404, detail="Source resume not found")

    _verify_resume_ownership(source_resume, current_user, candidate)

    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == payload.selected_template_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Selected template not found")

    latex_source = render_resume_to_latex(payload.tailored_resume_data, tmpl.latex_template or "")

    pdf_bytes = None
    if is_latex_installed():
        success, pdf_bytes, _ = compile_latex_to_pdf(latex_source)
    else:
        tmpl_slug = tmpl.slug or "ats-classic"
        pdf_bytes = render_structured_data_to_pdf(
            payload.tailored_resume_data,
            title=f"Preview - {source_resume.title}",
            template_slug=tmpl_slug
        )
        success = True

    if not pdf_bytes:
        raise HTTPException(status_code=500, detail="Failed to compile preview PDF for selected template")

    # Save to user preview storage cache
    user_folder = get_user_folder_name(current_user)
    preview_filename = f"preview_tailored_{source_resume.id}_tmpl_{tmpl.id}.pdf"
    storage_service.upload_file(
        folder=f"{user_folder}/previews",
        filename=preview_filename,
        content=pdf_bytes,
        mime_type="application/pdf"
    )

    preview_url = f"/api/v1/resume-tailoring/preview/{source_resume.id}/{tmpl.id}"

    return {
        "template_id": tmpl.id,
        "template_name": tmpl.name,
        "template_slug": tmpl.slug,
        "latex_source": latex_source,
        "preview_url": preview_url,
        "compiled_success": success
    }


@router.get("/resume-tailoring/preview/{source_resume_id}/{template_id}")
def stream_tailored_preview_pdf(
    source_resume_id: int,
    template_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Streams the compiled preview PDF bytes inline for live <iframe> preview.
    """
    candidate = _get_or_create_candidate(current_user, db)
    source_resume = db.query(Resume).filter(Resume.id == source_resume_id, Resume.deleted_at == None).first()
    if not source_resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    _verify_resume_ownership(source_resume, current_user, candidate)

    user_folder = get_user_folder_name(current_user)
    preview_filename = f"preview_tailored_{source_resume_id}_tmpl_{template_id}.pdf"
    pdf_bytes = storage_service.get_file_content(f"{user_folder}/previews", preview_filename)

    if not pdf_bytes:
        # Re-render if not cached
        tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == template_id).first()
        structured_data, _ = _get_consolidated_resume_data(source_resume, db)
        if not structured_data:
            raise HTTPException(status_code=404, detail="Preview PDF not found")
        tmpl_slug = tmpl.slug if tmpl else "ats-classic"
        pdf_bytes = render_structured_data_to_pdf(structured_data, title=source_resume.title, template_slug=tmpl_slug)
        if not pdf_bytes:
            raise HTTPException(status_code=404, detail="Could not generate preview PDF")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="tailored_preview.pdf"',
            "Cache-Control": "private, no-store, max-age=0"
        }
    )


@router.post("/resume-tailoring/save")
def save_tailored_resume(
    payload: SaveTailoredResumeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Saves tailored resume as a NEW resume record linked to source resume.
    Leaves original source resume 100% untouched.
    Compiles and stores final PDF with the user-selected template.
    """
    candidate = _get_or_create_candidate(current_user, db)
    source_resume = db.query(Resume).filter(Resume.id == payload.source_resume_id, Resume.deleted_at == None).first()
    if not source_resume:
        raise HTTPException(status_code=404, detail="Source resume not found")

    _verify_resume_ownership(source_resume, current_user, candidate)

    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == payload.selected_template_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Selected template not found")

    latex_source = render_resume_to_latex(payload.tailored_resume_data, tmpl.latex_template or "")

    title = payload.custom_title or f"{source_resume.title} — {payload.job_title} ({payload.company_name})"
    safe_title = _sanitize_filename(title)

    # Compile final PDF
    pdf_bytes = None
    if is_latex_installed():
        success, pdf_bytes, _ = compile_latex_to_pdf(latex_source)
    else:
        tmpl_slug = tmpl.slug or "ats-classic"
        pdf_bytes = render_structured_data_to_pdf(
            payload.tailored_resume_data,
            title=title,
            template_slug=tmpl_slug
        )
        success = True

    # Upload final PDF to user private storage
    user_folder = get_user_folder_name(current_user)
    pdf_filename = f"tailored_{int(datetime.utcnow().timestamp())}_{safe_title}.pdf"
    pdf_url = None
    if pdf_bytes:
        pdf_url = storage_service.upload_file(
            folder=f"{user_folder}/resumes",
            filename=pdf_filename,
            content=pdf_bytes,
            mime_type="application/pdf"
        )

    # Create new Resume row
    new_resume = Resume(
        candidate_id=candidate.id,
        title=title,
        source_type="tailored",
        template_id=tmpl.id,
        latest_pdf_url=pdf_url,
        file_name=pdf_filename,
        file_type="PDF",
        file_size=len(pdf_bytes) if pdf_bytes else 0,
        status="active",
        extraction_status="verified",
        parser_version="v2.0-tailored",
        is_verified=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    db.add(new_resume)
    db.flush()

    # Create ResumeVersion 1
    new_version = ResumeVersion(
        resume_id=new_resume.id,
        version_number=1,
        structured_data=payload.tailored_resume_data,
        latex_source=latex_source,
        pdf_file_url=pdf_url,
        change_summary=f"Tailored from #{source_resume.id} for {payload.job_title} at {payload.company_name}",
        created_by=current_user.id,
        created_at=datetime.utcnow()
    )
    db.add(new_version)
    db.flush()

    new_resume.current_version_id = new_version.id

    # Sync extraction companion tables for downstream features
    sync_extraction_to_database(
        db=db,
        resume=new_resume,
        structured_data=payload.tailored_resume_data,
        raw_text=json.dumps(payload.tailored_resume_data)
    )

    # Save target Job Description
    if payload.job_description:
        jd_record = JobDescription(
            candidate_id=candidate.id,
            title=payload.job_title,
            company=payload.company_name,
            raw_text=payload.job_description,
            created_at=datetime.utcnow()
        )
        db.add(jd_record)

    db.commit()
    db.refresh(new_resume)

    return {
        "message": "Tailored resume saved successfully as new resume",
        "resume_id": new_resume.id,
        "version_id": new_version.id,
        "title": new_resume.title,
        "template_id": tmpl.id,
        "template_name": tmpl.name,
        "latest_pdf_url": new_resume.latest_pdf_url,
        "source_resume_id": source_resume.id
    }


@router.post("/resume-tailoring/{resume_id}/approve")
def approve_tailored_resume(
    resume_id: int,
    payload: ApproveTailoringRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Explicit candidate approval:
    Saves the proposed tailored data as a new resume (or new version).
    Never overwrites original resume without confirmation.
    """
    candidate = _get_or_create_candidate(current_user, db)
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.deleted_at == None).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    _verify_resume_ownership(resume, current_user, candidate)

    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == resume.template_id).first()
    latex_source = render_resume_to_latex(payload.approved_resume_data, tmpl.latex_template if tmpl else "")

    if payload.create_new_resume:
        # Create as brand-new tailored resume (leaving original resume untouched)
        title = payload.new_title or f"{resume.title} (Tailored)"
        new_resume = Resume(
            candidate_id=candidate.id,
            title=title,
            source_type="tailored",
            template_id=resume.template_id,
            status="active",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(new_resume)
        db.flush()

        new_version = ResumeVersion(
            resume_id=new_resume.id,
            version_number=1,
            structured_data=payload.approved_resume_data,
            latex_source=latex_source,
            change_summary=payload.change_summary or "Approved tailored version",
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.add(new_version)
        db.flush()

        new_resume.current_version_id = new_version.id
        db.commit()
        db.refresh(new_resume)

        return {
            "message": "Tailored resume created successfully as new resume",
            "resume_id": new_resume.id,
            "version_id": new_version.id,
            "title": new_resume.title
        }

    else:
        # Save as new version on existing resume
        latest_v = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()
        next_num = (latest_v.version_number + 1) if latest_v else 1

        new_version = ResumeVersion(
            resume_id=resume.id,
            version_number=next_num,
            structured_data=payload.approved_resume_data,
            latex_source=latex_source,
            change_summary=payload.change_summary or f"Version {next_num} (Approved tailored update)",
            created_by=current_user.id,
            created_at=datetime.utcnow()
        )
        db.add(new_version)
        db.flush()

        resume.current_version_id = new_version.id
        resume.updated_at = datetime.utcnow()
        db.commit()

        return {
            "message": f"Tailored changes saved as Version {next_num}",
            "resume_id": resume.id,
            "version_id": new_version.id,
            "version_number": next_num
        }


@router.post("/resumes/ai-enhance")
def enhance_resume_section(
    payload: SectionEnhanceRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Improves resume text (professional summary, experience bullet, or project description)
    using AI or deterministic lexical action-verb enhancement.
    Strictly preserves the user's authentic facts with ZERO hallucinations.
    """
    from app.services.ai_provider import ai_provider_service

    orig_text = payload.text.strip()
    section = payload.section.lower()
    context = payload.context or ""

    prompt = f"""You are a professional resume editor and ATS optimization expert.
Improve the following candidate {section} for a resume.

CONTEXT / TITLE: {context}
ORIGINAL TEXT:
{orig_text}

STRICT ANTI-HALLUCINATION RULES:
1. Preserve all factual claims, metrics, technologies, and dates from the original text.
2. DO NOT invent new skills, metrics, percentages, achievements, or employment roles.
3. Use strong active voice action verbs (e.g. Engineered, Spearheaded, Optimized, Architected).
4. Make the text punchy, professional, and ATS-parseable.
5. Return ONLY the enhanced text without quotation marks, conversational intros, or explanations.
"""

    enhanced = None
    if (ai_provider_service.is_gemini_configured() or
        ai_provider_service.is_nvidia_configured() or
        ai_provider_service.is_groq_configured()):
        try:
            res = ai_provider_service.call_with_fallback(prompt, json_mode=False)
            if res and res.strip():
                enhanced = res.strip().strip('"').strip("'")
        except Exception as e:
            logger.warning(f"AI section enhancement fallback to rule-based: {e}")

    if not enhanced:
        # Deterministic active-verb polishing fallback
        replacements = [
            ("worked on", "Engineered"),
            ("helped with", "Collaborated on"),
            ("responsible for", "Spearheaded"),
            ("made", "Architected"),
            ("did", "Executed"),
            ("fixed", "Resolved"),
            ("managed", "Orchestrated"),
        ]
        res = orig_text
        for old, new in replacements:
            res = re.sub(r"\b" + re.escape(old) + r"\b", new, res, flags=re.IGNORECASE)
        enhanced = res

    return {
        "section": section,
        "original": orig_text,
        "enhanced": enhanced
    }


# ─────────────────────────────────────────────────────────────────────────────
# JD-DRIVEN ATS RESUME OPTIMIZATION ENGINE ENDPOINTS (Rules 21, 22, 23, 24)
# ─────────────────────────────────────────────────────────────────────────────

class JDOptimizeRequest(BaseModel):
    resume_id: Optional[int] = Field(None, description="Candidate master resume ID. Defaults to active resume.")
    job_description: str = Field(..., min_length=20, description="Full job description text to optimize against.")
    template_id: Optional[int] = Field(None, description="Target LaTeX template ID.")
    job_title: Optional[str] = Field(None, description="Target job title.")
    company: Optional[str] = Field(None, description="Target company name.")
    # Optional links to Job and Application entities for bidirectional tracking
    job_id: Optional[int] = Field(None, description="Job entity ID from the jobs table (optional).")
    application_id: Optional[int] = Field(None, description="Application entity ID to link this optimization to (optional).")
    force_new: bool = Field(False, description="If True, create a new optimization even if an identical one (same jd_hash) already exists.")
    # Mode selection: "template" (Mode A - choose a template) | "original_layout" (Mode B - edit uploaded original)
    rendering_mode: Optional[str] = Field("template", description="Rendering mode: 'template' or 'original_layout'")


@router.post("/resume/optimize")
@router.post("/resumes/optimize")
async def optimize_resume_for_job(
    req: JDOptimizeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Executes the 10-step JD-driven ATS resume optimization engine:
    - Idempotent: returns the existing optimization if the same (candidate, master_resume, JD) triple
      already has a saved record (same jd_hash), unless force_new=True.
    - Stores optimization as structured JSON snapshot — does NOT generate a PDF file.
    - PDF/DOCX are generated on-demand at download time from the saved snapshot.
    - Master Resume is never modified.
    """
    from app.services.resume_snapshot_service import (
        compute_jd_hash, compute_content_hash, find_existing_optimization, build_optimization_response
    )

    cand = _get_or_create_candidate(current_user, db)

    # 1. Resolve Master Resume
    if req.resume_id:
        master_resume = db.query(Resume).filter(
            Resume.id == req.resume_id,
            Resume.candidate_id == cand.id,
            Resume.deleted_at == None
        ).first()
        if not master_resume:
            raise HTTPException(status_code=404, detail="Master resume not found")
    else:
        # Resolve active resume
        master_resume = None
        if cand.active_resume_id:
            master_resume = db.query(Resume).filter(
                Resume.id == cand.active_resume_id,
                Resume.candidate_id == cand.id,
                Resume.deleted_at == None
            ).first()
        if not master_resume:
            master_resume = db.query(Resume).filter(
                Resume.candidate_id == cand.id,
                Resume.is_active == True,
                Resume.deleted_at == None
            ).order_by(Resume.updated_at.desc()).first()
        if not master_resume:
            master_resume = db.query(Resume).filter(
                Resume.candidate_id == cand.id,
                Resume.deleted_at == None
            ).order_by(Resume.updated_at.desc()).first()

    if not master_resume:
        raise HTTPException(
            status_code=400,
            detail="No candidate resume found. Please upload or create a master resume first."
        )

    # 2. Idempotency check — reuse existing record if JD hash matches
    jd_hash = compute_jd_hash(req.job_description)
    if not req.force_new:
        existing_opt = find_existing_optimization(
            db, cand.id, master_resume.id, jd_hash
        )
        if existing_opt:
            logger.info(
                f"Idempotency hit: reusing optimization {existing_opt.id} "
                f"for candidate {cand.id} / resume {master_resume.id}"
            )
            # If caller provided application_id, link them now (idempotent)
            if req.application_id and existing_opt.application_id != req.application_id:
                from app.services.resume_snapshot_service import link_optimization_to_application
                try:
                    link_optimization_to_application(
                        db, existing_opt.id, req.application_id, cand.id, commit=True
                    )
                    db.refresh(existing_opt)
                except Exception:
                    pass  # Non-fatal: linking is best-effort
            return build_optimization_response(existing_opt)

    # 3. Extract Master Structured Data (IMMUTABLE source — never modified)
    latest_version = db.query(ResumeVersion).filter(
        ResumeVersion.resume_id == master_resume.id
    ).order_by(ResumeVersion.version_number.desc()).first()

    master_data = latest_version.structured_data if (latest_version and latest_version.structured_data) else {}
    if not master_data:
        master_data = _build_structured_data_from_models(master_resume)

    if not master_data:
        raise HTTPException(
            status_code=400,
            detail="Master resume has no structured data available for ATS optimization."
        )

    # 4. Execute Master Optimization Engine (LLM call — only here, never at download/reopen)
    opt_result = run_full_jd_optimization(
        master_resume_data=master_data,
        job_description_text=req.job_description,
        job_title=req.job_title,
        company=req.company
    )

    # 5. Compute content hash for render cache key
    content_hash = compute_content_hash(opt_result.optimized_resume)

    # 6. Determine template version
    tmpl_version = None
    if req.template_id:
        tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == req.template_id).first()
        if tmpl:
            tmpl_version = f"v{tmpl.id}"

    # 7. Store Job Description in DB
    jd_record = JobDescription(
        candidate_id=cand.id,
        title=opt_result.job_title,
        company=opt_result.company,
        raw_text=req.job_description,
        extracted_requirements={
            "required_skills": opt_result.parsed_jd.required_skills,
            "preferred_skills": opt_result.parsed_jd.preferred_skills,
            "responsibilities": opt_result.parsed_jd.responsibilities,
            "seniority": opt_result.parsed_jd.seniority
        }
    )
    db.add(jd_record)
    db.flush()

    # 8. Determine Optimization Version (per-candidate-resume count)
    prior_opts_count = db.query(ResumeOptimization).filter(
        ResumeOptimization.master_resume_id == master_resume.id,
        ResumeOptimization.candidate_id == cand.id
    ).count()

    # 9. Store ResumeOptimization Record (structured JSON snapshot only — no PDF stored)
    ats_report_payload = opt_result.ats_scores.model_dump()
    ats_report_payload["resume_match_score"] = opt_result.resume_match_score
    ats_report_payload["score_breakdown"] = opt_result.score_breakdown
    ats_report_payload["score_explanation"] = opt_result.score_explanation.model_dump()
    ats_report_payload["skill_gaps"] = opt_result.skill_gaps.model_dump()
    ats_report_payload["application_readiness"] = opt_result.application_readiness.model_dump()
    ats_report_payload["prepared_application"] = opt_result.prepared_application.model_dump()

    # Determine mode & fidelity tier
    req_mode = (req.rendering_mode or "template").lower()
    fidelity = "template_fallback"
    if req_mode == "original_layout":
        if (master_resume.file_type or "").upper() == "DOCX" or (master_resume.file_name or "").lower().endswith(".docx"):
            fidelity = "original_layout_preserved"
        elif (master_resume.file_type or "").upper() == "PDF" or (master_resume.file_name or "").lower().endswith(".pdf"):
            fidelity = "reconstructed_from_original"
        else:
            fidelity = "template_fallback"

    opt_record = ResumeOptimization(
        candidate_id=cand.id,
        master_resume_id=master_resume.id,
        job_description_id=jd_record.id,
        job_id=req.job_id,
        application_id=req.application_id,
        template_id=req.template_id,
        template_version=tmpl_version,
        rendering_mode=req_mode,
        fidelity_tier=fidelity,
        optimization_version=prior_opts_count + 1,
        jd_hash=jd_hash,
        content_hash=content_hash,
        ats_score=opt_result.ats_scores.overall_ats_score,
        keyword_score=opt_result.ats_scores.keyword_match,
        experience_score=opt_result.ats_scores.experience_match,
        technical_score=opt_result.ats_scores.technical_match,
        responsibility_score=opt_result.ats_scores.responsibility_match,
        alignment_score=opt_result.ats_scores.alignment_score,
        quality_score=opt_result.ats_scores.quality_score,
        truthfulness_score=opt_result.truthfulness_score,
        job_title=opt_result.job_title,
        company=opt_result.company,
        optimized_data=opt_result.optimized_resume,
        matched_skills=opt_result.ats_scores.matched_skills,
        partial_matches=opt_result.ats_scores.partial_matches,
        missing_skills=opt_result.ats_scores.missing_skills,
        recommendations=opt_result.ats_scores.recommendations,
        ats_report=ats_report_payload
    )
    db.add(opt_record)
    db.flush()

    # 10. Store Evidence Mapping Items
    for ev in opt_result.evidence_matches:
        db.add(ResumeOptimizationEvidence(
            optimization_id=opt_record.id,
            jd_requirement=ev.jd_requirement,
            candidate_evidence=ev.candidate_evidence,
            match_type=ev.match_type,
            confidence=ev.confidence,
            category=ev.category
        ))

    # 11. If application_id supplied, link Application.optimization_id → this record
    if req.application_id:
        from app.models.job_models import Application as ApplicationModel
        app_rec = db.query(ApplicationModel).filter(
            ApplicationModel.id == req.application_id,
            ApplicationModel.candidate_id == cand.id
        ).first()
        if app_rec:
            app_rec.optimization_id = opt_record.id

    db.commit()
    db.refresh(opt_record)

    return build_optimization_response(opt_record)


@router.get("/resume/optimize/{optimization_id}")
@router.get("/resumes/optimize/{optimization_id}")
def get_resume_optimization(
    optimization_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves a saved resume optimization record with evidence mapping.
    Deterministic read: does NOT re-run any LLM or optimizer.
    """
    from app.services.resume_snapshot_service import get_optimization_by_id, build_optimization_response

    cand = _get_or_create_candidate(current_user, db)
    opt = get_optimization_by_id(db, optimization_id, cand.id)
    return build_optimization_response(opt)


@router.get("/applications/{application_id}/resume-snapshot")
@router.get("/job-agent/applications/{application_id}/resume-snapshot")
def get_application_resume_snapshot(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieves the exact saved resume snapshot used for this specific application.
    Tenant isolated: Candidate A cannot access Candidate B's application or resume snapshot.
    Deterministic read: Reopening an application does NOT trigger a new LLM optimization.
    """
    from app.services.resume_snapshot_service import get_optimization_for_application, build_optimization_response

    cand = _get_or_create_candidate(current_user, db)
    opt = get_optimization_for_application(db, application_id, cand.id)
    if not opt:
        raise HTTPException(
            status_code=404,
            detail="No resume optimization snapshot linked to this application."
        )
    return build_optimization_response(opt)


class ConfirmApplicationRequest(BaseModel):
    confirmed_fields: Dict[str, Any] = Field(default_factory=dict)
    user_acknowledged: bool = Field(..., description="Explicit acknowledgement by the user.")


class ApproveOptimizationRequest(BaseModel):
    user_acknowledged: bool = Field(..., description="Explicit approval by candidate.")
    notes: Optional[str] = Field(None, description="Optional candidate approval notes.")
    accepted_warnings: List[str] = Field(default_factory=list, description="List of accepted layout/evidence warnings.")


@router.post("/resume/optimize/{optimization_id}/approve")
@router.post("/resumes/optimize/{optimization_id}/approve")
def approve_optimization_endpoint(
    optimization_id: int,
    payload: ApproveOptimizationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Explicit Candidate Approval Gate:
    Records that the candidate reviewed and explicitly approved this specific optimization revision
    and its rendered artifact/content before platform-managed submission or prepared-application linking.
    """
    from app.services.resume_snapshot_service import get_optimization_by_id, build_optimization_response

    if not payload.user_acknowledged:
        raise HTTPException(
            status_code=400,
            detail="Candidate approval must be explicitly acknowledged."
        )

    cand = _get_or_create_candidate(current_user, db)
    opt = get_optimization_by_id(db, optimization_id, cand.id)

    opt.candidate_approved = True
    opt.approved_at = datetime.utcnow()
    opt.approval_hash = opt.content_hash
    opt.approval_notes = payload.notes
    db.commit()
    db.refresh(opt)

    return {
        "status": "APPROVED",
        "message": f"Optimization revision #{opt.optimization_version} explicitly approved by candidate.",
        "optimization_id": opt.id,
        "approved_at": opt.approved_at.isoformat(),
        "approval_hash": opt.approval_hash,
        "optimization": build_optimization_response(opt)
    }



@router.post("/resume/optimize/{optimization_id}/prepare-application")
@router.post("/resumes/optimize/{optimization_id}/prepare-application")
def prepare_application_endpoint(
    optimization_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Prepares structured form autofill fields for candidate review.
    Categorizes fields into EXACT_FIELD, SEMANTIC_FIELD, and MISSING_INFORMATION.
    Strictly forbids autonomous submission.
    """
    cand = _get_or_create_candidate(current_user, db)
    opt = db.query(ResumeOptimization).filter(
        ResumeOptimization.id == optimization_id,
        ResumeOptimization.candidate_id == cand.id
    ).first()
    if not opt:
        raise HTTPException(status_code=404, detail="Optimization record not found")

    report = opt.ats_report or {}
    prepared_app = report.get("prepared_application")
    if not prepared_app:
        from app.services.ats_optimizer import parse_job_description, prepare_application_draft
        master_resume = db.query(Resume).filter(Resume.id == opt.master_resume_id).first()
        master_data = _build_structured_data_from_models(master_resume) if master_resume else {}
        parsed_jd = parse_job_description(opt.job_description.raw_text if opt.job_description else "", override_title=opt.job_title, override_company=opt.company)
        draft = prepare_application_draft(master_data, parsed_jd, opt.optimized_data)
        prepared_app = draft.model_dump()
        report["prepared_application"] = prepared_app
        opt.ats_report = report
        db.commit()

    return prepared_app


@router.post("/resume/optimize/{optimization_id}/confirm-application")
@router.post("/resumes/optimize/{optimization_id}/confirm-application")
def confirm_application_endpoint(
    optimization_id: int,
    payload: ConfirmApplicationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    User review step for application form data:
    1. Transitions status to CONFIRMED.
    2. Marks the ResumeOptimization record as submitted and immutable (locks it from mutation).
    3. Preserves the exact submitted document artifact in private cloud storage.
    4. If application_id is linked, records submitted state.
    """
    from app.services.resume_snapshot_service import (
        get_optimization_by_id, render_pdf_from_snapshot,
        preserve_submitted_artifact, lock_optimization_as_submitted
    )

    if not payload.user_acknowledged:
        raise HTTPException(
            status_code=400,
            detail="Application cannot be confirmed without explicit user review and acknowledgment."
        )

    cand = _get_or_create_candidate(current_user, db)
    opt = get_optimization_by_id(db, optimization_id, cand.id)

    # 1. Update ATS report prepared_application status
    report = opt.ats_report or {}
    prepared_app = report.get("prepared_application", {})
    prepared_app["status"] = "CONFIRMED"
    prepared_app["requires_user_confirmation"] = False
    prepared_app["confirmed_at"] = datetime.utcnow().isoformat()
    prepared_app["confirmed_by_user"] = True
    prepared_app["submission_allowed"] = False
    report["prepared_application"] = prepared_app
    opt.ats_report = report

    # 2. Render and preserve exact submitted artifact in private storage
    artifact_url = opt.submitted_artifact_url
    if not artifact_url:
        try:
            pdf_bytes = render_pdf_from_snapshot(opt, db, cand.id)
            user_folder = get_user_folder_name(current_user)
            artifact_url = preserve_submitted_artifact(
                db=db,
                opt=opt,
                candidate_id=cand.id,
                pdf_bytes=pdf_bytes,
                user_folder=user_folder,
            )
        except Exception as e:
            logger.warning(f"Failed to preserve submitted artifact for opt {opt.id}: {e}")

    # 3. Lock optimization as submitted and immutable
    lock_optimization_as_submitted(
        db=db,
        optimization_id=opt.id,
        candidate_id=cand.id,
        artifact_url=artifact_url,
        commit=True
    )

    return {
        "status": "CONFIRMED",
        "message": "Application draft reviewed and confirmed by candidate. Submitted resume snapshot is preserved and locked.",
        "is_submitted": True,
        "is_immutable": True,
        "submitted_artifact_url": opt.submitted_artifact_url,
        "prepared_application": prepared_app
    }


@router.get("/resume/optimize/{optimization_id}/download/pdf")
@router.get("/resumes/optimize/{optimization_id}/download/pdf")
def download_optimized_resume_pdf(
    optimization_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generates and downloads a clean ATS-formatted PDF of the optimized resume.
    Deterministic: Renders on demand from saved structured JSON without calling LLM.
    If already submitted, serves the preserved submitted artifact.
    """
    from app.services.resume_snapshot_service import get_optimization_by_id, render_pdf_from_snapshot

    cand = _get_or_create_candidate(current_user, db)
    opt = get_optimization_by_id(db, optimization_id, cand.id)

    pdf_bytes = render_pdf_from_snapshot(opt, db, cand.id)
    safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', opt.job_title or 'Optimized_Resume')
    filename = f"Resume_{safe_title}_ATS{opt.ats_score}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-cache, max-age=0"
        }
    )


@router.get("/resume/optimize/{optimization_id}/download/docx")
@router.get("/resumes/optimize/{optimization_id}/download/docx")
def download_optimized_resume_docx(
    optimization_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generates and downloads an ATS-formatted Microsoft Word (.docx) of the optimized resume.
    Deterministic: Renders on demand from saved structured JSON without calling LLM.
    """
    from app.services.resume_snapshot_service import get_optimization_by_id, render_docx_from_snapshot

    cand = _get_or_create_candidate(current_user, db)
    opt = get_optimization_by_id(db, optimization_id, cand.id)

    docx_bytes = render_docx_from_snapshot(opt, cand.id)
    safe_title = re.sub(r'[^a-zA-Z0-9_-]', '_', opt.job_title or 'Optimized_Resume')
    filename = f"Resume_{safe_title}_ATS{opt.ats_score}.docx"

    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache"
        }
    )


class SaveOptimizedResumeRequest(BaseModel):
    custom_title: Optional[str] = None
    template_id: Optional[int] = None
    set_as_active: bool = False


@router.post("/resume/optimize/{optimization_id}/save-as-resume")
@router.post("/resumes/optimize/{optimization_id}/save-as-resume")
async def save_optimized_as_resume(
    optimization_id: int,
    req: SaveOptimizedResumeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Saves an optimized resume analysis as a new derived resume in candidate's repository.
    Strictly preserves the Master Resume without modifying it.
    """
    cand = _get_or_create_candidate(current_user, db)
    opt = db.query(ResumeOptimization).filter(
        ResumeOptimization.id == optimization_id,
        ResumeOptimization.candidate_id == cand.id
    ).first()
    if not opt:
        raise HTTPException(status_code=404, detail="Optimization record not found")

    title = req.custom_title or f"ATS Optimized — {opt.job_title} ({opt.company or 'Target'})"

    # Create new derived resume
    new_resume = Resume(
        candidate_id=cand.id,
        title=title,
        source_type="tailored",
        template_id=req.template_id or opt.template_id,
        is_active=req.set_as_active,
        status="active" if req.set_as_active else "tailored",
        extraction_status="verified",
        is_verified=True
    )
    db.add(new_resume)
    db.flush()

    # Create initial version
    version = ResumeVersion(
        resume_id=new_resume.id,
        version_number=1,
        structured_data=opt.optimized_data,
        change_summary=f"Derived ATS optimization for {opt.job_title} at {opt.company}. ATS Score: {opt.ats_score}/100.",
        created_by=current_user.id
    )
    db.add(version)
    db.flush()

    new_resume.current_version_id = version.id

    # If requested as active, archive previous active
    if req.set_as_active:
        cand.active_resume_id = new_resume.id
        db.query(Resume).filter(
            Resume.candidate_id == cand.id,
            Resume.id != new_resume.id,
            Resume.is_active == True
        ).update({"is_active": False, "status": "archived"})

    # Compile PDF
    pdf_bytes = render_structured_data_to_pdf(opt.optimized_data)
    user_folder = get_user_folder_name(current_user)
    pdf_filename = f"optimized_{new_resume.id}_v1.pdf"
    pdf_url = storage_service.upload_file(
        folder=f"{user_folder}/resumes",
        filename=pdf_filename,
        content=pdf_bytes,
        mime_type="application/pdf"
    )

    new_resume.latest_pdf_url = pdf_url
    version.pdf_file_url = pdf_url

    db.commit()
    db.refresh(new_resume)

    return {
        "message": "Optimized resume saved successfully as a new derived resume.",
        "resume_id": new_resume.id,
        "title": new_resume.title,
        "is_active": new_resume.is_active,
        "ats_score": opt.ats_score,
        "pdf_url": pdf_url
    }


# ─────────────────────────────────────────────────────────────────────────────
# RESUME PROJECTS REPAIR & MAINTENANCE ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/resumes/maintenance/inspect/{target_resume_id}")
def inspect_resume_for_maintenance(
    target_resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Diagnostic endpoint to inspect stored project data, bullet counts,
    and canonicalization diffs for a specific resume.
    """
    resume = db.query(Resume).filter(Resume.id == target_resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    cand = db.query(Candidate).filter(Candidate.id == resume.candidate_id).first()
    cand_user = db.query(User).filter(User.id == cand.user_id).first() if cand else None

    # Get active or latest version
    version = None
    if resume.current_version_id:
        version = db.query(ResumeVersion).filter(ResumeVersion.id == resume.current_version_id).first()
    if not version:
        version = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()

    raw_projs = []
    if version and version.structured_data and isinstance(version.structured_data, dict):
        raw_projs = version.structured_data.get("projects") or []

    canon_projs = canonicalize_projects_list(raw_projs)

    # Check database table projects
    db_projs = db.query(ResumeProject).filter(ResumeProject.resume_id == resume.id).all()
    db_projs_list = [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "responsibilities_count": len(p.responsibilities or []),
            "responsibilities": p.responsibilities or [],
            "features_count": len(p.features or []),
            "features": p.features or [],
            "technologies": p.technologies or []
        }
        for p in db_projs
    ]

    return {
        "resume_id": resume.id,
        "title": resume.title,
        "candidate_id": resume.candidate_id,
        "user_email": cand_user.email if cand_user else None,
        "user_id": cand_user.id if cand_user else None,
        "status": resume.status,
        "latest_pdf_url": resume.latest_pdf_url,
        "version_number": version.version_number if version else None,
        "raw_projects_count": len(raw_projs),
        "raw_projects": raw_projs,
        "canonical_projects": canon_projs,
        "has_duplication_in_version": raw_projs != canon_projs,
        "db_projects_table": db_projs_list
    }


@router.post("/resumes/maintenance/repair-projects")
def run_repair_projects_endpoint(
    apply: bool = Query(False, description="Apply changes to the database and invalidate stale caches. Default false (dry-run)."),
    resume_id: Optional[int] = Query(None, description="Optional specific resume ID to target."),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Triggers safe project deduplication repair and cache invalidation.
    Supports dry-run preview and live commit with structured response.
    """
    import sys
    from pathlib import Path
    backend_root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    try:
        from repair_resume_projects import repair_in_session
    except ImportError:
        raise HTTPException(status_code=500, detail="repair_resume_projects module not found")

    result = repair_in_session(session=db, apply_changes=apply, target_resume_id=resume_id, log_output=False)
    return result


@router.post("/resumes/maintenance/compile/{target_resume_id}")
def compile_resume_maintenance(
    target_resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Direct maintenance compilation endpoint that ensures canonicalization,
    re-renders LaTeX and fallback PDF, and invalidates/updates the cache.
    """
    resume = db.query(Resume).filter(Resume.id == target_resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    version = None
    if resume.current_version_id:
        version = db.query(ResumeVersion).filter(ResumeVersion.id == resume.current_version_id).first()
    if not version:
        version = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()
    if not version:
        raise HTTPException(status_code=400, detail="No resume version found")

    # Ensure canonical projects in structured data
    if version.structured_data and isinstance(version.structured_data, dict):
        raw_projs = version.structured_data.get("projects") or []
        canon_projs = canonicalize_projects_list(raw_projs)
        updated_sd = dict(version.structured_data)
        updated_sd["projects"] = canon_projs
        version.structured_data = updated_sd

    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == resume.template_id).first()
    tmpl_slug = tmpl.slug if tmpl else "ats-classic"

    # Render LaTeX
    latex_source = render_resume_to_latex(version.structured_data, tmpl.latex_template if tmpl else "")
    version.latex_source = latex_source

    # Render PDF via fallback / reportlab
    pdf_bytes = render_structured_data_to_pdf(version.structured_data, resume.title, template_slug=tmpl_slug)
    user_folder = get_user_folder_name(current_user)
    pdf_filename = f"resume_{resume.id}_v{version.version_number}_compiled.pdf"
    pdf_url = storage_service.upload_file(
        folder=f"{user_folder}/resumes",
        filename=pdf_filename,
        content=pdf_bytes,
        mime_type="application/pdf"
    )

    resume.latest_pdf_url = pdf_url
    resume.status = "COMPLETED"
    version.pdf_file_url = pdf_url

    db.commit()
    db.refresh(resume)

    return {
        "message": "Resume successfully compiled with canonicalized projects.",
        "resume_id": resume.id,
        "title": resume.title,
        "latest_pdf_url": pdf_url,
        "pdf_size": len(pdf_bytes),
        "projects_count": len(version.structured_data.get("projects", []))
    }


@router.get("/resumes/maintenance/preview-pdf/{target_resume_id}")
def preview_pdf_maintenance(
    target_resume_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Downloads the freshly compiled PDF bytes directly for verification.
    """
    resume = db.query(Resume).filter(Resume.id == target_resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    version = None
    if resume.current_version_id:
        version = db.query(ResumeVersion).filter(ResumeVersion.id == resume.current_version_id).first()
    if not version:
        version = db.query(ResumeVersion).filter(ResumeVersion.resume_id == resume.id).order_by(ResumeVersion.version_number.desc()).first()

    tmpl = db.query(ResumeTemplate).filter(ResumeTemplate.id == resume.template_id).first()
    tmpl_slug = tmpl.slug if tmpl else "ats-classic"

    pdf_bytes = render_structured_data_to_pdf(version.structured_data, resume.title, template_slug=tmpl_slug)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="resume_{resume.id}.pdf"'}
    )


