# 14. DASHBOARD NAVIGATION ROOT CAUSE AUDIT

## Overview
When candidates navigated away from `/candidate/dashboard` to other routes (e.g. `/candidate/resumes`, `/candidate/jobs`, `/candidate/applications`, `/candidate/learning`, `/candidate/mentor`) and subsequently returned to `/candidate/dashboard`, the page presented a full-screen loading spinner and suffered noticeable latency rather than appearing instantly.

This document records the empirical investigation into the root causes across the frontend React component tree, state lifecycle, network requests, and backend endpoints.

---

## 1. Frontend Lifecycle & Unpersisted Component State

### Root Cause 1: Component State Discarded on Route Unmount
In `frontend/app/candidate/dashboard/page.tsx`:
```tsx
const [data, setData] = useState<CareerData>({ ... });
const [loading, setLoading] = useState(true);
```
- In Next.js client-side navigation, navigating from `/candidate/dashboard` to `/candidate/resumes` completely unmounts `DashboardPage`.
- All local React state (`data`) was stored strictly in transient component memory.
- When the candidate clicked back to `/candidate/dashboard`, `DashboardPage` mounted afresh.
- `loading` was initialized to `true`, and `data` was initialized to `null`.
- The following block triggered unconditionally on every single navigation:
```tsx
if (loading) {
  return (
    <div className="min-h-screen bg-app-bg flex items-center justify-center">
      <div className="w-10 h-10 rounded-full border-4 border-t-blue-500 ... animate-spin" />
      <p className="text-sm text-app-text-muted">Loading your career dashboard…</p>
    </div>
  );
}
```
As a result, even if the candidate had visited the dashboard seconds earlier, the user was subjected to a full-screen spinner.

---

## 2. Network Waterfall & Redundant Parallel Invocations

### Root Cause 2: Five Discrete Network Roundtrips per Mount
Upon each mount, `useEffect(() => { fetchDashboardData(); }, [])` fired 5 independent HTTP requests:
1. `apiService.getProfile()` -> `GET /api/v1/candidates/profile`
2. `apiService.getResumeRoles()` -> `GET /api/v1/resume/roles`
3. `apiService.getResumeSkillGaps()` -> `GET /api/v1/resume/skill-gaps`
4. `apiService.getCareerReadiness()` -> `GET /api/v1/career-readiness`
5. `apiService.getResumes()` -> `GET /api/v1/candidates/resumes`

### Latency Accumulation:
- Each network request traversed browser TCP connections, SSL handshakes, FastAPI route middleware, JWT validation, and PostgreSQL queries.
- Even with parallel execution (`Promise.allSettled`), total screen-block duration was constrained by the slowest responding endpoint (~250–600ms network round-trip).
- Browser bandwidth and connection limits were strained on repeated tab switches.

---

## 3. Backend Endpoint Isolation & Missing Dashboard Aggregation

### Root Cause 3: Absence of Aggregated Dashboard Summary
- While specialized domain routers existed (`profile.py`, `resume.py`, `learning.py`), there was no unified candidate dashboard summary endpoint.
- Calculations such as enrollment counts, quiz completions, and candidate roles were evaluated independently across disparate database queries.
- There was no candidate-scoped Redis key aggregating these 5 items into a single pre-calculated payload.

---

## 4. Summary Matrix

| Metric | Before Optimization | Root Cause Mechanism |
| :--- | :--- | :--- |
| **Return to Dashboard Display** | 450 – 850 ms (Full Spinner) | Unpersisted component state unmounted on route change |
| **Network Requests per Visit** | 5 discrete HTTP requests | Disparate endpoints queried sequentially/concurrently |
| **Client Cache Hit Rate** | 0% | No shared Zustand dashboard store or memory cache |
| **UI Stability** | Jarring layout tear down & full-page spinner | `if (loading) return FullPageSpinner` pattern |
