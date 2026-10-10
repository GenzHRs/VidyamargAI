from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Response, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any, Union, Tuple
from datetime import datetime, timedelta
import json
import logging
import os
import uuid
import time
import asyncio

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user, get_current_admin
from app.schemas import schemas
from app.models.models import User, Candidate, CandidateProfile
from app.models.job_models import SkillGapAnalysis
from app.models.resume_center_models import (
    Resume, ResumeVersion, ResumeProfile, ResumeExperience,
    ResumeProject, ResumeSkill, ResumeEducation, ResumeCertification
)
from app.services.resume_context_service import ResumeContextService

logger = logging.getLogger(__name__)

router = APIRouter()

# ----------------- CANDIDATE PROFILE & RESUME -----------------

@router.get("/candidates/profile")
def get_candidate_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    candidate = db.query(Candidate).options(joinedload(Candidate.user)).filter(Candidate.user_id == current_user.id).first()
    if not candidate:
        candidate = Candidate(user_id=current_user.id, status="Registered", current_step="Profile")
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        candidate = db.query(Candidate).options(joinedload(Candidate.user)).filter(Candidate.user_id == current_user.id).first()

    # 1. Resolve Active Resume for Candidate
    active_resume, latest_version, s_data = ResumeContextService.get_active_resume(db, candidate.id)

    # Base personal info & links from user and candidate records
    personal_info = {
        "full_name": candidate.parsed_name or current_user.full_name or "Not available",
        "email": candidate.parsed_email or current_user.email or "Not available",
        "phone": candidate.phone or "Not available",
        "location": candidate.address or "Not available",
        "address": candidate.address or "Not available"
    }
    links = {
        "linkedin": candidate.linkedin or "",
        "github": candidate.github or "",
        "portfolio": candidate.portfolio or ""
    }

    exps_data = []
    projs_data = []
    skills_data = []
    edus_data = []
    certs_data = []
    achievements_data = []
    languages_data = []

    summary_text = candidate.summary or ""

    if active_resume:
        # Fetch normalized records from PostgreSQL tables
        prof = db.query(ResumeProfile).filter(ResumeProfile.resume_id == active_resume.id).first()
        if prof:
            if prof.full_name: personal_info["full_name"] = prof.full_name
            if prof.email: personal_info["email"] = prof.email
            if prof.phone: personal_info["phone"] = prof.phone
            if prof.location:
                personal_info["location"] = prof.location
                personal_info["address"] = prof.location
            if prof.linkedin_url: links["linkedin"] = prof.linkedin_url
            if prof.github_url: links["github"] = prof.github_url
            if prof.portfolio_url: links["portfolio"] = prof.portfolio_url
            if prof.professional_summary: summary_text = prof.professional_summary

        # 2. Employment History (STRICT Company ↔ Designation distinction)
        db_exps = db.query(ResumeExperience).filter(ResumeExperience.resume_id == active_resume.id).order_by(ResumeExperience.sort_order.asc(), ResumeExperience.id.asc()).all()
        for e in db_exps:
            exps_data.append({
                "company": e.employer or "",           # Company / Employer
                "employer": e.employer or "",
                "designation": e.designation or "",   # Job title / Designation
                "role": e.designation or "",
                "employment_type": e.employment_type or "Full-time",
                "location": e.employment_location or "",
                "start_date": e.start_date or "",
                "end_date": e.end_date if not e.is_current else "Present",
                "is_current": e.is_current,
                "responsibilities": e.responsibilities or [],
                "achievements": e.achievements or [],
                "technologies": e.technologies or []
            })

        # 3. Projects
        db_projs = db.query(ResumeProject).filter(ResumeProject.resume_id == active_resume.id).order_by(ResumeProject.id.asc()).all()
        for p in db_projs:
            projs_data.append({
                "name": p.name or "",
                "project_name": p.name or "",
                "description": p.description or "",
                "technologies": p.technologies or [],
                "responsibilities": p.responsibilities or [],
                "achievements": getattr(p, "results_metrics", []) or getattr(p, "features", []) or [],
                "start_date": getattr(p, "duration", "") or "",
                "end_date": "",
                "url": p.link or ""
            })

        # 4. Skills
        db_skills = db.query(ResumeSkill).filter(ResumeSkill.resume_id == active_resume.id).all()
        for s in db_skills:
            skills_data.append({
                "name": s.name,
                "category": s.category or "Other Skills",
                "source_text": s.source_text,
                "proficiency": s.proficiency
            })

        # 5. Education
        db_edus = db.query(ResumeEducation).filter(ResumeEducation.resume_id == active_resume.id).all()
        for ed in db_edus:
            edus_data.append({
                "degree": ed.degree or "",
                "institution": ed.institution or "",
                "field_of_study": ed.field_of_study or "",
                "start_date": ed.start_date or "",
                "end_date": ed.end_date or ed.graduation_year or "",
                "gpa": getattr(ed, "grade", "") or "",
                "grade": getattr(ed, "grade", "") or ""
            })

        # 6. Certifications
        db_certs = db.query(ResumeCertification).filter(ResumeCertification.resume_id == active_resume.id).all()
        for c in db_certs:
            certs_data.append({
                "name": c.name or "",
                "certification_name": c.name or "",
                "issuer": c.issuing_organization or "",
                "date": c.issue_date or "",
                "credential_id": c.credential_id or "",
                "credential_url": c.credential_url or ""
            })

        # Fallback to s_data JSON if normalized tables were empty
        if not exps_data and s_data:
            s_exps = s_data.get("work_experience") or s_data.get("experience") or []
            for item in s_exps:
                if isinstance(item, dict):
                    exps_data.append({
                        "company": item.get("employer") or item.get("company") or "",
                        "employer": item.get("employer") or item.get("company") or "",
                        "designation": item.get("designation") or item.get("role") or item.get("title") or "",
                        "role": item.get("designation") or item.get("role") or item.get("title") or "",
                        "employment_type": item.get("employment_type") or "Full-time",
                        "location": item.get("location") or item.get("employment_location") or "",
                        "start_date": item.get("start_date") or "",
                        "end_date": item.get("end_date") or "",
                        "responsibilities": item.get("responsibilities") or item.get("bullets") or [],
                        "achievements": item.get("achievements") or [],
                        "technologies": item.get("technologies") or []
                    })

        if not projs_data and s_data:
            s_projs = s_data.get("projects") or []
            for item in s_projs:
                if isinstance(item, dict):
                    projs_data.append({
                        "name": item.get("name") or item.get("title") or "",
                        "project_name": item.get("name") or item.get("title") or "",
                        "description": item.get("description") or "",
                        "technologies": item.get("technologies") or [],
                        "responsibilities": item.get("responsibilities") or item.get("bullets") or [],
                        "achievements": item.get("achievements") or [],
                        "start_date": item.get("start_date") or "",
                        "end_date": item.get("end_date") or "",
                        "url": item.get("url") or item.get("project_url") or ""
                    })

        if not skills_data and s_data:
            s_skills = s_data.get("skills")
            if isinstance(s_skills, list):
                for sk in s_skills:
                    if isinstance(sk, dict):
                        skills_data.append({"name": sk.get("name", ""), "category": sk.get("category", "Other Skills")})
                    else:
                        skills_data.append({"name": str(sk), "category": "Other Skills"})
            elif isinstance(s_skills, dict):
                for cat, sk_list in s_skills.items():
                    if isinstance(sk_list, list):
                        for sk in sk_list:
                            skills_data.append({"name": str(sk), "category": cat})

        if not edus_data and s_data:
            s_edus = s_data.get("education") or []
            for item in s_edus:
                if isinstance(item, dict):
                    edus_data.append({
                        "degree": item.get("degree") or "",
                        "institution": item.get("institution") or item.get("school") or "",
                        "field_of_study": item.get("field_of_study") or "",
                        "start_date": item.get("start_date") or "",
                        "end_date": item.get("end_date") or item.get("graduation_year") or "",
                        "gpa": item.get("gpa") or ""
                    })

    # Parse target roles & evidence
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

    # Sync candidate top-level fields for backwards compatibility
    if personal_info["full_name"] != "Not available": candidate.parsed_name = personal_info["full_name"]
    if personal_info["email"] != "Not available": candidate.parsed_email = personal_info["email"]
    if personal_info["phone"] != "Not available": candidate.phone = personal_info["phone"]
    if personal_info["location"] != "Not available": candidate.address = personal_info["location"]
    if links["linkedin"]: candidate.linkedin = links["linkedin"]
    if links["github"]: candidate.github = links["github"]
    if links["portfolio"]: candidate.portfolio = links["portfolio"]

    if skills_data:
        candidate.skills = ", ".join(list(dict.fromkeys([s["name"] for s in skills_data if isinstance(s, dict) and s.get("name")])))
    if exps_data:
        candidate.experience = json.dumps(exps_data)
    if projs_data:
        candidate.projects = json.dumps(projs_data)
    if edus_data:
        candidate.education = json.dumps(edus_data)

    db.commit()

    return {
        "id": candidate.id,
        "user_id": candidate.user_id,
        "candidate_id": candidate.id,
        "active_resume_id": active_resume.id if active_resume else None,

        "personal_info": personal_info,
        "links": links,
        "professional": {
            "summary": summary_text,
            "primary_designation": candidate.primary_designation or "",
            "target_roles": target_roles_list,
            "role_evidence": role_evidence_list
        },

        "experience": exps_data,
        "experience_list": exps_data,
        "skills": skills_data,
        "skills_list": skills_data,
        "projects": projs_data,
        "projects_list": projs_data,
        "education": edus_data,
        "education_list": edus_data,
        "certifications": certs_data,
        "certifications_list": certs_data,
        "achievements": achievements_data,
        "languages": languages_data,

        # Backward compatibility top-level attributes
        "parsed_name": personal_info["full_name"],
        "parsed_email": personal_info["email"],
        "phone": personal_info["phone"],
        "address": personal_info["location"],
        "summary": summary_text,
        "linkedin": links["linkedin"],
        "github": links["github"],
        "portfolio": links["portfolio"],
        "primary_designation": candidate.primary_designation or "",
        "target_roles": target_roles_list,
        "role_evidence": role_evidence_list,
        "status": candidate.status or "Registered",
        "current_step": candidate.current_step or "Profile",
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role or "candidate"
        }
    }

