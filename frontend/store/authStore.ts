import { create } from 'zustand';
import { useDashboardStore } from './dashboardStore';
import { apiService } from '@/services/api';

interface AuthState {
  token: string | null;
  role: string | null;
  fullName: string | null;
  email: string | null;
  isAuthenticated: boolean;
  isInitialized: boolean;
  isDevUser: boolean;
  login: (token: string, role: string, fullName: string, email: string, isDevUser?: boolean) => void;
  logout: () => void;
  initialize: () => Promise<void>;
  updateUser: (fullName: string, email?: string) => void;
  exitDevMode: () => void;
  resumeDevMode: () => Promise<boolean>;
}

function clearPrivateCaches() {
  if (typeof window === 'undefined') return;
  try {
    useDashboardStore.getState().reset();
  } catch (e) {}
  for (const key of Object.keys(localStorage)) {
    if (key.startsWith('cache_') || key === 'REACT_QUERY_OFFLINE_CACHE' || key === 'candidate_applied_email') {
      localStorage.removeItem(key);
    }
  }
}

const getInitialAuthState = () => {
  if (typeof window !== 'undefined') {
    try {
      const token = localStorage.getItem('token');
      const role = localStorage.getItem('role');
      const fullName = localStorage.getItem('fullName');
      const email = localStorage.getItem('email');
      const isDev = email === 'dev.candidate@vidyamarg.local' || localStorage.getItem('is_dev_mode') === 'true';
      if (token) {
        return { token, role, fullName, email, isAuthenticated: true, isInitialized: false, isDevUser: isDev };
      }
    } catch {}
  }
  return { token: null, role: null, fullName: null, email: null, isAuthenticated: false, isInitialized: false, isDevUser: false };
};

const initialAuth = getInitialAuthState();
let initPromise: Promise<void> | null = null;

export const useAuthStore = create<AuthState>((set, get) => ({
  ...initialAuth,

  login: (token, role, fullName, email, isDevUser = false) => {
    clearPrivateCaches();
    if (typeof window !== 'undefined') {
      localStorage.setItem('token', token);
      localStorage.setItem('role', role);
      localStorage.setItem('fullName', fullName);
      localStorage.setItem('email', email);
      if (isDevUser || email === 'dev.candidate@vidyamarg.local') {
        localStorage.setItem('is_dev_mode', 'true');
      } else {
        localStorage.removeItem('is_dev_mode');
      }
    }
    set({
      token,
      role,
      fullName,
      email,
      isAuthenticated: true,
      isInitialized: true,
      isDevUser: isDevUser || email === 'dev.candidate@vidyamarg.local'
    });
  },

  logout: () => {
    clearPrivateCaches();
    get().resumeDevMode();
  },

  initialize: async () => {
    if (typeof window === 'undefined') return;

    if (initPromise) {
      return initPromise;
    }

    initPromise = (async () => {
      try {
        const token = localStorage.getItem('token');
        const role = localStorage.getItem('role');
        const fullName = localStorage.getItem('fullName');
        const email = localStorage.getItem('email');

        // 1. Existing saved session in localStorage
        if (token && role && fullName && email) {
          const isDev = email === 'dev.candidate@vidyamarg.local' || localStorage.getItem('is_dev_mode') === 'true';
          set({
            token,
            role,
            fullName,
            email,
            isAuthenticated: true,
            isInitialized: true,
            isDevUser: isDev
          });
          return;
        }

        // 2. Direct Candidate Session Bootstrap (always enabled)
        const bypassEnv = process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS || process.env.NEXT_PUBLIC_DEV_MODE;
        const isBypassConfigured = bypassEnv !== 'false' && bypassEnv !== '0';

        if (isBypassConfigured) {
          const session = await apiService.getDevSession();
          if (session && session.access_token && session.user) {
            const user = session.user;
            localStorage.setItem('token', session.access_token);
            localStorage.setItem('role', user.role);
            localStorage.setItem('fullName', user.full_name);
            localStorage.setItem('email', user.email);
            localStorage.setItem('is_dev_mode', 'true');
            set({
              token: session.access_token,
              role: user.role,
              fullName: user.full_name,
              email: user.email,
              isAuthenticated: true,
              isInitialized: true,
              isDevUser: true
            });
            return;
          }
        }
      } catch (err) {
        console.warn('Testing mode initialization notice:', err);
      } finally {
        set({ isInitialized: true });
        initPromise = null;
      }
    })();

    return initPromise;
  },

  updateUser: (fullName, email) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('fullName', fullName);
      if (email) {
        localStorage.setItem('email', email);
      }
    }
    if (email) {
      set({ fullName, email });
    } else {
      set({ fullName });
    }
  },

  exitDevMode: () => {
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('disable_dev_mode', 'true');
      sessionStorage.setItem('disable_testing_mode', 'true');
    }
    get().logout();
  },

  resumeDevMode: async () => {
    if (typeof window !== 'undefined') {
      sessionStorage.removeItem('disable_dev_mode');
      sessionStorage.removeItem('disable_testing_mode');
    }
    try {
      const session = await apiService.getDevSession();
      if (session && session.access_token && session.user) {
        get().login(
          session.access_token,
          session.user.role,
          session.user.full_name,
          session.user.email,
          true
        );
        return true;
      }
      return false;
    } catch (err) {
      console.error('Failed to resume development mode:', err);
      return false;
    }
  }
}));
