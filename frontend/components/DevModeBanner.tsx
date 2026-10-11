"use client";

import { useAuthStore } from "@/store/authStore";
import { useRouter } from "next/navigation";
import { RefreshCw, Terminal, ShieldAlert } from "lucide-react";

export default function DevModeBanner() {
  const router = useRouter();
  const { isDevUser, email, resumeDevMode } = useAuthStore();

  const isDevModeEnv =
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true" ||
    process.env.NEXT_PUBLIC_DEV_MODE === "true" ||
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "1" ||
    process.env.NEXT_PUBLIC_DEV_MODE === "1";

  // Only render banner if Testing / Dev Mode is enabled and user is in the test session
  if (!isDevModeEnv && !isDevUser) {
    return null;
  }

  const handleResetSession = async () => {
    await resumeDevMode();
    router.replace("/candidate/dashboard");
  };

  return (
    <div
      role="banner"
      aria-label="Testing Mode Indicator"
      className="w-full bg-amber-500/15 border-b border-amber-500/40 text-amber-950 dark:text-amber-200 px-4 py-1.5 text-xs flex flex-wrap items-center justify-between gap-2 font-sans z-50 shrink-0"
    >
      <div className="flex items-center gap-2 font-bold tracking-tight">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
        </span>
        <span className="text-[11px] uppercase tracking-wider font-extrabold text-amber-800 dark:text-amber-300">
          TESTING MODE — TEST CANDIDATE
        </span>
        <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-amber-500/20 border border-amber-500/30 text-amber-900 dark:text-amber-100 font-semibold">
          {email || "dev.candidate@vidyamarg.local"}
        </span>
      </div>

      <div className="flex items-center gap-3">
        <span className="text-[10px] text-amber-700/80 dark:text-amber-300/80 hidden md:inline font-medium">
          Authorized testing active (landing, login, and signup bypassed)
        </span>
        <button
          onClick={handleResetSession}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-amber-600/85 hover:bg-amber-600 text-white rounded-lg text-[11px] font-bold transition-all shadow-xs cursor-pointer"
          title="Refresh seeded test candidate data"
        >
          <RefreshCw size={11} />
          <span>Reset Test Data</span>
        </button>
      </div>
    </div>
  );
}
