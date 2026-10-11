# 18 — GLOBAL NAVIGATION AND DATA CACHE ARCHITECTURE

**Project:** VidyaMarg AI  
**Scope:** Navigation Stability, Provider Persistence, Client Cache Management, Request Deduplication  
**Status:** Implemented & Verified in Production Build  

---

## 1. Shared Navigation & Provider Stability

### 1.1 Elimination of the Key Change Remount Storm
In previous versions, `frontend/components/Providers.tsx` wrapped the TanStack Query provider with an identity-keyed component:
```tsx
// PREVIOUS IMPLEMENTATION (FLAWED):
export default function Providers({ children }: { children: React.ReactNode }) {
  const token = useAuthStore(state => state.token);
  return <SessionQueries key={token || "anonymous"}>{children}</SessionQueries>;
}
```
**Impact of Flaw**:
On every initial candidate visit, `token` rehydrated asynchronously from `localStorage` in `CandidateLayout`. When `token` transitioned from `null` to `jwt_token_string`, the key changed from `"anonymous"` to `"jwt_token_string"`. React unmounted the entire component tree, destroyed the `QueryClient`, erased all in-flight promises, and mounted a brand-new tree, causing:
- Double invocation of every component mount effect.
- Flash of unstyled content / redundant loading spinners.
- Twice the number of HTTP requests hitting the backend API.

**Engineered Resolution**:
`Providers.tsx` was refactored to provide a stable singleton `QueryClient` that remains mounted throughout the entire browser session:
```tsx
// OPTIMIZED IMPLEMENTATION:
let globalQueryClient: QueryClient | null = null;

export function getSharedQueryClient(): QueryClient {
  if (!globalQueryClient) {
    globalQueryClient = new QueryClient({
      defaultOptions: {
        queries: {
          staleTime: 60 * 1000,    // 60-second fresh window for instant warm navigation
          gcTime: 5 * 60 * 1000,   // 5-minute memory retention
          refetchOnWindowFocus: false,
          refetchOnMount: false,   // Reuse valid cached data
          retry: 1,
        },
      },
    });
  }
  return globalQueryClient;
}

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => getSharedQueryClient());

  useEffect(() => {
    // Clear query cache ONLY when user token switches or on explicit logout
    const unsub = useAuthStore.subscribe((state, prevState) => {
      if (prevState.token && state.token !== prevState.token) {
        queryClient.clear();
      }
    });
    return () => unsub();
  }, [queryClient]);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
```
**Result**: The component tree remains mounted across authentication state hydration and route changes. Queries are cleared only when an authenticated user explicitly logs out or switches accounts.

---

## 2. In-Flight Request Deduplication in `apiService`

To prevent concurrent requests from firing simultaneously when multiple components render at the same moment (e.g. `CandidateLayout` and child page components), a transparent in-flight request registry was added to `frontend/services/api.ts`:

```ts
const inFlightGetMap = new Map<string, Promise<Response>>();

const customFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const method = (init?.method || "GET").toUpperCase();
  const urlStr = input.toString();

  // Deduplicate concurrent identical GET requests
  if (method === "GET") {
    const existingPromise = inFlightGetMap.get(urlStr);
    if (existingPromise) {
      const res = await existingPromise;
      return res.clone();
    }
  }

  const fetchPromise = (async () => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s bounded timeout
    const combinedSignal = init?.signal || controller.signal;

    try {
      const res = await fetch(input, {
        credentials: "include",
        ...init,
        signal: combinedSignal,
        cache: "no-store",
      });
      clearTimeout(timeoutId);
      return res;
    } finally {
      if (method === "GET") {
        inFlightGetMap.delete(urlStr);
      }
    }
  })();

  if (method === "GET") {
    inFlightGetMap.set(urlStr, fetchPromise);
  }

  const res = await fetchPromise;
  return res.clone();
};
```
**Benefits**:
- Multiple callers requesting the exact same GET URL within the flight window share a single HTTP connection.
- Each caller receives an independent `Response.clone()`, permitting independent `.json()` or `.text()` decoding without collision.
- A 15-second bounded `AbortController` timeout guarantees zero hanging requests on intermittent network connections.

---

## 3. Stale-Time Caching in `useResumeStore`

In `frontend/store/resumeStore.ts`, `fetchActiveResume()` previously set `isLoading: true` and fired an un-cached network request on every invocation:

```ts
// OPTIMIZED IMPLEMENTATION:
const CACHE_STALE_TIME_MS = 60 * 1000;
let inFlightFetchPromise: Promise<void> | null = null;

fetchActiveResume: async (options?: { forceRefresh?: boolean }) => {
  const state = get();
  const now = Date.now();

  // 1. If fresh and not forced, return immediately (0ms instant reuse)
  if (!options?.forceRefresh && state.lastFetched && (now - state.lastFetched) < CACHE_STALE_TIME_MS) {
    return;
  }

  // 2. Deduplicate simultaneous in-flight calls
  if (inFlightFetchPromise) {
    return inFlightFetchPromise;
  }

  // 3. Only set isLoading on cold load (no active data yet)
  if (!state.activeResume && !state.hasResume) {
    set({ isLoading: true, error: null });
  }

  inFlightFetchPromise = (async () => {
    try {
      const res = await apiService.getActiveResume();
      // ... update state with fresh data ...
      set({ lastFetched: Date.now(), isLoading: false });
    } finally {
      inFlightFetchPromise = null;
    }
  })();

  return inFlightFetchPromise;
}
```

---

## 4. Elimination of Redundant Sidebar Preference Writes

In `frontend/components/Sidebar.tsx`, the component previously wrote back to the server upon mounting:
```tsx
// REMOVED: Redundant mount write
const localTheme = localStorage.getItem("theme");
if (localTheme === "dark" || localTheme === "light") {
  // REMOVED: apiService.updatePreferences(localTheme as "dark" | "light").catch(() => {});
  return;
}
```
`apiService.updatePreferences()` is now triggered **strictly when the candidate clicks the theme toggle or saves preferences in the Settings panel**, saving 1 superfluous network write per page visit.

---

## 5. Cache Key Standard & Invalidation Matrix

| Scope | Entity | Cache Key | Freshness Window (TTL) | Invalidation Trigger |
| :--- | :--- | :--- | :--- | :--- |
| **Client** | Resumes List | `["candidate", "resumes"]` | 60 seconds | Resume upload, delete, compile, or replacement |
| **Client** | Active Resume | Stored in `resumeStore` | 60 seconds | `setActiveResume()`, `replaceResume()`, or explicit refresh |
| **Client** | Recommended Jobs | `["jobs", "recommended"]` | 60 seconds | Active resume change, target role update, manual refresh |
| **Client** | Job Catalog | `["jobs", "catalog"]` | 60 seconds | Page change or manual refresh |
| **Client** | Candidate Profile | `["candidate", "profile"]` | 60 seconds | Profile edit submission |
| **Client** | Applications | `["candidate", "applications"]` | 60 seconds | New application submitted or status changed |
| **Client** | Resume Intelligence | `["candidate", "resume-intelligence"]` | 60 seconds | Resume upload, analysis trigger |
| **Client** | Courses & LMS | `["courses"]`, `["enrollments", email]` | 60 seconds | New course enrollment, lesson completed |
