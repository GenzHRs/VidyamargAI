import json
import logging
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger("app.resume_cache")

# Local in-memory fallback
_LOCAL_RESUME_CACHE = {}

import time

_redis = None
_redis_checked_at = 0.0
_redis_is_online = False
_REDIS_RETRY_INTERVAL = 30.0

def _get_redis():
    global _redis, _redis_checked_at, _redis_is_online
    now = time.time()
    if not settings.REDIS_URL:
        return None
    if _redis is not None and _redis_is_online:
        return _redis
    if not _redis_is_online and (now - _redis_checked_at) < _REDIS_RETRY_INTERVAL:
        return None

    _redis_checked_at = now
    try:
        import redis
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=0.2,
            socket_timeout=0.5,
            decode_responses=True
        )
        client.ping()
        _redis = client
        _redis_is_online = True
        return _redis
    except Exception as e:
        _redis = None
        _redis_is_online = False
        logger.debug(f"Redis not available for resume cache (using in-memory fallback): {e}")
        return None

def get_cached_resume_analysis(candidate_id: int):
    global _redis_is_online
    r = _get_redis()
    key = f"resume_analysis_cache:{candidate_id}"
    if r:
        try:
            val = r.get(key)
            if val:
                return json.loads(val)
        except Exception as e:
            _redis_is_online = False
            logger.debug(f"Redis cache error reading resume analysis for candidate {candidate_id}: {e}")
    return _LOCAL_RESUME_CACHE.get(candidate_id)

def set_cached_resume_analysis(candidate_id: int, data: dict):
    global _redis_is_online
    r = _get_redis()
    key = f"resume_analysis_cache:{candidate_id}"
    # TTL: 24 hours
    ttl = 60 * 60 * 24
    if r:
        try:
            r.setex(key, ttl, json.dumps(data))
            return
        except Exception as e:
            _redis_is_online = False
            logger.debug(f"Redis cache error writing resume analysis for candidate {candidate_id}: {e}")
    try:
        _LOCAL_RESUME_CACHE[candidate_id] = json.loads(json.dumps(data))
    except Exception:
        _LOCAL_RESUME_CACHE[candidate_id] = data

def invalidate_resume_analysis(candidate_id: int):
    global _redis_is_online
    r = _get_redis()
    key = f"resume_analysis_cache:{candidate_id}"
    if r:
        try:
            r.delete(key)
        except Exception as e:
            _redis_is_online = False
            logger.debug(f"Redis cache error deleting resume analysis for candidate {candidate_id}: {e}")
    if candidate_id in _LOCAL_RESUME_CACHE:
        try:
            del _LOCAL_RESUME_CACHE[candidate_id]
        except KeyError:
            pass

# ─────────────────────────────────────────────────────────────────────────────
# Candidate Context Revision & Active Resume Context Cache
# ─────────────────────────────────────────────────────────────────────────────

_LOCAL_CONTEXT_CACHE = {}
_LOCAL_REVISIONS = {}

def get_candidate_context_revision(candidate_id: int) -> int:
    """Returns the current monotonic context revision for a candidate (defaults to 1)."""
    global _redis_is_online
    r = _get_redis()
    key = f"candidate:{candidate_id}:context_revision"
    if r:
        try:
            val = r.get(key)
            if val is not None:
                return int(val)
        except Exception as e:
            _redis_is_online = False
            logger.debug(f"Error reading context revision for candidate {candidate_id}: {e}")
    return _LOCAL_REVISIONS.get(candidate_id, 1)

def increment_candidate_context_revision(candidate_id: int) -> int:
    """Increments and returns the context revision, immediately invalidating stale cache."""
    global _redis_is_online
    r = _get_redis()
    key = f"candidate:{candidate_id}:context_revision"
    new_rev = 1
    if r:
        try:
            new_rev = int(r.incr(key))
            # Also clear the old cached context
            r.delete(f"candidate:{candidate_id}:active_resume_context")
            r.delete(f"candidate:{candidate_id}:active_resume_id")
        except Exception as e:
            _redis_is_online = False
            logger.debug(f"Error incrementing context revision for candidate {candidate_id}: {e}")
            new_rev = _LOCAL_REVISIONS.get(candidate_id, 1) + 1
    else:
        new_rev = _LOCAL_REVISIONS.get(candidate_id, 1) + 1

    _LOCAL_REVISIONS[candidate_id] = new_rev
    _LOCAL_CONTEXT_CACHE.pop(candidate_id, None)
    logger.info(f"Incremented context revision for candidate {candidate_id} -> {new_rev}")
    return new_rev

