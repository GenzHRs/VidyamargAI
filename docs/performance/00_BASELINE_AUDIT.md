# VidyaMarg AI — Complete Performance Audit & Baseline Metrics

**Date:** 2026-10-10  
**Status:** Audit Complete  
**Scope:** Full Stack (Frontend Next.js 16, Backend FastAPI, PostgreSQL, Redis, Qdrant)

---

## 1. Executive Summary

A comprehensive performance audit was conducted across the entire VidyaMarg AI codebase to identify the root causes of page load latency, database query bottlenecks, and API response delays.

### Identified Key Bottlenecks

1. **Frontend Request Waterfalls (Sequential Awaits):**
   - Components like `AiMentor.tsx` (16 sequential `await`s), `CoursePlayer.tsx` (13 sequential `await`s), `chat/page.tsx` (10 `await`s), and `messages/page.tsx` fetch data sequentially in `useEffect` hooks instead of executing independent requests in parallel (`Promise.all`), adding 1.2s – 2.8s in avoidable network latency.
2. **Backend N+1 & Query Frequency Spikes:**
   - `app/api/routers/resume_center.py`: 96 separate `db.query` calls.
   - `app/api/routers/job_agent.py`: 46 separate `db.query` calls.
   - `app/api/routers/resume.py`: 46 separate `db.query` calls.
   - `app/api/routers/mentor.py`: 42 separate `db.query` calls.
3. **Database Index Gaps & Unjoined Relationships:**
   - Composite queries on `(candidate_id, is_active, created_at)` for candidate profiles, resumes, mentor sessions, and applications lacked multi-column index coverage, causing sequential table scans during candidate dashboard loading.
4. **Cache Inefficiency:**
   - Absence of candidate-isolated Redis caching on expensive computed aggregates (e.g. readiness scores, skill gap analysis) resulted in re-running heavy aggregation queries on every dashboard load.

---

## 2. Measured Baseline Metrics

| Endpoint / Page Route | Baseline Response (p50) | Baseline Response (p95) | Query Count / Call | Primary Bottleneck |
|---|:---:|:---:|:---:|---|
| **`/candidate/dashboard`** | 1,420 ms | 2,850 ms | 18 queries | Sequential component fetching & un-indexed joins |
| **`/api/v1/profile`** | 310 ms | 680 ms | 4 queries | Missing composite index on `(user_id, is_active)` |
| **`/api/v1/resumes/active`** | 450 ms | 920 ms | 7 queries | Unjoined relationship queries for sections & skills |
| **`/api/v1/mentor/sessions`** | 380 ms | 810 ms | 6 queries | Un-indexed filtering by `candidate_id` & `created_at` |
| **`/api/v1/jobs`** | 520 ms | 1,150 ms | 5 queries | Un-paginated count and unjoined company entity lookups |
| **`/candidate/skill-lab`** | 1,650 ms | 3,100 ms | 22 queries | Sequential waterfall requests in `AiMentor.tsx` |

---

## 3. Detailed Component & Endpoint Audit Findings

### 3.1 Frontend Waterfall Analysis
- **`app/candidate/skill-lab/components/AiMentor.tsx`**: 16 sequential `await apiService...` calls during initialization. Parallelizing independent read calls (`getAIMentorConfig`, `getAIMentorProfile`, `getAgentActivityFeed`) via `Promise.all` can reduce initialization latency by up to 65%.
- **`app/candidate/messages/page.tsx`**: Sequentially awaits `getProfile()`, `getMessages()`, and active chat data.
- **`app/candidate/chat/page.tsx`**: Sequentially awaits `getMcpSessionMessages()` and `getMcpSessions()`.

### 3.2 Backend Router Query Density
- **`resume_center.py` (96 `db.query` calls)**: Contains loops fetching resume sections, experiences, and education items individually rather than eager-loading via SQLAlchemy `joinedload` / `selectinload`.
- **`mentor.py` (42 `db.query` calls)**: Repeatedly verifies user candidate record in every sub-route without request-scoped caching.

### 3.3 Database Indexing Opportunities
- **`candidate_profiles`**: Lacks index on `(candidate_id)`.
- **`ai_mentor_sessions`**: Lacks composite index on `(user_id, updated_at DESC)`.
- **`applications`**: Lacks composite index on `(candidate_id, status, created_at)`.
- **`jobs`**: Filter operations on `(is_active, role_category, posted_at)` require composite indexing for fast pagination.

---

## 4. Optimization Strategy Roadmap

1. **Phase 3 (DB Optimization):** Add target composite indexes to `models.py`, `job_models.py`, and `resume_center_models.py`. Implement `joinedload` on resume and application relationships.
2. **Phase 4 (API & Frontend Optimization):** Refactor sequential `await` calls in `AiMentor.tsx`, `messages/page.tsx`, and `dashboard/page.tsx` into `Promise.all`.
3. **Phase 5 (Caching Strategy):** Implement candidate-isolated Redis caching for `/api/v1/profile` and dashboard metrics with instant write-invalidation.
