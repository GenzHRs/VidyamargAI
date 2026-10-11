"""VidyaMarg API. Schema changes are explicit operator actions, never startup work."""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.core.config import settings
from app.core.database import engine, SessionLocal, Base
from app.core.security import get_current_user
from app.core.limiter import limiter
from app.api.endpoints import router as legacy_api_router
from app.api.v1.sync import router as sync_router
from services.candidate_service.app.router import router as candidate_router

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app):
    # Production Startup Guard: Refuse to boot if DEV_AUTH_BYPASS is rejected by environment security policy
    if settings.DEV_AUTH_BYPASS:
        if not settings.is_dev_mode_allowed:
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: DEV_AUTH_BYPASS is enabled but rejected by environment security policy! "
                "In production/staging environments, DEV_AUTH_BYPASS_DEPLOYMENT='authorized_testing' is strictly required. "
                "Server refuses to boot. Disable DEV_AUTH_BYPASS=false."
            )
        logger.warning("⚠️  TESTING AUTH BYPASS ACTIVE: Testing enabled with seeded test candidate.")

    # Ensure database schema is initialized on PostgreSQL startup
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        logger.warning(f"Database table initialization warning: {e}")

    task = None
    if settings.SCHEDULER_ENABLED:
        from app.core.scheduler import start_scheduler, run_periodic_job_sync
        start_scheduler()
        task = asyncio.create_task(run_periodic_job_sync())
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        from app.core.scheduler import shutdown_scheduler
        shutdown_scheduler()
    from app.core.redis_client import close_redis
    await close_redis()
    engine.dispose()

app = FastAPI(title="VidyaMarg AI Career OS API", version="2.0.1", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(legacy_api_router, prefix="/api/v1")
app.include_router(candidate_router)
app.include_router(sync_router, prefix="/api/v1")

@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    if request.headers.get("authorization") or request.url.path.startswith("/api/v1/auth"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/db-check")
def check_db_connection():
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            if engine.dialect.name == "sqlite":
                tables = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
            else:
                tables = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")).fetchall()
            table_names = [t[0] for t in tables]
            
            user_count = conn.execute(text("SELECT count(*) FROM users")).scalar() if "users" in table_names else 0
            candidate_count = conn.execute(text("SELECT count(*) FROM candidates")).scalar() if "candidates" in table_names else 0
            job_count = conn.execute(text("SELECT count(*) FROM jobs")).scalar() if "jobs" in table_names else 0

            return {
                "connected": True,
                "ping": result == 1,
                "engine": engine.dialect.name,
                "tables_count": len(table_names),
                "counts": {
                    "users": user_count,
                    "candidates": candidate_count,
                    "jobs": job_count
                },
                "tables": table_names
            }
    except Exception as e:
        return JSONResponse({"connected": False, "error": str(e)}, status_code=500)

@app.get("/ready")
def readiness():
    try:
        with engine.connect() as conn:
            if engine.dialect.name == "sqlite":
                ready = conn.execute(text("SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN ('users', 'candidates')")).scalar() == 2
            else:
                ready = conn.execute(text("SELECT to_regclass('users') IS NOT NULL AND to_regclass('candidates') IS NOT NULL")).scalar()
        if not ready:
            return JSONResponse({"status": "not_ready"}, status_code=503)
    except Exception:
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return {"status": "ready"}

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    # Token is sent in the first frame, not a logged URL query parameter.
    from app.core.ws import manager
    origin = websocket.headers.get("origin")
    is_valid_origin = (
        not origin 
        or origin in settings.CORS_ORIGINS 
        or (origin.startswith("https://") and origin.endswith(".vercel.app"))
    )
    if not is_valid_origin:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    def authorize(token):
        with SessionLocal() as db:
            user = get_current_user(db=db, token=token)
            rooms = {user.email, f"user_{user.id}"}
            if user.candidate:
                rooms.add(f"candidate_{user.candidate.id}")
            if user.role in {"admin", "super_admin"}:
                rooms.update({"admin", "admin_portal", f"admin_{user.id}"})
            return client_id in rooms
    try:
        frame = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        token = frame.get("token") if isinstance(frame, dict) else None
        if not isinstance(token, str) or not await run_in_threadpool(authorize, token):
            await websocket.close(code=1008)
            return
        await manager.connect(websocket, client_id)
        # Require reauthentication on reconnect no later than token expiry.
        import jwt
        import time
        claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        expires = float(claims["exp"])
        while True:
            await asyncio.wait_for(websocket.receive_text(), timeout=max(0.01, expires-time.time()))
    except (WebSocketDisconnect, asyncio.TimeoutError, HTTPException, ValueError, KeyError):
        with suppress(RuntimeError):
            await websocket.close(code=1008)
    finally:
        manager.disconnect(websocket, client_id)

class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    candidate_id: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=12000)

@app.post("/tush-ai/chat")
async def chat_tush_ai(payload: ChatRequest, current_user=Depends(get_current_user)):
    raise HTTPException(status_code=501, detail="Experimental AI OS execution is not implemented. Use /api/v1/mcp/chat.")
