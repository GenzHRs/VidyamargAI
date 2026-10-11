from fastapi import APIRouter
from app.api.routers import (
    auth, profile, resume, learning, mentor,
    chat, notifications, storage, job_agent, resume_center,
    career_agent, autofill, jobs
)


# Backward compatibility exports
from app.api.routers.learning import _build_curriculum_payload
from app.api.routers.mentor import call_llm_with_fallback
from app.api.routers.resume import delete_candidate_resume

router = APIRouter()

router.include_router(auth.router)
router.include_router(profile.router)
router.include_router(resume.router)
router.include_router(resume_center.router)
router.include_router(learning.router)
router.include_router(mentor.router)
router.include_router(chat.router)
router.include_router(notifications.router)
router.include_router(storage.router)
router.include_router(job_agent.router)
router.include_router(jobs.router, prefix="/jobs")
router.include_router(career_agent.router)
router.include_router(autofill.router, prefix="/applications/autofill")

