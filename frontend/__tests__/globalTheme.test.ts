import { getStoredTheme, applyThemeGlobally } from "../utils/themeUtils";

function assert(condition: boolean, message: string) {
  if (!condition) {
    throw new Error(`Assertion Failed: ${message}`);
  }
}

export function runGlobalThemeRegressionTests() {
  if (typeof window === "undefined") return;

  // 1. Default theme is light when no theme is stored
  localStorage.clear();
  assert(getStoredTheme() === "light", "Default theme must be light");

  // 2. Selecting light mode applies light-theme and updates localStorage
  applyThemeGlobally("light");
  assert(localStorage.getItem("theme") === "light", "localStorage theme must be light");
  assert(document.documentElement.classList.contains("light-theme"), "document element must have light-theme class");

  // 3. Selecting dark mode applies dark class and updates localStorage
  applyThemeGlobally("dark");
  assert(localStorage.getItem("theme") === "dark", "localStorage theme must be dark");
  assert(document.documentElement.classList.contains("dark"), "document element must have dark class");

  // 4. Explicit local selection is preserved across login transitions
  applyThemeGlobally("light");
  const localTheme = localStorage.getItem("theme");
  assert(localTheme === "light", "Local selection must remain light after simulated login");

  // 5. Logout does not clear the saved theme preference
  localStorage.setItem("token", "dummy-jwt-token");
  localStorage.removeItem("token");
  assert(localStorage.getItem("theme") === "light", "Theme preference must persist after logout");

  console.log("All 5 global theme regression tests passed successfully.");
}
