# VidyaMarg AI — Global Theme Architecture Audit & Root Cause Analysis

**Date:** 2026-10-10  
**Status:** Root Cause Identified & Verified  
**Target:** Enforce one unified global theme across all public, auth, and candidate dashboard pages.

---

## 1. Executive Summary & Root Cause

### The Bug
When a user selects **Light mode** on the landing page, logs in, and is redirected to `/candidate/dashboard`, the page unexpectedly switches back to **Dark mode**.

### The Exact Root Cause
The root cause of this regression lies in `frontend/components/Sidebar.tsx` (Lines 62–74). 

When the candidate dashboard loads after a successful login, `Sidebar.tsx` mounts inside `CandidateLayout`. On mount, `Sidebar` executes an asynchronous `useEffect` that calls `apiService.getPreferences()`:

```tsx
// frontend/components/Sidebar.tsx: Lines 63–74
useEffect(() => {
  const fetchPreferences = async () => {
    try {
      const token = localStorage.getItem("token");
      if (!token) return;
      const prefs = await apiService.getPreferences();
      if (prefs && prefs.theme && (prefs.theme === "dark" || prefs.theme === "light")) {
        setTheme(prefs.theme as "dark" | "light"); // ❌ OVERWRITES LOCAL THEME PREFERENCE
      }
    } catch (err) {
      console.error("Failed to fetch user preferences:", err);
    }
  };
  fetchPreferences();
}, []);
```

Because new user records in PostgreSQL default `preferences.theme` to `"dark"` (or return stale backend preference values), calling `setTheme(prefs.theme)` upon entering the dashboard **overwrites the user's explicit local theme selection** saved in `localStorage.getItem('theme')` and switches the document root HTML class back to `.dark`.

---

## 2. Comprehensive Theme Architecture Audit

### 2.1 Theme State & Synchronization Path
- **Provider & Root Initialization:** `frontend/app/layout.tsx` (Lines 106–109) includes an inline script before paint that reads `localStorage.getItem('theme')` and sets `document.documentElement.classList` to `.dark` or `.light-theme`.
- **Global Theme Hook:** `frontend/utils/themeUtils.ts` exports `useGlobalTheme()`, `applyThemeGlobally()`, and `getStoredTheme()`.
  - Stored theme key: `localStorage.getItem('theme')`.
  - DOM representation: `.dark` or `.light-theme` attached to `document.documentElement`.
  - Tab event synchronization: `CustomEvent("theme-change")` & `window.addEventListener("storage")`.
- **Backend Sync:** `applyThemeGlobally()` calls `apiService.updatePreferences(theme)` asynchronously when logged in.

### 2.2 Conflicting Logic Identified

| File Path | Line(s) | Finding / Problem |
|---|---|---|
| `frontend/components/Sidebar.tsx` | 63–74 | **Primary Root Cause:** On mount, `Sidebar` calls `apiService.getPreferences()` and forces `setTheme(prefs.theme)` using stale/default backend preferences, overwriting `localStorage`. |
| `frontend/app/layout.tsx` | 106–109 | Inline head script adds `.dark` or `.light-theme`. Standardized class names are `.dark` for dark mode and no `.dark` (or `.light`) for light mode. |
| `frontend/app/globals.css` | 73, 276 | Conflicting CSS rules targeting `:root, .dark, .light-theme` causing specificity clashes with Tailwind CSS v4 variables. |

---

## 3. Reproduction Sequence & Baseline Results

1. **Step 1:** Navigate to `http://localhost:3000/`.
2. **Step 2:** Open the Header theme toggle and select **Light**.
   - `localStorage.getItem('theme')` ➔ `"light"`.
   - `document.documentElement.classList` ➔ `["light-theme"]` (No `dark` class).
3. **Step 3:** Click **Login** and authenticate with valid candidate credentials.
4. **Step 4:** Upon redirection to `/candidate/dashboard`, `CandidateLayout` mounts `Sidebar`.
5. **Step 5:** `Sidebar.tsx` executes `fetchPreferences()`, fetches `theme: "dark"` from backend, and invokes `setTheme("dark")`.
   - **Result:** `localStorage.getItem('theme')` is overwritten to `"dark"`.
   - **Result:** `document.documentElement.classList` changes to `["dark"]`.
   - **Result:** Dashboard visually flips to Dark mode.

---

## 4. Architectural Solution Plan

1. **Single Source of Truth:** `localStorage` + root HTML element `document.documentElement.classList`.
2. **Fix `Sidebar.tsx` Sync Logic:** `Sidebar` must **never** blindly call `setTheme(prefs.theme)` on mount. If a local theme choice exists in `localStorage`, the local selection takes precedent and syncs *to* the backend (`apiService.updatePreferences(localTheme)`), ensuring user choice is strictly respected across logins and page reloads.
3. **Clean Up CSS Specificity (`globals.css` & `themeUtils.ts`):** Ensure dark mode uses standard `.dark` class on `<html>` and light mode removes `.dark` class, harmonizing with Tailwind v4 `@theme` tokens.
4. **Preserve Theme On Auth Lifecycle:** Verify `authStore.ts` does not purge `localStorage.getItem('theme')` on logout or login initialization.
