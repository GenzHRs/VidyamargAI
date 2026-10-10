"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";
import { apiService } from "@/services/api";
import {
  LayoutDashboard,
  FileText,
  Briefcase,
  BookOpen,
  Bot,
  Mic2,
  Send,
  User,
  Settings,
  Moon,
  Sun,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  Menu,
  X,
  Users,
  BarChart3,
  ChevronRight,
} from "lucide-react";

import { useGlobalTheme } from "@/utils/themeUtils";

interface SidebarProps {
  portal: "candidate" | "admin";
}

const candidateLinks = [
  { name: "Dashboard", href: "/candidate/dashboard", icon: LayoutDashboard },
  { name: "Resume", href: "/candidate/resumes", icon: FileText },
  { name: "Jobs", href: "/candidate/jobs", icon: Briefcase },
  { name: "Skills & Courses", href: "/candidate/skill-lab", icon: BookOpen },
  { name: "AI Mentor", href: "/candidate/mentor", icon: Bot },
  { name: "Interview Room", href: "/candidate/interview", icon: Mic2 },
  { name: "My Applications", href: "/candidate/applications", icon: Send },
  { name: "Settings", href: "/candidate/settings", icon: Settings },
];

const adminLinks = [
  { name: "Overview", href: "/admin", icon: LayoutDashboard },
  { name: "Students", href: "/admin/candidates", icon: Users },
  { name: "Course Management", href: "/admin/courses", icon: BookOpen },
  { name: "Analytics", href: "/admin/analytics", icon: BarChart3 },
];

