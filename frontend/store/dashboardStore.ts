import { create } from "zustand";
import { apiService } from "@/services/api";

export interface CareerData {
  profile: any;
  roles: any;
  skillGaps: any;
  readiness: any;
  resumes: any[];
}

export interface DashboardState {
  data: CareerData | null;
  lastFetched: number | null;
  isInitialLoading: boolean;
  isBackgroundRefreshing: boolean;
  error: string | null;
  
  // Actions
  fetchDashboard: (options?: { forceRefresh?: boolean }) => Promise<void>;
  invalidateDashboard: () => void;
  reset: () => void;
}

// 60 seconds cache freshness window for warm navigation
const CACHE_STALE_TIME_MS = 60 * 1000;

export const useDashboardStore = create<DashboardState>((set, get) => ({
  data: null,
  lastFetched: null,
  isInitialLoading: false,
  isBackgroundRefreshing: false,
  error: null,

  fetchDashboard: async (options = {}) => {
    const { data, lastFetched, isInitialLoading, isBackgroundRefreshing } = get();
    const now = Date.now();
    const isFresh = lastFetched && (now - lastFetched) < CACHE_STALE_TIME_MS;

    // 1. If we already have fresh data and not forcing refresh, return immediately (instant ~0ms!)
    if (data && isFresh && !options.forceRefresh) {
      return;
    }

    // 2. Prevent duplicate concurrent fetches
    if (isInitialLoading || isBackgroundRefreshing) {
      return;
    }

    // 3. Determine if this is an initial cold load or a warm background refresh
    if (!data) {
      set({ isInitialLoading: true, error: null });
    } else {
      set({ isBackgroundRefreshing: true, error: null });
    }

    try {
      // 4. Preferred fast path: single aggregated, Redis-cached endpoint
      try {
        const summary = await apiService.getDashboardSummary();
        if (summary && summary.profile) {
          set({
            data: {
              profile: summary.profile,
              roles: summary.roles,
              skillGaps: summary.skillGaps,
              readiness: summary.readiness,
              resumes: Array.isArray(summary.resumes) ? summary.resumes : [],
            },
            lastFetched: Date.now(),
            isInitialLoading: false,
            isBackgroundRefreshing: false,
            error: null,
          });
          return;
        }
      } catch (err) {
        console.warn("[DashboardStore] Fast aggregated summary unavailable, falling back to multi-endpoint retrieval:", err);
      }

      // 5. Fallback path: parallel individual endpoints with allSettled
      const [profile, roles, skillGaps, readiness, resumes] = await Promise.allSettled([
        apiService.getProfile(),
        apiService.getResumeRoles(),
        apiService.getResumeSkillGaps(),
        apiService.getCareerReadiness(),
        apiService.getResumes(),
      ]);

      const resolvedData: CareerData = {
        profile: profile.status === "fulfilled" ? profile.value : (data?.profile || null),
        roles: roles.status === "fulfilled" ? roles.value : (data?.roles || null),
        skillGaps: skillGaps.status === "fulfilled" ? skillGaps.value : (data?.skillGaps || null),
        readiness: readiness.status === "fulfilled" ? readiness.value : (data?.readiness || null),
        resumes: resumes.status === "fulfilled" 
          ? (Array.isArray(resumes.value) ? resumes.value : []) 
          : (data?.resumes || []),
      };

      set({
        data: resolvedData,
        lastFetched: Date.now(),
        isInitialLoading: false,
        isBackgroundRefreshing: false,
        error: null,
      });
    } catch (e: any) {
      console.error("[DashboardStore] Failed to fetch dashboard data:", e);
      set({
        isInitialLoading: false,
        isBackgroundRefreshing: false,
        error: "Failed to load dashboard data. Please try again.",
      });
    }
  },

  invalidateDashboard: () => {
    set({ lastFetched: null });
  },

  reset: () => {
    set({
      data: null,
      lastFetched: null,
      isInitialLoading: false,
      isBackgroundRefreshing: false,
      error: null,
    });
  },
}));
