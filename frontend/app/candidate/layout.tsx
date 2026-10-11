"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";
import { useResumeStore } from "@/store/resumeStore";
import { useGlobalAgentStore } from "@/store/globalAgentStore";
import Sidebar from "@/components/Sidebar";
import CandidateHeader from "@/components/CandidateHeader";
import AskVidyamargAgent from "@/components/AskVidyamargAgent";

import { AgentActionBridge } from "@/services/agentActionBridge";
import DevModeBanner from "@/components/DevModeBanner";

export default function CandidateLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isAuthenticated, email, initialize } = useAuthStore();
  const fetchActiveResume = useResumeStore((state) => state.fetchActiveResume);
  const [mounted, setMounted] = useState(false);

  // Register router with AgentActionBridge for website control execution
  useEffect(() => {
    AgentActionBridge.registerRouter(router);
    return () => {
      AgentActionBridge.unregisterRouter();
    };
  }, [router]);

  // Global agent panel state — read directly from the shared store.
  const isAgentOpen = useGlobalAgentStore((state) => state.isOpen);
  const toggleAgent = useGlobalAgentStore((state) => state.toggle);
  const closeAgent = useGlobalAgentStore((state) => state.close);
  const setOwnerEmail = useGlobalAgentStore((state) => state.setOwnerEmail);

  const isInitialized = useAuthStore((state) => state.isInitialized);

  const isBypassConfigured =
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true" ||
    process.env.NEXT_PUBLIC_DEV_MODE === "true" ||
    process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "1" ||
    process.env.NEXT_PUBLIC_DEV_MODE === "1";

  useEffect(() => {
    let active = true;
    initialize().finally(() => {
      if (active) setMounted(true);
    });
    return () => {
      active = false;
    };
  }, [initialize]);

  useEffect(() => {
    if (mounted && isAuthenticated) {
      fetchActiveResume();
    }
  }, [mounted, isAuthenticated, fetchActiveResume]);

  // Scope the persisted conversation to the authenticated user.
  useEffect(() => {
    if (mounted && isAuthenticated && email) {
      setOwnerEmail(email);
    }
  }, [mounted, isAuthenticated, email, setOwnerEmail]);

  useEffect(() => {
    if (mounted && isInitialized && !isAuthenticated) {
      if (!isBypassConfigured) {
        router.replace("/login");
      }
    }
  }, [mounted, isInitialized, isAuthenticated, router, isBypassConfigured]);

  if (!mounted || !isInitialized) {
    return (
      <div className="h-screen w-full bg-app-bg flex flex-col items-center justify-center font-sans text-app-text">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
          <span className="text-sm font-medium text-app-text-muted">
            Opening VidyaMarg AI Workspace...
          </span>
        </div>
      </div>
    );
  }

  if (mounted && !isAuthenticated && !isBypassConfigured) {
    return null;
  }

  return (
    <div className="h-screen w-full bg-app-bg flex flex-col overflow-hidden relative font-sans transition-colors duration-300">
      <DevModeBanner />
      <div className="flex-1 flex flex-row min-h-0 overflow-hidden relative">
        <Sidebar portal="candidate" />

        {/* Main content column — min-w-0 prevents it from overflowing the flex container */}
        <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden relative">
          <CandidateHeader
            isAgentOpen={isAgentOpen}
            onToggleAgent={toggleAgent}
          />
          <main className="flex-1 min-w-0 min-h-0 overflow-y-auto overflow-x-hidden bg-app-bg text-app-text transition-colors duration-300 font-sans pb-16 sm:pb-0 workspace-container">
            {children}
          </main>
        </div>

        {/* AI Agent panel — always mounted so conversation persists across navigations.
            The panel renders null internally when closed, keeping the mount stable. */}
        <AskVidyamargAgent isOpen={isAgentOpen} onClose={closeAgent} />
      </div>
    </div>
  );
}
