"use client";
import React, { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useAuthStore } from "@/store/authStore";

// Stable global query client instance to prevent remounting and cache destruction across route changes
let globalQueryClient: QueryClient | null = null;

export function getSharedQueryClient(): QueryClient {
  if (!globalQueryClient) {
    globalQueryClient = new QueryClient({
      defaultOptions: {
        queries: {
          staleTime: 60 * 1000, // 60 seconds fresh window for instant warm navigation
          gcTime: 5 * 60 * 1000, // 5 minutes garbage collection time
          refetchOnWindowFocus: false,
          refetchOnMount: false, // Reuse valid cached queries unless stale
          retry: 1,
        },
      },
    });
  }
  return globalQueryClient;
}

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => getSharedQueryClient());

  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("REACT_QUERY_OFFLINE_CACHE");
    }

    // Clear query cache only when switching from one authenticated user to another or on explicit logout
    const unsub = useAuthStore.subscribe((state, prevState) => {
      if (prevState.token && state.token !== prevState.token) {
        queryClient.clear();
      }
    });

    return () => unsub();
  }, [queryClient]);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

