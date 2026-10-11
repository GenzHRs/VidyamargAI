"""
dev_mode_service.py — Dedicated Testing Mode & Development Authentication Service.

Provides idempotent seeding and authentic session generation for the isolated test candidate.
Enforces strict fail-closed security: rejected in unverified production environments.
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, generate_refresh_token, hash_token
from app.models.models import User, Candidate, UserRefreshToken
from app.models.resume_center_models import Resume, ResumeVersion

logger = logging.getLogger("app.dev_mode")

DEV_USER_EMAIL = "dev.candidate@vidyamarg.local"
DEV_USER_NAME = "Test Candidate (Testing Mode)"
DEV_USER_ROLE = "candidate"

TEST_STRUCTURED_DATA = {
    "personal_info": {
        "full_name": "Test Candidate (Testing Mode)",
        "email": "dev.candidate@vidyamarg.local",
        "phone": "+1 (555) 019-2834",
        "location": "San Francisco, CA",
        "address": "San Francisco, CA",
        "summary": "Full Stack AI Engineer with 4+ years experience building production LLM architectures, FastAPI microservices, and React/Next.js client applications.",
        "linkedin": "https://linkedin.com/in/vidyamarg-test",
        "github": "https://github.com/vidyamarg-test",
        "portfolio": "https://vidyamarg.local"
    },
    "work_experience": [
        {
            "employer": "Vidyamarg AI Labs",
            "company": "Vidyamarg AI Labs",
            "designation": "Senior Full Stack AI Engineer",
            "role": "Senior Full Stack AI Engineer",
            "employment_type": "Full-time",
            "location": "San Francisco, CA",
            "start_date": "2023-01",
            "end_date": "Present",
            "responsibilities": [
                "Architected high-throughput FastAPI microservices handling 50k+ daily career agent recommendations.",
                "Engineered Next.js 16 frontend interfaces with sub-second response times and optimistic caching."
            ],
            "technologies": ["Python", "FastAPI", "TypeScript", "Next.js", "PostgreSQL", "Redis"]
        }
    ],
    "education": [
        {
            "institution": "Stanford University",
            "degree": "B.S. in Computer Science (Artificial Intelligence)",
            "start_date": "2018-09",
            "end_date": "2022-06",
            "grade": "3.92 GPA"
        }
    ],
    "skills": [
        {"name": "Python", "category": "Programming Languages"},
        {"name": "TypeScript", "category": "Programming Languages"},
        {"name": "FastAPI", "category": "Backend & Cloud"},
        {"name": "Next.js", "category": "Frontend Frameworks"},
        {"name": "PostgreSQL", "category": "Databases & Storage"},
        {"name": "Redis", "category": "Databases & Storage"},
        {"name": "TailwindCSS", "category": "Frontend Frameworks"},
        {"name": "PyTorch", "category": "AI & Machine Learning"}
    ],
    "projects": [
        {
            "name": "Vidyamarg Career Operating System",
            "title": "Vidyamarg Career Operating System",
            "description": "Autonomous AI career mentor matching talent to global tech opportunities.",
            "technologies": ["FastAPI", "React", "Qdrant", "PostgreSQL"],
            "responsibilities": [
                "Developed vector retrieval engine across 100k+ real job descriptions."
            ]
        }
    ]
}


class DevModeService:
    @staticmethod
    def is_allowed() -> bool:
        """Independent backend check whether Testing Mode / Dev Auth Bypass is permitted."""
        return settings.is_dev_mode_allowed

    @classmethod
    def get_or_create_dev_user(cls, db: Session) -> Tuple[User, Candidate]:
        """
        Idempotently resolves or creates the isolated test candidate with full persisted relationships.
        Strictly enforces role='candidate' (never administrator).
        """
        if not cls.is_allowed():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Testing Mode / DEV_AUTH_BYPASS is disabled or rejected by environment policy."
            )

        user = db.query(User).filter(User.email == DEV_USER_EMAIL).first()
        if not user:
            logger.info(f"Seeding isolated development test user: {DEV_USER_EMAIL}")
            user = User(
                email=DEV_USER_EMAIL,
                full_name=DEV_USER_NAME,
                role=DEV_USER_ROLE,
                password_hash=get_password_hash("DevModeTestPass_2026_LocalOnly!")
            )
            db.add(user)
            db.flush()

        candidate = db.query(Candidate).filter(Candidate.user_id == user.id).first()
        if not candidate:
            candidate = Candidate(
                user_id=user.id,
                status="Active",
                current_step="Dashboard",
                parsed_name=DEV_USER_NAME,
                parsed_email=DEV_USER_EMAIL,
                phone="+1 (555) 019-2834",
                address="San Francisco, CA",
                primary_designation="Senior Full Stack AI Engineer",
                summary=TEST_STRUCTURED_DATA["personal_info"]["summary"],
                skills="Python, TypeScript, FastAPI, Next.js, PostgreSQL, Redis, TailwindCSS, PyTorch",
                experience=json.dumps(TEST_STRUCTURED_DATA["work_experience"]),
                education=json.dumps(TEST_STRUCTURED_DATA["education"]),
                projects=json.dumps(TEST_STRUCTURED_DATA["projects"]),
                linkedin="https://linkedin.com/in/vidyamarg-test",
                github="https://github.com/vidyamarg-test",
                portfolio="https://vidyamarg.local"
            )
            db.add(candidate)
            db.flush()
        else:
            # Ensure key fields exist
            if not candidate.primary_designation:
                candidate.primary_designation = "Senior Full Stack AI Engineer"
                candidate.summary = TEST_STRUCTURED_DATA["personal_info"]["summary"]
                candidate.skills = "Python, TypeScript, FastAPI, Next.js, PostgreSQL, Redis, TailwindCSS, PyTorch"
                candidate.experience = json.dumps(TEST_STRUCTURED_DATA["work_experience"])
                candidate.education = json.dumps(TEST_STRUCTURED_DATA["education"])
                candidate.projects = json.dumps(TEST_STRUCTURED_DATA["projects"])
                db.flush()

        # Seed test resume if none exists for this test candidate
        existing_resume = db.query(Resume).filter(
            Resume.candidate_id == candidate.id,
            Resume.deleted_at == None
        ).first()

        if not existing_resume:
            logger.info("Seeding persisted test resume for test candidate.")
            test_resume = Resume(
                candidate_id=candidate.id,
                title="Test Candidate Master Resume",
                source_type="builder",
                status="active",
                is_active=True,
                extraction_status="extracted",
                is_verified=True
            )
            db.add(test_resume)
            db.flush()

            test_version = ResumeVersion(
                resume_id=test_resume.id,
                version_number=1,
                structured_data=TEST_STRUCTURED_DATA,
                change_summary="Initial seeded test version"
            )
            db.add(test_version)
            db.flush()

            test_resume.current_version_id = test_version.id
            candidate.active_resume_id = test_resume.id
            db.flush()

        db.commit()
        db.refresh(user)
        db.refresh(candidate)

        return user, candidate

    @classmethod
    def create_dev_session(cls, db: Session) -> Dict[str, Any]:
        """
        Issues an authentic JWT access token and refresh token for the test candidate.
        """
        user, candidate = cls.get_or_create_dev_user(db)

        # Issue access token valid for 7 days in dev/testing mode
        access_token = create_access_token(
            subject=user.email,
            role=user.role,
            expires_delta=timedelta(days=7)
        )

        # Issue refresh token
        refresh_token = generate_refresh_token()
        token_hash = hash_token(refresh_token)
        db_refresh = UserRefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
        db.add(db_refresh)
        db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "candidate_id": candidate.id,
                "is_dev_user": True
            },
            "dev_mode": True,
            "bypass_enabled": True,
            "banner_text": "TESTING MODE — TEST CANDIDATE"
        }
