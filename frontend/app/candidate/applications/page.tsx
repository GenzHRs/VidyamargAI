"use client";

import { useState } from "react";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { apiService } from "@/services/api";
import {
  Send,
  Building2,
  Calendar,
  MapPin,
  ChevronRight,
  Filter,
  Search,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  FileText,
  ExternalLink,
} from "lucide-react";
import Link from "next/link";

interface Application {
  id: number;
  job_title?: string;
  company?: string;
  location?: string;
  status?: string;
  applied_at?: string;
  interview_date?: string;
  application_url?: string;
}

const STATUS_CONFIG: Record<string, { label: string; color: string; icon: any }> = {
  applied: { label: "Applied", color: "bg-blue-100 dark:bg-blue-950/40 text-blue-700 dark:text-blue-400", icon: Send },
  reviewing: { label: "Under Review", color: "bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400", icon: Clock },
  interview: { label: "Interview Scheduled", color: "bg-violet-100 dark:bg-violet-950/40 text-violet-700 dark:text-violet-400", icon: Calendar },
  offer: { label: "Offer Received", color: "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400", icon: CheckCircle },
  rejected: { label: "Rejected", color: "bg-red-100 dark:bg-red-950/40 text-red-700 dark:text-red-400", icon: XCircle },
  withdrawn: { label: "Withdrawn", color: "bg-slate-100 dark:bg-slate-800 text-slate-500", icon: XCircle },
};

const getInitialApplications = (): Application[] => {
  if (typeof window !== "undefined") {
    try {
      const cached = localStorage.getItem("cache_candidate_applications");
      if (cached) {
        const parsed = JSON.parse(cached);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {}
  }
  return [];
};

export default function ApplicationsPage() {
  const { data: applications = [], isLoading } = useQuery<Application[]>({
    queryKey: ["candidate", "applications"],
    queryFn: async () => {
      try {
        const res = await apiService.getApplications?.();
        const list = Array.isArray(res) ? res : [];
        if (typeof window !== "undefined" && list.length > 0) {
          try { localStorage.setItem("cache_candidate_applications", JSON.stringify(list)); } catch {}
        }
        return list;
      } catch {
        return getInitialApplications();
      }
    },
    initialData: () => getInitialApplications(),
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
  });
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");


  const filtered = applications.filter((a) => {
    const matchSearch = !search ||
      (a.job_title || "").toLowerCase().includes(search.toLowerCase()) ||
      (a.company || "").toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === "All" || a.status === statusFilter;
    return matchSearch && matchStatus;
  });

  const statusCounts = Object.keys(STATUS_CONFIG).reduce((acc, s) => {
    acc[s] = applications.filter((a) => a.status === s).length;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="min-h-screen bg-app-bg text-app-text font-sans">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-app-text">My Applications</h1>
          <p className="text-sm text-app-text-muted mt-0.5">Track all your job applications in one place</p>
        </div>

        {/* Stats */}
        {applications.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "Total", value: applications.length, color: "text-app-text" },
              { label: "Interview", value: statusCounts.interview || 0, color: "text-violet-600 dark:text-violet-400" },
              { label: "Offers", value: statusCounts.offer || 0, color: "text-emerald-600 dark:text-emerald-400" },
              { label: "Rejected", value: statusCounts.rejected || 0, color: "text-red-600 dark:text-red-400" },
            ].map((s) => (
              <div key={s.label} className="bg-app-surface border border-app-border rounded-2xl p-4 text-center">
                <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
                <p className="text-xs text-app-text-muted font-medium mt-0.5">{s.label}</p>
              </div>
            ))}
          </div>
        )}

        {/* Filters */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-app-text-muted" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by role or company…"
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-app-border bg-app-surface text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-all"
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2.5 rounded-xl border border-app-border bg-app-surface text-sm focus:outline-none"
          >
            <option value="All">All Status</option>
            {Object.entries(STATUS_CONFIG).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
        </div>

        {/* Content */}
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-4 text-center">
            <Send size={36} className="text-app-text-muted/30" />
            <div>
              <p className="font-semibold text-app-text">No applications yet</p>
              <p className="text-sm text-app-text-muted mt-1 max-w-sm">
                {applications.length === 0
                  ? "Browse jobs and start applying to track them here."
                  : "No applications match your current filters."}
              </p>
            </div>
            {applications.length === 0 && (
              <Link
                href="/candidate/jobs"
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 transition-colors"
              >
                Browse Jobs <ChevronRight size={14} />
              </Link>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((app) => {
              const statusConf = STATUS_CONFIG[app.status || "applied"] || STATUS_CONFIG.applied;
              const StatusIcon = statusConf.icon;
              return (
                <div key={app.id} className="bg-app-surface border border-app-border rounded-2xl p-5 hover:border-blue-200 dark:hover:border-blue-800/60 transition-all">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3">
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-blue-950/40 dark:to-indigo-950/40 flex items-center justify-center border border-app-border shrink-0">
                        <Building2 size={16} className="text-blue-500" />
                      </div>
                      <div>
                        <h3 className="font-bold text-sm text-app-text">{app.job_title || "Job Application"}</h3>
                        <p className="text-xs text-app-text-muted mt-0.5">{app.company || "Company"}</p>
                        <div className="flex flex-wrap gap-2 mt-2">
                          {app.location && (
                            <span className="flex items-center gap-1 text-[11px] text-app-text-muted">
                              <MapPin size={10} /> {app.location}
                            </span>
                          )}
                          {app.applied_at && (
                            <span className="flex items-center gap-1 text-[11px] text-app-text-muted">
                              <Calendar size={10} /> Applied {new Date(app.applied_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold shrink-0 ${statusConf.color}`}>
                      <StatusIcon size={11} />
                      {statusConf.label}
                    </span>
                  </div>

                  {app.interview_date && (
                    <div className="mt-3 pt-3 border-t border-app-border flex items-center gap-2 text-xs text-violet-600 dark:text-violet-400">
                      <Calendar size={12} />
                      Interview: {new Date(app.interview_date).toLocaleString()}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
