"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuthStore } from "@/store/authStore";
import { useGlobalAgentStore } from "@/store/globalAgentStore";
import { apiService } from "@/services/api";
import {
  Bot,
  Sparkles,
  Bell,
  Sun,
  Moon,
} from "lucide-react";

import { useGlobalTheme } from "@/utils/themeUtils";

interface CandidateHeaderProps {
  /** Whether the AI agent panel is currently open — supplied by CandidateLayout. */
  isAgentOpen?: boolean;
  /** Toggle the AI agent panel — supplied by CandidateLayout. */
  onToggleAgent?: () => void;
}

export default function CandidateHeader({ isAgentOpen, onToggleAgent }: CandidateHeaderProps) {
  const { fullName } = useAuthStore();
  // Read unread badge from the global store — single source of truth.
  const hasAgentUnread = useGlobalAgentStore((state) => state.hasUnread);

  const { theme, toggleTheme } = useGlobalTheme();
  const [unreadNotifications, setUnreadNotifications] = useState(0);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  const handleOpenAgent = () => {
    if (onToggleAgent) {
      onToggleAgent();
    }
  };

  const userInitial = fullName ? fullName[0].toUpperCase() : "C";

  return (
    <header className="sticky top-0 z-30 w-full font-sans transition-colors duration-300 bg-transparent">
      <div className="w-full px-4 sm:px-6 h-14 sm:h-16 flex items-center justify-end gap-2 sm:gap-3">

        {/* 🤖 PRIMARY TOP-RIGHT AI AGENT TOGGLE BUTTON */}
        <button
          onClick={handleOpenAgent}
          aria-label={isAgentOpen ? "Close AI Agent Column" : "Open AI Career Agent"}
          title={isAgentOpen ? "Close AI Agent Column" : "Open AI Career Agent (Natural Language Website Control)"}
          className={`relative group flex items-center gap-2 px-3.5 py-1.5 sm:px-4 sm:py-2 rounded-full font-extrabold text-xs shadow-xs hover:shadow-sm transition-all transform active:scale-95 ${
            isAgentOpen
              ? "bg-purple-700 text-white ring-2 ring-purple-400 shadow-purple-500/30"
              : "bg-gradient-to-r from-purple-600 via-indigo-600 to-blue-600 hover:from-purple-500 hover:to-blue-500 text-white"
          }`}
        >
          <div className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center shrink-0">
            <Bot size={13} className="text-white" />
          </div>

          <span className="tracking-tight">{isAgentOpen ? "Agent ✓" : "AI Agent"}</span>
          {!isAgentOpen && <Sparkles size={13} className="text-amber-300 animate-pulse shrink-0" />}

          {/* Unread badge — only when panel is closed and there's a pending reply */}
          {hasAgentUnread && !isAgentOpen && (
            <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-amber-500 text-[9px] font-black text-slate-950 items-center justify-center">
                !
              </span>
            </span>
          )}
        </button>

        {/* Notifications Dropdown Button */}
        <div className="relative">
          <button
            onClick={() => setNotificationsOpen(!notificationsOpen)}
            className="relative p-2 rounded-xl text-app-text-muted hover:text-app-text hover:bg-app-surface/50 transition-colors"
            title="Notifications"
          >
            <Bell size={18} />
            {unreadNotifications > 0 && (
              <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-blue-600" />
            )}
          </button>

          {/* Notifications Dropdown Panel */}
          {notificationsOpen && (
            <div className="absolute right-0 mt-2 w-72 rounded-2xl border border-app-border bg-app-surface shadow-xl p-3 z-50 space-y-2 text-xs">
              <div className="flex items-center justify-between pb-2 border-b border-app-border">
                <span className="font-bold text-app-text">Career Notifications</span>
                <button
                  onClick={() => { setUnreadNotifications(0); setNotificationsOpen(false); }}
                  className="text-[10px] text-blue-600 hover:underline"
                >
                  Dismiss
                </button>
              </div>
              <p className="text-[11px] text-app-text-muted py-2 text-center">No new notifications</p>
            </div>
          )}
        </div>

        {/* Theme Switcher */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-xl text-app-text-muted hover:text-app-text hover:bg-app-surface/50 transition-colors"
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          {theme === "dark" ? <Moon size={18} className="text-slate-400" /> : <Sun size={18} className="text-amber-500" />}
        </button>

        {/* Candidate Profile Avatar */}
        <Link
          href="/candidate/profile"
          className="flex items-center gap-2 pl-1"
          title={fullName || "Candidate Profile"}
        >
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 text-white font-bold text-xs flex items-center justify-center shadow-xs hover:ring-2 hover:ring-purple-400/40 transition-all">
            {userInitial}
          </div>
        </Link>

      </div>
    </header>
  );
}
