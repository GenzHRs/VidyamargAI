from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from urllib.parse import unquote, quote, urlparse
import logging

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import User, Candidate, CandidateResume
from app.services.storage import storage_service, safe_object_path, get_user_folder_name

logger = logging.getLogger(__name__)

router = APIRouter(tags=["storage"])


@router.get("/storage/{path:path}")
def serve_storage_file(
    path: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Candidate-authenticated file streaming and download endpoint for uploaded resumes,
    compiled PDFs, and related candidate artifacts.
    """
    folder, _, filename = path.rpartition("/")
    try:
        safe_object_path(folder, filename)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")

    # Candidate ownership verification
    if current_user.role not in {"admin", "super_admin"}:
        candidate = db.query(Candidate).filter(Candidate.user_id == current_user.id).first()
        owns_folder = path.startswith(f"users/{get_user_folder_name(current_user)}/")
        owns_resume = False

        if candidate:
            resumes = db.query(CandidateResume).filter(CandidateResume.candidate_id == candidate.id).all()
            owns_resume = any(
                unquote(urlparse(resume.resume_url).path) == f"/api/v1/storage/{path}"
                for resume in resumes
                if resume.resume_url
            )

        if not (owns_folder or owns_resume):
            raise HTTPException(status_code=404, detail="File not found")

    parts = path.split("/")
    if len(parts) > 1:
        folder_path = "/".join(parts[:-1])
        file_name = parts[-1]
    else:
        folder_path = ""
        file_name = path

    content = storage_service.get_file_content(folder_path, file_name)
    if not content:
        raise HTTPException(status_code=404, detail="File not found")

    if file_name.endswith(".pdf"):
        media_type = "application/pdf"
    elif file_name.endswith(".md") or file_name.endswith(".txt"):
        media_type = "text/markdown"
    elif file_name.endswith(".mp4"):
        media_type = "video/mp4"
    elif file_name.endswith(".webm"):
        media_type = "video/webm"
    elif file_name.endswith(".wav"):
        media_type = "audio/wav"
    elif file_name.endswith(".png"):
        media_type = "image/png"
    elif file_name.endswith(".jpg") or file_name.endswith(".jpeg"):
        media_type = "image/jpeg"
    else:
        media_type = "application/octet-stream"

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": "inline; filename*=UTF-8''" + quote(file_name),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
        },
    )
