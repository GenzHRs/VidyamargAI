"""Validated configuration. Environment takes precedence over the project .env."""
import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Explicit locations, never search arbitrary ancestor directories.
load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

class Settings(BaseSettings):
    PROJECT_NAME: str = "HireAI API"
    API_V1_STR: str = "/api/v1"
    
    # Security
    SECRET_KEY: str = Field(
        default="vidyamarg_ai_default_secret_key_production_fallback_32bytes_min",
        min_length=32
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # 15 minutes
    
    # Database (Fallback to local SQLite if not provided in environment)
    DATABASE_URL: str = "sqlite:///./vidyamarg.db"
    
    # Storage (MinIO / S3)
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = ""
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "False").lower() == "true"
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "hireai")
    MINIO_REGION: str = os.getenv("MINIO_REGION", "us-east-1")
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # AI Keys
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
    NVIDIA_API_KEY_FALLBACK: str = os.getenv("NVIDIA_API_KEY_FALLBACK", "")
    SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")
    QDRANT_URL: str = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    APIFY_API_TOKEN: str = os.getenv("APIFY_API_TOKEN", "")
    
    # Telegram API
    TG_API_ID: str = os.getenv("TG_API_ID", os.getenv("api_id", ""))
    TG_API_HASH: str = os.getenv("TG_API_HASH", os.getenv("api_hash", ""))
    # Path to the channels list .txt file (overridable for Docker volume mounts)
    TG_CHANNELS_FILE: str = os.getenv(
        "TG_CHANNELS_FILE",
        os.path.join(os.path.dirname(__file__), "../job_agent/channel.txt")
    )
    
    # Feature Flags
    AI_MENTOR_ENABLED: bool = os.getenv("AI_MENTOR_ENABLED", "True").lower() == "true"
    VOICE_MENTOR_ENABLED: bool = os.getenv("VOICE_MENTOR_ENABLED", "False").lower() == "true"
    STUDY_PLAN_ENABLED: bool = os.getenv("STUDY_PLAN_ENABLED", "True").lower() == "true"
    ARTIFACTS_ENABLED: bool = os.getenv("ARTIFACTS_ENABLED", "True").lower() == "true"
    SEARCH_ENABLED: bool = os.getenv("SEARCH_ENABLED", "True").lower() == "true"
    ANALYTICS_ENABLED: bool = os.getenv("ANALYTICS_ENABLED", "False").lower() == "true"
    
    # Auto Apply Agent
    CREDENTIAL_ENCRYPTION_KEY: str = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")
    AUTO_APPLY_MAX_CONCURRENT: int = int(os.getenv("AUTO_APPLY_MAX_CONCURRENT", "5"))
    AUTO_APPLY_DAILY_CAP: int = int(os.getenv("AUTO_APPLY_DAILY_CAP", "50"))
    AUTO_APPLY_MIN_MATCH_SCORE: float = float(os.getenv("AUTO_APPLY_MIN_MATCH_SCORE", "80.0"))
    AUTO_APPLY_MIN_SKILL_MATCH: float = float(os.getenv("AUTO_APPLY_MIN_SKILL_MATCH", "70.0"))
    AUTO_APPLY_MAX_JOB_AGE_DAYS: int = int(os.getenv("AUTO_APPLY_MAX_JOB_AGE_DAYS", "2"))
    AUTO_APPLY_CHECKPOINT_DB: str = os.getenv("AUTO_APPLY_CHECKPOINT_DB", "storage/langgraph_checkpoints/auto_apply.db")
    PLATFORM_DISABLE_THRESHOLD: float = float(os.getenv("PLATFORM_DISABLE_THRESHOLD", "0.20"))
    PLATFORM_MIN_ATTEMPTS_BEFORE_CHECK: int = int(os.getenv("PLATFORM_MIN_ATTEMPTS_BEFORE_CHECK", "10"))
    
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_FALLBACK_MODEL: str = "openai/gpt-oss-20b"
    ADMIN_REGISTRATION_KEY: str = ""
    HR_SYNC_SECRET: str = ""
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://vidyamarg-ai-nzud.vercel.app",
        "https://vidyamargai-production-2c1f.up.railway.app",
    ]
    SCHEDULER_ENABLED: bool = False
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    STORAGE_DIR: str = "storage"

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value):
        if not value.startswith(("postgresql://", "postgresql+psycopg2://", "postgresql+asyncpg://", "postgres://", "sqlite://", "sqlite+aiosqlite://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL or SQLite URL")
        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def validate_cors_origins(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                import json
                try:
                    return json.loads(value)
                except Exception:
                    pass
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("ADMIN_REGISTRATION_KEY", "HR_SYNC_SECRET")
    @classmethod
    def validate_optional_secrets(cls, value):
        if value and len(value) < 32:
            raise ValueError("Configured shared secrets must contain at least 32 characters")
        return value


settings = Settings()
