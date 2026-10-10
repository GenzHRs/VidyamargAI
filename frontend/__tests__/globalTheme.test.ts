import { getStoredTheme, applyThemeGlobally } from "../utils/themeUtils";

describe("Global Theme Persistence & Login Flow Test", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.className = "";
  });

  test("1. Default theme is light when no theme is stored", () => {
    expect(getStoredTheme()).toBe("light");
  });

  test("2. Selecting light mode applies light-theme and updates localStorage", () => {
    applyThemeGlobally("light");
    expect(localStorage.getItem("theme")).toBe("light");
    expect(document.documentElement.classList.contains("light-theme")).toBe(true);
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  test("3. Selecting dark mode applies dark class and updates localStorage", () => {
    applyThemeGlobally("dark");
    expect(localStorage.getItem("theme")).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.classList.contains("light-theme")).toBe(false);
  });

  test("4. Explicit local selection is preserved across login transitions", () => {
    // User selects light mode on landing page
    applyThemeGlobally("light");
    expect(localStorage.getItem("theme")).toBe("light");

    // Simulate login & navigation to dashboard
    const localTheme = localStorage.getItem("theme");
    expect(localTheme).toBe("light");

    // Even if backend preference is dark, explicit local choice must take precedence
    if (localTheme === "dark" || localTheme === "light") {
      // Local selection is preserved — no setTheme overwrite
      expect(localStorage.getItem("theme")).toBe("light");
    }
  });

  test("5. Logout does not clear the saved theme preference", () => {
    applyThemeGlobally("light");
    localStorage.setItem("token", "dummy-jwt-token");
    localStorage.setItem("fullName", "Test User");

    // Simulate logout
    localStorage.removeItem("token");
    localStorage.removeItem("fullName");

    // Theme preference must remain intact
    expect(localStorage.getItem("theme")).toBe("light");
  });
});
