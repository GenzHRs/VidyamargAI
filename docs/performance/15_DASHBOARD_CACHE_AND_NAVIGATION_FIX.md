# 15. DASHBOARD CACHE AND NAVIGATION FIX ARCHITECTURE

## Overview
To provide instant navigation (<100ms) when candidates return to `/candidate/dashboard`, VidyamargAI implemented a multi-layered Stale-While-Revalidate caching architecture across the frontend Zustand state layer and the backend FastAPI Redis layer.

---

## 1. Architectural Components

### A. Shared Client-Side Zustand Cache (`useDashboardStore`)
File: `frontend/store/dashboardStore.ts`
- **Persistent Client Memory**: State persists across candidate route changes while the Next.js candidate layout remains mounted.
- **Stale-While-Revalidate Lifecycle**:
  - `CACHE_STALE_TIME_MS = 60000` (60-second fresh window).
  - When returning to the dashboard with existing `data`:
    - If within 60 seconds: **Instant display (0–5ms)**, 0 network requests triggered.
    - If older than 60 seconds: **Instant display of previous data**, silent background revalidation initiated (`isBackgroundRefreshing: true`).
  - No full-screen spinner is ever shown once data has been fetched.
- **Graceful Skeleton Placeholder**:
  - On the cold first visit (`!data && isInitialLoading`), a layout-matching skeleton (`DashboardSkeleton`) is rendered rather than a generic spinner.
- **Error Isolation**:
  - If background refresh fails, existing data remains visible.
  - If initial cold load fails, a retry banner is rendered without leaving an infinite spinner.

### B. Single-Roundtrip Backend Summary Endpoint
Files: `backend/app/api/routers/profile.py`, `backend/app/services/resume_cache.py`
- **Endpoint**: `GET /api/v1/candidates/dashboard-summary`
- Aggregates:
  1. Candidate profile & personal info
  2. Generated target roles & recommendation confidence
  3. Skill gaps analysis & present skills
  4. LMS learning streak, completed hours, & career readiness score
  5. Active resume records
- **Redis Cache Layer**:
  - Cache key: `candidate:{candidate_id}:dashboard_summary` (TTL: 300s).
  - Delivers sub-10ms response times on cache hits.
  - Falls back seamlessly to database computation if Redis is unreachable.

### C. Coordinated Cache Invalidation upon Mutations
- When a candidate updates their profile:
  - Backend executes `invalidate_dashboard_summary(candidate.id)`.
  - Frontend triggers `apiService.invalidateDashboardSummary()`.
- When a candidate updates, replaces, or activates a resume:
  - Backend `invalidate_candidate_context()` automatically purges `dashboard_summary`.
  - Frontend `resumeStore` calls `useDashboardStore.getState().invalidateDashboard()`.
- On Logout:
  - `authStore` executes `useDashboardStore.getState().reset()`, preventing cross-account data leakage.

---

## 2. Source Code Changes

1. **`frontend/store/dashboardStore.ts`** [NEW]:
   - Created `useDashboardStore` with `data`, `isInitialLoading`, `isBackgroundRefreshing`, `fetchDashboard`, `invalidateDashboard`, and `reset`.
2. **`frontend/app/candidate/dashboard/page.tsx`** [MODIFIED]:
   - Removed unpersisted local `useState` fetching.
   - Integrated `useDashboardStore`.
   - Added responsive `DashboardSkeleton` for cold initial visits.
   - Added top background revalidation status badge (`Syncing latest data…`).
3. **`frontend/services/api.ts`** [MODIFIED]:
   - Added `getDashboardSummary()` and `invalidateDashboardSummary()` methods.
4. **`frontend/store/resumeStore.ts` & `authStore.ts`** [MODIFIED]:
   - Connected cache invalidation and reset triggers upon resume mutations and logout.
5. **`backend/app/services/resume_cache.py`** [MODIFIED]:
   - Implemented `get_cached_dashboard_summary()`, `set_cached_dashboard_summary()`, and `invalidate_dashboard_summary()`.
6. **`backend/app/api/routers/profile.py`** [MODIFIED]:
   - Added `GET /candidates/dashboard-summary` and `POST /candidates/dashboard-summary/invalidate`.