export default function Sidebar({ portal }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { logout, fullName, email } = useAuthStore();
  const { theme, toggleTheme, setTheme } = useGlobalTheme();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const fetchPreferences = async () => {
      try {
        const token = localStorage.getItem("token");
        if (!token) return;

        // Respect explicit local theme selection above all else — single source of truth
        const localTheme = localStorage.getItem("theme");
        if (localTheme === "dark" || localTheme === "light") {
          // Sync local theme to backend asynchronously
          apiService.updatePreferences(localTheme as "dark" | "light").catch(() => {});
          return;
        }

        // Fallback to backend preferences ONLY if no local choice exists
        const prefs = await apiService.getPreferences();
        if (prefs && prefs.theme && (prefs.theme === "dark" || prefs.theme === "light")) {
          setTheme(prefs.theme as "dark" | "light");
        }
      } catch (err) {
        console.error("Failed to fetch user preferences:", err);
      }
    };

    fetchPreferences();

    const savedCollapsed = localStorage.getItem("sidebar_collapsed");
    if (savedCollapsed === "true") {
      setTimeout(() => setCollapsed(true), 0);
    }
  }, []);

  const toggleCollapsed = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("sidebar_collapsed", String(next));
  };

  const handleLogout = () => {
    logout();
    router.push("/");
  };

  const handleProfileClick = () => {
    if (portal === "candidate") router.push("/candidate/profile");
  };

  const activeLinks = portal === "candidate" ? candidateLinks : adminLinks;
  const userInitial = fullName ? fullName[0].toUpperCase() : "U";
  const displayName = fullName || "User";
  const displayEmail = email || "";

  const isActive = (href: string) => {
    if (href === "/candidate/dashboard") return pathname === href;
    return pathname === href || pathname.startsWith(href + "/");
  };

  const NavLinks = ({ onLinkClick }: { onLinkClick?: () => void }) => (
    <nav className="flex flex-col gap-1">
      {activeLinks.map((link) => {
        const Icon = link.icon;
        const active = isActive(link.href);
        return (
          <Link
            key={link.name}
            href={link.href}
            onClick={onLinkClick}
            aria-current={active ? "page" : undefined}
            title={collapsed ? link.name : undefined}
            className={`group flex items-center ${
              collapsed ? "justify-center px-2" : "gap-3 px-3"
            } py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
              active
                ? "bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 font-semibold"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 hover:bg-slate-100/70 dark:hover:bg-slate-800/50"
            }`}
          >
            <Icon
              size={18}
              className={`shrink-0 transition-colors ${
                active
                  ? "text-blue-600 dark:text-blue-400"
                  : "text-slate-400 dark:text-slate-500 group-hover:text-slate-600 dark:group-hover:text-slate-300"
              }`}
            />
            {!collapsed && <span className="truncate">{link.name}</span>}
            {!collapsed && active && (
              <ChevronRight size={14} className="ml-auto text-blue-500/60" />
            )}
          </Link>
        );
      })}
    </nav>
  );

  const UserFooter = ({ onProfileClick }: { onProfileClick?: () => void }) => {
    const isProfileActive = pathname === "/candidate/profile" || pathname.startsWith("/candidate/profile/");

    return (
      <div className={`flex-shrink-0 border-t border-app-border ${collapsed ? "p-3" : "p-4"} space-y-1`}>
        {/* Theme Toggle */}
        <button
          onClick={toggleTheme}
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          className={`flex items-center w-full py-2.5 rounded-xl text-sm font-medium transition-all duration-200 text-slate-500 dark:text-slate-400 hover:bg-slate-100/70 dark:hover:bg-slate-800/50 hover:text-slate-700 dark:hover:text-slate-200 ${
            collapsed ? "justify-center px-2" : "gap-3 px-3"
          }`}
        >
          {theme === "dark" ? (
            <Moon size={18} className="shrink-0 text-slate-400" />
          ) : (
            <Sun size={18} className="shrink-0 text-amber-500" />
          )}
          {!collapsed && <span>{theme === "dark" ? "Dark Mode" : "Light Mode"}</span>}
        </button>

        {/* Profile User Area & Logout */}
        {collapsed ? (
          <div className="flex flex-col items-center gap-2 pt-1">
            <div
              onClick={onProfileClick || handleProfileClick}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  (onProfileClick || handleProfileClick)();
                }
              }}
              className={`w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center font-bold text-sm cursor-pointer transition-all ${
                isProfileActive
                  ? "ring-2 ring-blue-500 dark:ring-blue-400 shadow-md scale-105"
                  : "hover:ring-2 hover:ring-blue-400/50"
              }`}
              title={`View Profile (${displayName})`}
            >
              {userInitial}
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleLogout();
              }}
              className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors"
              title="Logout"
            >
              <LogOut size={15} />
            </button>
          </div>
        ) : (
          <div
            onClick={onProfileClick || handleProfileClick}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                (onProfileClick || handleProfileClick)();
              }
            }}
            title="View Profile"
            className={`group flex items-center gap-2.5 px-3 py-2.5 rounded-xl cursor-pointer transition-all duration-200 ${
              isProfileActive
                ? "bg-blue-50 dark:bg-blue-950/40 border border-blue-200/80 dark:border-blue-800/50 text-blue-600 dark:text-blue-400 font-semibold shadow-xs"
                : "hover:bg-slate-100/70 dark:hover:bg-slate-800/50 text-slate-700 dark:text-slate-300"
            }`}
          >
            <div
              className={`w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-white flex items-center justify-center font-bold text-sm shrink-0 transition-all ${
                isProfileActive
                  ? "ring-2 ring-blue-500 dark:ring-blue-400 shadow-xs"
                  : "group-hover:ring-2 group-hover:ring-blue-400/40"
              }`}
            >
              {userInitial}
            </div>
            <div className="flex-1 min-w-0">
              <p className={`text-xs font-semibold truncate ${isProfileActive ? "text-blue-600 dark:text-blue-400 font-bold" : "text-app-text"}`}>
                {displayName}
              </p>
              <p className={`text-[10px] truncate ${isProfileActive ? "text-blue-500/80 dark:text-blue-300/80" : "text-app-text-muted"}`}>
                {displayEmail}
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleLogout();
              }}
              className="p-1.5 rounded-lg text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/20 transition-colors shrink-0"
              title="Logout"
            >
              <LogOut size={15} />
            </button>
          </div>
        )}
      </div>
    );
  };

  const Logo = ({ size = "md" }: { size?: "sm" | "md" }) => (
    <div className="flex items-center gap-2">
      <div className={`${size === "sm" ? "w-7 h-7" : "w-8 h-8"} rounded-lg bg-gradient-to-br from-blue-600 to-indigo-600 flex items-center justify-center shadow-md shrink-0`}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M12 2L2 7L12 12L22 7L12 2Z" fill="white" opacity="0.95" />
          <path d="M2 17L12 22L22 17" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M2 12L12 17L22 12" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      <div className="flex items-baseline">
        <span className="text-app-text font-extrabold text-base tracking-tight">Vidyamarg</span>
        <span className="text-blue-600 dark:text-blue-400 font-extrabold text-base tracking-tight italic">AI</span>
      </div>
    </div>
  );

  const homePath = portal === "candidate" ? "/candidate/dashboard" : "/admin";

  return (
    <>
      {/* ── Mobile: sticky top header ── */}
      <header className="md:hidden flex items-center justify-between px-4 py-3 bg-transparent fixed top-0 left-0 right-0 z-40 h-16 w-full font-sans">
        <button
          onClick={() => setMobileOpen(true)}
          className="text-app-text-muted hover:text-app-text p-2 min-w-11 min-h-11 flex items-center justify-center rounded-lg hover:bg-app-bg transition-colors"
          title="Open Menu"
        >
          <Menu size={20} />
        </button>

        <div
          className="cursor-pointer"
          onClick={() => router.push(homePath)}
        >
          <Logo size="sm" />
        </div>

        <div className="flex items-center gap-2">
          {/* Top-Right AI Agent Button on Mobile */}
          <button
            onClick={() => window.dispatchEvent(new CustomEvent("open-career-agent"))}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gradient-to-r from-purple-600 via-indigo-600 to-blue-600 text-white font-extrabold text-xs shadow-xs"
            title="Open AI Career Agent"
          >
            <Bot size={14} />
            <span>AI Agent</span>
          </button>

          <button
            onClick={toggleTheme}
            className="text-app-text-muted hover:text-app-text p-2 min-w-10 min-h-10 flex items-center justify-center rounded-lg hover:bg-app-bg transition-colors"
            title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          >
            {theme === "dark" ? <Moon size={18} className="text-slate-400" /> : <Sun size={18} className="text-amber-500" />}
          </button>
        </div>
      </header>

      {/* ── Mobile: drawer overlay ── */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            onClick={() => setMobileOpen(false)}
            className="fixed inset-0 bg-slate-950/40 dark:bg-black/60 backdrop-blur-sm"
          />
          <aside className="relative flex flex-col w-72 max-w-xs h-full bg-app-surface border-r border-app-border z-50">
            {/* Header */}
            <div className="flex-shrink-0 px-5 py-4 flex items-center justify-between border-b border-app-border">
              <div className="cursor-pointer" onClick={() => { setMobileOpen(false); router.push(homePath); }}>
                <Logo />
              </div>
              <button
                onClick={() => setMobileOpen(false)}
                className="p-2 rounded-lg text-app-text-muted hover:text-app-text hover:bg-app-bg transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Nav */}
            <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3">
              <NavLinks onLinkClick={() => setMobileOpen(false)} />
            </div>

            <UserFooter onProfileClick={() => { setMobileOpen(false); handleProfileClick(); }} />
          </aside>
        </div>
      )}

      {/* ── Desktop: fixed sidebar ── */}
      <aside
        className={`hidden md:flex ${
          collapsed ? "w-[72px]" : "w-64"
        } h-screen border-r border-app-border bg-app-surface flex-col shrink-0 font-sans transition-all duration-300`}
      >
        {/* Logo + collapse button */}
        <div className={`flex-shrink-0 flex items-center ${collapsed ? "justify-center p-3 h-16" : "justify-between px-5 h-16"} border-b border-app-border`}>
          {!collapsed && (
            <div className="cursor-pointer" onClick={() => router.push(homePath)}>
              <Logo />
            </div>
          )}
          <button
            onClick={toggleCollapsed}
            className="p-2 rounded-lg text-app-text-muted hover:text-app-text hover:bg-app-bg transition-colors"
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
          </button>
        </div>

        {/* Navigation */}
        <div className={`flex-1 min-h-0 overflow-y-auto overflow-x-hidden ${collapsed ? "px-3" : "px-4"} py-4`}>
          <NavLinks />
        </div>

        <UserFooter />
      </aside>

      {/* ── Mobile bottom navigation bar (quick access) ── */}
      {portal === "candidate" && (
        <nav
          className="sm:hidden fixed bottom-0 left-0 right-0 z-40 bg-app-surface border-t border-app-border flex justify-around items-center px-2 w-full font-sans"
          style={{
            paddingBottom: "max(12px, env(safe-area-inset-bottom, 12px))",
            height: "calc(60px + env(safe-area-inset-bottom, 0px))",
          }}
        >
          {[
            { name: "Dashboard", href: "/candidate/dashboard", icon: LayoutDashboard },
            { name: "Resume", href: "/candidate/resumes", icon: FileText },
            { name: "Jobs", href: "/candidate/jobs", icon: Briefcase },
            { name: "Courses", href: "/candidate/skill-lab", icon: BookOpen },
            { name: "Profile", href: "/candidate/profile", icon: User },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = isActive(tab.href);
            return (
              <Link
                key={tab.name}
                href={tab.href}
                aria-current={active ? "page" : undefined}
                className={`flex flex-col items-center justify-center flex-1 py-1 gap-0.5 transition-all ${
                  active ? "text-blue-600 dark:text-blue-400" : "text-app-text-muted hover:text-app-text"
                }`}
              >
                <Icon size={19} className="shrink-0" />
                <span className="text-[9px] font-semibold tracking-tight">{tab.name}</span>
              </Link>
            );
          })}
        </nav>
      )}
    </>
  );
}