def get_cached_active_resume_context(candidate_id: int) -> Optional[dict]:
    """
    Returns cached active resume context ONLY if its revision matches the current revision.
    Guarantees stale cache is NEVER returned.
    """
    global _redis_is_online
    current_rev = get_candidate_context_revision(candidate_id)
    r = _get_redis()
    key = f"candidate:{candidate_id}:active_resume_context"
    cached_obj = None

    if r:
        try:
            val = r.get(key)
            if val:
                cached_obj = json.loads(val)
        except Exception as e:
            _redis_is_online = False
            logger.debug(f"Error reading cached active resume context for candidate {candidate_id}: {e}")

    if not cached_obj:
        cached_obj = _LOCAL_CONTEXT_CACHE.get(candidate_id)

    if cached_obj and isinstance(cached_obj, dict):
        if cached_obj.get("revision") == current_rev:
            return cached_obj.get("data")
        else:
            logger.info(f"Discarding stale cached context for candidate {candidate_id} (cache rev {cached_obj.get('revision')} != current rev {current_rev})")

    return None

def set_cached_active_resume_context(candidate_id: int, revision: int, data: dict):
    """Caches candidate active resume context stamped with its revision."""
    global _redis_is_online
    r = _get_redis()
    key = f"candidate:{candidate_id}:active_resume_context"
    payload = {"revision": revision, "data": data}
    ttl = 60 * 60 * 2  # 2 hours
    if r:
        try:
            r.setex(key, ttl, json.dumps(payload))
            r.set(f"candidate:{candidate_id}:active_resume_id", str(data.get("active_resume_id", "")))
            return
        except Exception as e:
            _redis_is_online = False
            logger.debug(f"Error writing active resume context cache for candidate {candidate_id}: {e}")

    _LOCAL_CONTEXT_CACHE[candidate_id] = payload


def invalidate_candidate_context(candidate_id: int):
    """Invalidates all cached candidate context across Redis and local memory."""
    increment_candidate_context_revision(candidate_id)
    invalidate_resume_analysis(candidate_id)
    invalidate_dashboard_summary(candidate_id)
    _LOCAL_CONTEXT_CACHE.pop(candidate_id, None)


_LOCAL_DASHBOARD_CACHE = {}

def get_cached_dashboard_summary(candidate_id: int) -> Optional[dict]:
    global _redis_is_online
    r = _get_redis()
    key = f"candidate:{candidate_id}:dashboard_summary"
    if r:
        try:
            val = r.get(key)
            if val:
                return json.loads(val)
        except Exception as e:
            _redis_is_online = False
            logger.debug(f"Redis cache error reading dashboard summary for candidate {candidate_id}: {e}")
    return _LOCAL_DASHBOARD_CACHE.get(candidate_id)

def set_cached_dashboard_summary(candidate_id: int, data: dict):
    global _redis_is_online
    r = _get_redis()
    key = f"candidate:{candidate_id}:dashboard_summary"
    ttl = 300  # 5 minutes
    if r:
        try:
            r.setex(key, ttl, json.dumps(data))
            return
        except Exception as e:
            _redis_is_online = False
            logger.debug(f"Redis cache error writing dashboard summary for candidate {candidate_id}: {e}")
    try:
        _LOCAL_DASHBOARD_CACHE[candidate_id] = json.loads(json.dumps(data))
    except Exception:
        _LOCAL_DASHBOARD_CACHE[candidate_id] = data

def invalidate_dashboard_summary(candidate_id: int):
    global _redis_is_online
    r = _get_redis()
    key = f"candidate:{candidate_id}:dashboard_summary"
    if r:
        try:
            r.delete(key)
        except Exception as e:
            _redis_is_online = False
            logger.debug(f"Redis cache error deleting dashboard summary for candidate {candidate_id}: {e}")
    _LOCAL_DASHBOARD_CACHE.pop(candidate_id, None)


def clear_all_local_caches():
    """Testing helper to clear all in-memory caches across test boundaries."""
    _LOCAL_RESUME_CACHE.clear()
    _LOCAL_CONTEXT_CACHE.clear()
    _LOCAL_REVISIONS.clear()
    _LOCAL_DASHBOARD_CACHE.clear()



