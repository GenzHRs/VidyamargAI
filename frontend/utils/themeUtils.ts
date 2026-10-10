"use client";

import { useEffect, useState } from "react";
import { apiService } from "@/services/api";

export type ThemeMode = "dark" | "light";

export const getStoredTheme = (): ThemeMode => {
  if (typeof window === "undefined") return "dark";
  const saved = localStorage.getItem("theme");
  if (saved === "dark" || saved === "light") return saved;
  if (window.matchMedia("(prefers-color-scheme: dark)").matches) return "dark";
  return "light";
};

export const applyThemeGlobally = (theme: ThemeMode) => {
  if (typeof window === "undefined") return;

  localStorage.setItem("theme", theme);

  if (theme === "light") {
    document.documentElement.classList.add("light-theme");
    document.documentElement.classList.remove("dark");
  } else {
    document.documentElement.classList.remove("light-theme");
    document.documentElement.classList.add("dark");
  }

  // Notify all components in the current tab
  window.dispatchEvent(new CustomEvent("theme-change", { detail: theme }));

  // Persist preference to backend DB if user is logged in
  const token = localStorage.getItem("token");
  if (token) {
    apiService.updatePreferences(theme).catch(() => {});
  }
};

export function useGlobalTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(getStoredTheme);

  useEffect(() => {
    const current = getStoredTheme();
    setThemeState(current);

    const handleThemeChange = (e: Event) => {
      const customEvent = e as CustomEvent<ThemeMode>;
      if (customEvent.detail === "dark" || customEvent.detail === "light") {
        setThemeState(customEvent.detail);
      } else {
        setThemeState(getStoredTheme());
      }
    };

    window.addEventListener("theme-change", handleThemeChange);
    window.addEventListener("storage", handleThemeChange);

    return () => {
      window.removeEventListener("theme-change", handleThemeChange);
      window.removeEventListener("storage", handleThemeChange);
    };
  }, []);

  const setTheme = (nextTheme: ThemeMode) => {
    setThemeState(nextTheme);
    applyThemeGlobally(nextTheme);
  };

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
  };

  return { theme, setTheme, toggleTheme };
}
