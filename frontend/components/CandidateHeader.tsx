"use client";

import { useGlobalAgentStore } from "@/store/globalAgentStore";
import { Bot, Sparkles } from "lucide-react";

interface CandidateHeaderProps {
  /** Whether the AI agent panel is currently open — supplied by CandidateLayout. */
  isAgentOpen?: boolean;
  /** Toggle the AI agent panel — supplied by CandidateLayout. */
  onToggleAgent?: () => void;
}

export default function CandidateHeader({ isAgentOpen, onToggleAgent }: CandidateHeaderProps) {
  // Read unread badge from the global store — single source of truth.
  const hasAgentUnread = useGlobalAgentStore((state) => state.hasUnread);

  const handleOpenAgent = () => {
    if (onToggleAgent) {
      onToggleAgent();
    }
  };

  return (
    <header className="sticky top-0 z-30 w-full font-sans transition-colors duration-300 bg-transparent pointer-events-none">
      <div className="w-full px-4 sm:px-6 h-14 sm:h-16 flex items-center justify-end">
        {/* 🤖 PRIMARY TOP-RIGHT AI AGENT TOGGLE BUTTON AT EDGE */}
        <button
          onClick={handleOpenAgent}
          aria-label={isAgentOpen ? "Close AI Agent Column" : "Open AI Career Agent"}
          title={isAgentOpen ? "Close AI Agent Column" : "Open AI Career Agent (Natural Language Website Control)"}
          className={`pointer-events-auto relative group flex items-center gap-2 px-3.5 py-1.5 sm:px-4 sm:py-2 rounded-full font-extrabold text-xs shadow-xs hover:shadow-sm transition-all transform active:scale-95 ${
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
      </div>
    </header>
  );
}