@router.put("/candidates/profile", response_model=schemas.CandidateResponse)
async def update_candidate_profile(
    profile_in: schemas.CandidateProfileUpdate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    candidate = db.query(Candidate).options(joinedload(Candidate.user)).filter(Candidate.user_id == current_user.id).first()
    if not candidate:
        candidate = Candidate(user_id=current_user.id, status="Registered", current_step="Profile")
        db.add(candidate)
        db.commit()
        db.refresh(candidate)
        candidate = db.query(Candidate).options(joinedload(Candidate.user)).filter(Candidate.user_id == current_user.id).first()
        
    for k, v in profile_in.dict(exclude_unset=True).items():
        setattr(candidate, k, v)
        
    if profile_in.parsed_name is not None and candidate.user:
        candidate.user.full_name = profile_in.parsed_name
        
    candidate.status = "Profile Completed"
    candidate.current_step = "Resume"
    db.commit()
    
    from app.services.resume_cache import invalidate_resume_analysis, invalidate_dashboard_summary
    invalidate_resume_analysis(candidate.id)
    invalidate_dashboard_summary(candidate.id)
    try:
        from app.services.mentor_cache import invalidate_mentor_profile
        invalidate_mentor_profile(candidate.user_id)
    except Exception as cache_err:
        logger.warning(f"Failed to invalidate AI Mentor profile cache: {cache_err}")
    
    db.refresh(candidate)
    return get_candidate_profile(current_user=current_user, db=db)


# ─────────────────────────────────────────────────────────────────────────────
# CANDIDATE DASHBOARD AGGREGATED SUMMARY (Single-Roundtrip, Redis-Cached)
# ─────────────────────────────────────────────────────────────────────────────

def _safe_json_loads(val, default=None):
    if not val:
        return default if default is not None else {}
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str):
        try:
            res = json.loads(val)
            if isinstance(res, (list, dict)):
                return res
        except Exception:
            pass
    return default if default is not None else {}


