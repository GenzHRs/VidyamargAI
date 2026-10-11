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
    if (mounted && !isAuthenticated) {
      router.replace("/login");
    }
  }, [mounted, isAuthenticated, router]);

  if (mounted && !isAuthenticated) {
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
