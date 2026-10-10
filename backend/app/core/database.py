import time
import logging
import os
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core.config import settings
from app.core.monitoring import db_queries_var, db_query_time_var, cache_status_var

logger = logging.getLogger("app.db")

from sqlalchemy.pool import NullPool

# WELL-DOCUMENTED EXCEPTION: Sync engine is ONLY for legacy sync scripts and workers.
# To prevent PostgreSQL connection pool exhaustion (with asyncpg being the standard async path),
# the sync engine uses NullPool to avoid maintaining an always-on parallel pool of idle connections.
# PostgreSQL connection engine with NullPool for serverless/containerized stability
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=NullPool
    )
else:
    pg_url = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1).replace("postgresql+asyncpg://", "postgresql://", 1)
    if pg_url.startswith("postgresql://"):
        pg_url = pg_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    engine = create_engine(
        pg_url,
        poolclass=NullPool,
        connect_args={
            "options": "-c idle_in_transaction_session_timeout=120000 -c lock_timeout=5000"
        }
    )

# Slow Query Monitoring Listeners
@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_start_time = time.perf_counter()
    try:
        # Increment request database query counter
        current_count = db_queries_var.get()
        db_queries_var.set(current_count + 1)
    except Exception:
        pass

@event.listens_for(engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    duration = time.perf_counter() - context._query_start_time
    try:
        # Accumulate DB query execution time
        current_time = db_query_time_var.get()
        db_query_time_var.set(current_time + duration)
    except Exception:
        pass

    if duration > 0.2:
        logger.warning(f"Slow Query ({duration:.2f}s): {statement[:200]}")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