@router.get("/candidates/dashboard-summary")
def get_candidate_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Unified, single-roundtrip endpoint providing complete dashboard data.
    Backed by candidate-scoped Redis caching for sub-10ms response times on warm navigation.
    """
    candidate = db.query(Candidate).filter(Candidate.user_id == current_user.id).first()
    if not candidate:
        candidate = Candidate(user_id=current_user.id, status="Registered", current_step="Profile")
        db.add(candidate)
        db.commit()
        db.refresh(candidate)

    from app.services.resume_cache import get_cached_dashboard_summary, set_cached_dashboard_summary
    cached = get_cached_dashboard_summary(candidate.id)
    if cached:
        return cached

    # 1. Profile Data
    profile_data = get_candidate_profile(current_user=current_user, db=db)

    # 2. Roles Data
    roles_data = {
        "core": [{"role": "Software Engineer", "confidence": 95}],
        "related": [],
        "adjacent": [],
        "transferable": [],
        "future": [],
        "leadership": []
    }
    cand_profile = db.query(CandidateProfile).filter(CandidateProfile.candidate_id == candidate.id).order_by(CandidateProfile.created_at.desc()).first()
    if cand_profile and cand_profile.generated_roles:
        r_data = _safe_json_loads(cand_profile.generated_roles)
        if isinstance(r_data, list):
            roles_data = {
                "core": [{"role": r, "confidence": 90 - idx * 2} for idx, r in enumerate(r_data[:3])],
                "related": [{"role": r, "confidence": 80 - idx * 2} for idx, r in enumerate(r_data[3:6])],
                "adjacent": [{"role": r, "confidence": 75} for r in r_data[6:10]],
                "transferable": [],
                "future": [],
                "leadership": []
            }
        elif isinstance(r_data, dict):
            roles_data = r_data

    # 3. Skill Gaps Data
    gaps_obj = db.query(SkillGapAnalysis).filter(SkillGapAnalysis.candidate_id == candidate.id).order_by(SkillGapAnalysis.created_at.desc()).first()
    if gaps_obj:
        curr_skills = gaps_obj.current_skills or (candidate.skills or "").split(", ")
        missing_skills = gaps_obj.missing_skills or ["AWS", "Docker", "Kubernetes"]
        skill_gaps_data = {
            "current_skills": curr_skills,
            "skills_present": curr_skills,
            "required_skills": gaps_obj.target_role_skills or ["AWS", "Docker", "Kubernetes"],
            "missing_skills": missing_skills,
            "skill_gaps": missing_skills,
            "overall_gap_score": gaps_obj.overall_gap_score or 45.0,
        }
    else:
        curr_skills = (candidate.skills or "").split(", ") if candidate.skills else []
        skill_gaps_data = {
            "current_skills": curr_skills,
            "skills_present": curr_skills,
            "required_skills": ["AWS", "Docker", "Kubernetes"],
            "missing_skills": ["AWS", "Docker", "Kubernetes"],
            "skill_gaps": ["AWS", "Docker", "Kubernetes"],
            "overall_gap_score": 45.0,
        }

    # 4. Career Readiness Metrics
    courses_completed = 0
    try:
        enrollments = db.execute(text("SELECT progress FROM enrollments WHERE user_id=:user_id"), {"user_id": current_user.id}).fetchall()
        courses_completed = sum(1 for e in enrollments if (e[0] or 0) >= 100.0)
    except Exception:
        pass

    completed_items = 0
    try:
        prog_res = db.execute(
            text('SELECT "videoCompleted", "pdfCompleted", "quizCompleted", "writtenCompleted", "interviewCompleted" FROM user_progress WHERE "userId"=:user_id'),
            {"user_id": current_user.id}
        ).fetchall()
        completed_items = sum(sum(1 for val in p if val) for p in prog_res)
    except Exception:
        pass

    readiness_data = {
        "learning_streak": getattr(current_user, "user_streaks", 3) or 3,
        "hours_learned": round(completed_items * 0.25, 1),
        "courses_completed": courses_completed,
        "career_readiness_score": min(99.0, 64.0 + completed_items * 1.5),
        "resume_score": 85 if candidate.active_resume_id else 0,
        "profile_completion": 90 if candidate.parsed_name else 40
    }

    # 5. Resumes List
    from app.models.resume_center_models import Resume
    db_resumes = db.query(Resume).filter(Resume.candidate_id == candidate.id, Resume.deleted_at == None).all()
    resumes_data = [
        {
            "id": r.id,
            "title": r.title,
            "file_name": r.file_name,
            "is_active": r.is_active,
            "status": r.status
        } for r in db_resumes
    ]

    result = {
        "profile": profile_data,
        "roles": roles_data,
        "skillGaps": skill_gaps_data,
        "readiness": readiness_data,
        "resumes": resumes_data
    }

    set_cached_dashboard_summary(candidate.id, result)
    return result


@router.post("/candidates/dashboard-summary/invalidate")
def invalidate_candidate_dashboard_summary_route(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Explicitly invalidates candidate's cached dashboard summary upon mutations."""
    candidate = db.query(Candidate).filter(Candidate.user_id == current_user.id).first()
    if candidate:
        from app.services.resume_cache import invalidate_dashboard_summary
        invalidate_dashboard_summary(candidate.id)
    return {"status": "invalidated", "candidate_id": candidate.id if candidate else None}

