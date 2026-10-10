# VidyaMarg AI — Redis & Application Caching Strategy

**Date:** 2026-10-10  
**Target:** Define strict caching policies, tenant isolation, and write invalidation.

---

## 1. Candidate Isolation & Security Principles

1. **No Shared Private Caches:** Every candidate cache key is prefixed with the candidate's authenticated user ID (e.g. `candidate:profile:{candidate_id}`, `candidate:readiness:{candidate_id}`).
2. **Instant Write Invalidation:** When a candidate edits their profile, uploads a new resume, or updates an application status, the corresponding cache key is immediately invalidated via `redis_client.delete(cache_key)`.
3. **Short TTL Default:** Read-heavy aggregates use short Time-To-Live values (TTL = 300s) to guarantee data freshness even if an invalidation event is delayed.

---

## 2. Caching Architecture Matrix

| Data Type | Cache Key Structure | TTL | Invalidation Trigger | Fallback Strategy |
|---|---|:---:|---|---|
| **Candidate Profile** | `candidate:profile:{candidate_id}` | 300s | Profile edit, resume upload, skills update | Direct DB read |
| **Active Resume Snapshot** | `resume:active:{candidate_id}` | 600s | Resume upload, template selection, section update | `ResumeContextService` DB query |
| **Job Market Reference Data** | `jobs:metadata:categories` | 3,600s | Daily scheduled crawler update | Database query |
| **AI Mentor Session Summary** | `mentor:sessions:{user_id}` | 180s | New session creation, session deletion | PostgreSQL query |

---

## 3. Cache Failure Resilience

If Redis is unreachable or returns a connection timeout, the application automatically catches the exception, logs a warning, and falls back seamlessly to authoritative PostgreSQL database queries.
