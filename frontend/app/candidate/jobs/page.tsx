"use client";

import { useEffect, useState, useCallback, useMemo, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiService } from "@/services/api";
import { useResumeStore } from "@/store/resumeStore";
import {
  Briefcase,
  Search,
  Filter,
  MapPin,
  Clock,
  Star,
  Bookmark,
  BookmarkCheck,
  ExternalLink,
  TrendingUp,
  CheckCircle,
  AlertCircle,
  Zap,
  RefreshCw,
  FileText,
  ChevronRight,
  Building2,
  SlidersHorizontal,
  X,
  Target,
  Sparkles,
  Check,
} from "lucide-react";

interface Job {
  id: number | string;
  title: string;
  company: string;
  location?: string;
  employment_type?: string;
  salary?: string;
  description?: string;
  required_skills?: string[];
  match_score?: number;
  match_explanation?: string;
  matched_skills?: string[];
  missing_skills?: string[];
  application_url?: string;
  posted_date?: string;
  source?: string;
  role_category?: string;
  industry?: string;
}

function isValidUrl(url?: string): boolean {
  if (!url) return false;
  const trimmed = url.trim().toLowerCase();
  if (
    trimmed === "" ||
    trimmed === "#" ||
    trimmed.startsWith("javascript:") ||
    trimmed.includes("fake-job") ||
    trimmed.includes("example-job") ||
    trimmed.includes("demo-job")
  ) {
    return false;
  }
  return true;
}

function MatchBadge({ score }: { score: number }) {
  const color =
    score >= 80
      ? "bg-emerald-100 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-400"
      : score >= 60
      ? "bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-400"
      : "bg-slate-100 dark:bg-slate-800 text-slate-500";
  return (
    <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${color}`}>
      {Math.round(score)}% match
    </span>
  );
}

function JobCard({
  job,
  saved,
  onSave,
  hasResume,
}: {
  job: Job;
  saved: boolean;
  onSave: (id: string | number) => void;
  hasResume: boolean | null;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="bg-app-surface border border-app-border rounded-2xl p-5 hover:border-blue-200 dark:hover:border-blue-800/60 transition-all group"
      data-agent-resource="job"
      data-job-id={job.id}
    >
      <div className="flex items-start justify-between gap-3">
        {/* Company logo placeholder */}
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-100 to-indigo-100 dark:from-blue-950/40 dark:to-indigo-950/40 flex items-center justify-center shrink-0 border border-app-border">
          <Building2 size={17} className="text-blue-500 dark:text-blue-400" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <h3 className="text-sm font-bold text-app-text">{job.title}</h3>
            {hasResume && job.match_score !== undefined && job.match_score !== null && job.match_score > 0 && (
              <MatchBadge score={job.match_score} />
            )}
            {hasResume && job.match_score !== undefined && job.match_score >= 70 && (
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border border-purple-200/60 dark:border-purple-800/40">
                <Target size={10} /> Target Role Match
              </span>
            )}
          </div>
          <p className="text-xs text-app-text-muted font-medium">{job.company}</p>

          <div className="flex flex-wrap items-center gap-3 mt-2 text-[11px] text-app-text-muted">
            {job.role_category && (
              <span className="px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-200/50 dark:border-blue-800/40 text-[10px] font-medium">
                {job.role_category}
              </span>
            )}
            {job.location && (
              <span className="flex items-center gap-1">
                <MapPin size={10} /> {job.location}
              </span>
            )}
            {job.employment_type && (
              <span className="flex items-center gap-1">
                <Clock size={10} /> {job.employment_type}
              </span>
            )}
            {job.salary && (
              <span className="flex items-center gap-1">
                <TrendingUp size={10} /> {job.salary}
              </span>
            )}
          </div>
        </div>

        <button
          onClick={() => onSave(job.id)}
          className="p-2 rounded-lg hover:bg-app-bg transition-colors shrink-0"
          title={saved ? "Unsave" : "Save job"}
        >
          {saved ? (
            <BookmarkCheck size={16} className="text-blue-500" />
          ) : (
            <Bookmark size={16} className="text-app-text-muted group-hover:text-blue-500 transition-colors" />
          )}
        </button>
      </div>

      {/* Skill match breakdown */}
      {(job.matched_skills?.length || job.missing_skills?.length) ? (
        <div className="mt-3 pt-3 border-t border-app-border space-y-2">
          {job.matched_skills && job.matched_skills.length > 0 && (
            <div className="flex flex-wrap gap-1.5 items-center">
              <CheckCircle size={11} className="text-emerald-500 shrink-0" />
              {job.matched_skills.slice(0, 4).map((s) => (
                <span
                  key={s}
                  className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 dark:text-emerald-400"
                >
                  {s}
                </span>
              ))}
            </div>
          )}
          {job.missing_skills && job.missing_skills.length > 0 && (
            <div className="flex flex-wrap gap-1.5 items-center">
              <AlertCircle size={11} className="text-amber-500 shrink-0" />
              {job.missing_skills.slice(0, 3).map((s) => (
                <span
                  key={s}
                  className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400"
                >
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {/* Match explanation */}
      {job.match_explanation && expanded && (
        <div className="mt-3 pt-3 border-t border-app-border">
          <p className="text-xs text-app-text-muted leading-relaxed">{job.match_explanation}</p>
        </div>
      )}

      {/* Actions */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {isValidUrl(job.application_url) && (
          <a
            href={job.application_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-bold hover:bg-blue-700 transition-colors"
          >
            Apply Now <ExternalLink size={11} />
          </a>
        )}
        <Link
          href={`/candidate/resumes?optimize=true&role=${encodeURIComponent(job.title)}`}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-app-border text-xs font-semibold hover:bg-app-bg transition-colors"
        >
          <FileText size={11} /> Optimize Resume
        </Link>
        <Link
          href={`/candidate/interview?role=${encodeURIComponent(job.title)}`}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-app-border text-xs font-semibold hover:bg-app-bg transition-colors"
        >
          <Zap size={11} /> Practice Interview
        </Link>
        {job.match_explanation && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs font-semibold text-app-text-muted hover:text-app-text transition-colors ml-auto"
          >
            {expanded ? "Less" : "Why this match?"}
          </button>
        )}
      </div>
    </div>
  );
}

import { useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";

function JobsContent() {
  const searchParams = useSearchParams();
  const roleParam = searchParams.get("role") || "";
  const queryClient = useQueryClient();
  const { activeResume, primaryDesignation, targetRoles, structuredData, fetchActiveResume } = useResumeStore();

  const getCachedJobs = (key: string): Job[] => {
    if (typeof window !== "undefined") {
      try {
        const cached = localStorage.getItem(key);
        if (cached) {
          const parsed = JSON.parse(cached);
          if (Array.isArray(parsed) && parsed.length > 0) return parsed;
        }
      } catch {}
    }
    return [];
  };

  const {
    data: recommendedJobs = [],
    isLoading: loadingRec,
    refetch: refetchRec,
  } = useQuery<Job[]>({
    queryKey: ["jobs", "recommended"],
    queryFn: async () => {
      try {
        const res = await apiService.getRecommendedJobs();
        const list = Array.isArray(res) ? res : [];
        if (typeof window !== "undefined" && list.length > 0) {
          try { localStorage.setItem("cache_jobs_recommended", JSON.stringify(list)); } catch {}
        }
        return list;
      } catch {
        return getCachedJobs("cache_jobs_recommended");
      }
    },
    initialData: () => getCachedJobs("cache_jobs_recommended"),
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
  });

  const {
    data: allCatalogJobs = [],
    isLoading: loadingCatalog,
    refetch: refetchCatalog,
  } = useQuery<Job[]>({
    queryKey: ["jobs", "catalog"],
    queryFn: async () => {
      try {
        const res = await apiService.getAllJobs();
        const list = Array.isArray(res) ? res : [];
        if (typeof window !== "undefined" && list.length > 0) {
          try { localStorage.setItem("cache_jobs_catalog", JSON.stringify(list)); } catch {}
        }
        return list;
      } catch {
        return getCachedJobs("cache_jobs_catalog");
      }
    },
    initialData: () => getCachedJobs("cache_jobs_catalog"),
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
  });

  const loading = (loadingRec && recommendedJobs.length === 0) && (loadingCatalog && allCatalogJobs.length === 0);
  const [error, setError] = useState<string | null>(null);
  const hasResume = useResumeStore((state) => state.hasResume || Boolean(state.activeResume));

  const [search, setSearch] = useState(roleParam);
  const [locationFilter, setLocationFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("All");
  const [domainFilter, setDomainFilter] = useState("All Domains");
  const [savedJobs, setSavedJobs] = useState<Set<string | number>>(new Set());
  const [activeTab, setActiveTab] = useState<"recommended" | "all" | "saved">("recommended");

  // Show only based on target roles or skills (default true)
  const [onlyTargetRolesAndSkills, setOnlyTargetRolesAndSkills] = useState(true);
  const [selectedTargetRole, setSelectedTargetRole] = useState<string>("All My Roles");
  const [selectedSkill, setSelectedSkill] = useState<string>("All Skills");

  // Extract flat list of candidate skills from structuredData
  const candidateSkills = useMemo(() => {
    if (!structuredData?.skills) return [];
    if (Array.isArray(structuredData.skills)) return structuredData.skills as string[];
    if (typeof structuredData.skills === "object") {
      const all: string[] = [];
      for (const val of Object.values(structuredData.skills)) {
        if (Array.isArray(val)) {
          all.push(...(val as string[]));
        } else if (typeof val === "string") {
          all.push(val);
        }
      }
      return Array.from(new Set(all));
    }
    return [];
  }, [structuredData]);

  const fetchJobs = useCallback(async () => {
    setError(null);
    try {
      await Promise.all([refetchRec(), refetchCatalog()]);
      await fetchActiveResume({ forceRefresh: true });
    } catch {
      setError("Unable to load jobs right now. Please try again.");
    }
  }, [refetchRec, refetchCatalog, fetchActiveResume]);

  useEffect(() => {
    fetchActiveResume();
  }, [fetchActiveResume]);


  const handleSave = (id: string | number) => {
    setSavedJobs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    // TODO: persist to backend
  };

  const isMatchingProfile = useCallback(
    (j: Job, roleFilter: string, skillFilter: string): boolean => {
      const titleLower = j.title.toLowerCase();
      const catLower = (j.role_category || "").toLowerCase();
      const descLower = (j.description || "").toLowerCase();

      // If specific role is selected
      if (roleFilter !== "All My Roles") {
        const words = roleFilter
          .toLowerCase()
          .split(/\s+/)
          .filter((w) => w.length > 2 && !["and", "the", "for", "with"].includes(w));
        const matchesRole = words.some((w) => titleLower.includes(w) || catLower.includes(w));
        if (!matchesRole) return false;
      }

      // If specific skill is selected
      if (skillFilter !== "All Skills") {
        const skLower = skillFilter.toLowerCase();
        const matchesSkill =
          (j.required_skills && j.required_skills.some((s) => s.toLowerCase() === skLower)) ||
          (j.matched_skills && j.matched_skills.some((s) => s.toLowerCase().includes(skLower))) ||
          titleLower.includes(skLower) ||
          descLower.includes(skLower);
        if (!matchesSkill) return false;
      }

      // If backend calculated overall_score >= 50, it passed target role or skill threshold
      if (j.match_score !== undefined && j.match_score !== null && j.match_score >= 50) {
        return true;
      }

      // Check against candidate target roles
      if (targetRoles && targetRoles.length > 0) {
        const matchesAnyRole = targetRoles.some((tr) => {
          const words = tr
            .toLowerCase()
            .split(/\s+/)
            .filter((w) => w.length > 2 && !["and", "the", "for", "with"].includes(w));
          return words.some((w) => titleLower.includes(w) || catLower.includes(w));
        });
        if (matchesAnyRole) return true;
      }

      // Check against candidate primary designation
      if (primaryDesignation) {
        const words = primaryDesignation
          .toLowerCase()
          .split(/\s+/)
          .filter((w) => w.length > 2 && !["and", "the", "for", "with"].includes(w));
        if (words.some((w) => titleLower.includes(w) || catLower.includes(w))) return true;
      }

      // Check against candidate skills
      if (candidateSkills.length > 0) {
        const candSet = new Set(candidateSkills.map((s) => s.toLowerCase()));
        if (j.required_skills && j.required_skills.some((rs) => candSet.has(rs.toLowerCase()))) {
          return true;
        }
        if (j.matched_skills && j.matched_skills.length > 0) {
          return true;
        }
      }

      return false;
    },
    [targetRoles, primaryDesignation, candidateSkills]
  );

  const currentFeedJobs = activeTab === "recommended" ? recommendedJobs : allCatalogJobs;

  const filteredJobs = useMemo(() => {
    return currentFeedJobs.filter((j) => {
      const matchesSearch =
        !search ||
        j.title.toLowerCase().includes(search.toLowerCase()) ||
        j.company.toLowerCase().includes(search.toLowerCase());
      const matchesLocation =
        !locationFilter ||
        (j.location || "").toLowerCase().includes(locationFilter.toLowerCase());
      const matchesType =
        typeFilter === "All" ||
        (j.employment_type && j.employment_type.toLowerCase() === typeFilter.toLowerCase()) ||
        (typeFilter === "Remote" && (
          (j.employment_type && j.employment_type.toLowerCase() === "remote") ||
          (j.location && j.location.toLowerCase().includes("remote"))
        ));
      const matchesDomain =
        domainFilter === "All Domains" ||
        (j.role_category && j.role_category.toLowerCase() === domainFilter.toLowerCase());

      const shouldFilterByProfile =
        activeTab === "all"
          ? (onlyTargetRolesAndSkills ? isMatchingProfile(j, selectedTargetRole, selectedSkill) : true)
          : true;

      return matchesSearch && matchesLocation && matchesType && matchesDomain && shouldFilterByProfile;
    });
  }, [
    currentFeedJobs,
    search,
    locationFilter,
    typeFilter,
    domainFilter,
    onlyTargetRolesAndSkills,
    activeTab,
    selectedTargetRole,
    selectedSkill,
    isMatchingProfile,
  ]);

  const displayJobs =
    activeTab === "saved"
      ? (recommendedJobs.concat(allCatalogJobs)).filter((j, idx, arr) => arr.findIndex(x => x.id === j.id) === idx && savedJobs.has(j.id))
      : filteredJobs;

  return (
    <div className="min-h-screen bg-app-bg text-app-text font-sans">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-8 space-y-6">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-app-text">Jobs</h1>
            <p className="text-sm text-app-text-muted mt-0.5">
              Personalized matches based on your active resume and generated target roles
            </p>
          </div>
          <button
            onClick={fetchJobs}
            className="flex items-center gap-2 px-4 py-2 rounded-xl border border-app-border text-sm font-medium text-app-text-muted hover:text-app-text hover:bg-app-surface transition-colors self-start"
          >
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>

        {/* Active Resume Context Indicator */}
        {activeResume ? (
          <div className="bg-blue-50 dark:bg-blue-950/30 border border-blue-200/60 dark:border-blue-800/40 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3 shadow-xs">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-blue-600/10 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0">
                <FileText size={16} />
              </div>
              <div>
                <p className="text-xs font-semibold text-blue-900 dark:text-blue-200">
                  Using your active resume: <span className="font-bold text-blue-600 dark:text-blue-400">{activeResume.title || activeResume.file_name}</span>
                </p>
                <p className="text-[11px] text-blue-700/80 dark:text-blue-300/70">
                  Primary Designation: <strong className="text-blue-900 dark:text-blue-200">{primaryDesignation || "Extracting..."}</strong>
                  {targetRoles && targetRoles.length > 0 && ` • Target Roles: ${targetRoles.slice(0, 3).join(", ")}`}
                </p>
              </div>
            </div>
            <span className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300">
              Single Active Context
            </span>
          </div>
        ) : hasResume === false && (
          <div className="bg-amber-50 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-800/40 rounded-2xl p-4 flex items-center gap-3">
            <AlertCircle size={18} className="text-amber-500 shrink-0" />
            <p className="text-sm text-amber-700 dark:text-amber-400">
              Upload your resume to get personalized job matches with skill scores.{" "}
              <Link href="/candidate/resumes/upload" className="font-semibold underline">
                Upload Resume →
              </Link>
            </p>
          </div>
        )}

        {/* Target Roles & Skills Strict Matching Bar */}
        {(activeResume || (targetRoles && targetRoles.length > 0) || candidateSkills.length > 0) && (
          <div className="bg-app-surface border border-app-border rounded-2xl p-4 sm:p-5 shadow-xs space-y-3.5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-app-border">
              <div className="flex items-center gap-2.5">
                <div
                  className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                    onlyTargetRolesAndSkills
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                      : "bg-app-bg text-app-text-muted"
                  }`}
                >
                  <Target size={16} />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-xs font-bold uppercase tracking-wider text-app-text">
                      Target Roles & Skills Filter
                    </h2>
                    <span
                      className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                        onlyTargetRolesAndSkills
                          ? "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300"
                          : "bg-app-bg text-app-text-muted border border-app-border"
                      }`}
                    >
                      {onlyTargetRolesAndSkills ? "Active — Filtered" : "All Jobs Shown"}
                    </span>
                  </div>
                  <p className="text-[11px] text-app-text-muted mt-0.5">
                    {onlyTargetRolesAndSkills
                      ? `Displaying strictly jobs matching your target roles (${targetRoles.slice(0, 3).join(", ") || primaryDesignation}) or verified skills.`
                      : "Showing all available jobs in the database (including non-matching domains)."}
                  </p>
                </div>
              </div>

              {/* Toggle Button */}
              <button
                type="button"
                onClick={() => setOnlyTargetRolesAndSkills((prev) => !prev)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all shrink-0 self-start sm:self-center border ${
                  onlyTargetRolesAndSkills
                    ? "bg-emerald-600 text-white border-emerald-600 hover:bg-emerald-700 shadow-xs"
                    : "bg-app-bg text-app-text border-app-border hover:bg-app-surface hover:border-emerald-500/40"
                }`}
              >
                {onlyTargetRolesAndSkills ? (
                  <>
                    <Check size={13} />
                    Only My Roles & Skills
                  </>
                ) : (
                  <>
                    <Sparkles size={13} className="text-amber-500" />
                    Show All Jobs
                  </>
                )}
              </button>
            </div>

            {/* Target Role Pills and Skill Selector */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-0.5">
              {/* Role Pills */}
              {targetRoles && targetRoles.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] font-semibold text-app-text-muted mr-1">Role:</span>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedTargetRole("All My Roles");
                      setOnlyTargetRolesAndSkills(true);
                    }}
                    className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-all ${
                      selectedTargetRole === "All My Roles" && onlyTargetRolesAndSkills
                        ? "bg-blue-600 text-white shadow-xs"
                        : "bg-app-bg text-app-text-muted hover:text-app-text hover:bg-app-border/40"
                    }`}
                  >
                    All My Roles
                  </button>
                  {targetRoles.map((role) => (
                    <button
                      type="button"
                      key={role}
                      onClick={() => {
                        setSelectedTargetRole(role);
                        setOnlyTargetRolesAndSkills(true);
                      }}
                      className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-all ${
                        selectedTargetRole === role && onlyTargetRolesAndSkills
                          ? "bg-blue-600 text-white shadow-xs"
                          : "bg-app-bg text-app-text-muted hover:text-app-text hover:bg-app-border/40"
                      }`}
                    >
                      {role}
                    </button>
                  ))}
                </div>
              )}

              {/* Skill Dropdown */}
              {candidateSkills.length > 0 && (
                <div className="flex items-center gap-2 ml-auto">
                  <span className="text-[11px] font-semibold text-app-text-muted">Skill:</span>
                  <select
                    value={selectedSkill}
                    onChange={(e) => {
                      setSelectedSkill(e.target.value);
                      setOnlyTargetRolesAndSkills(true);
                    }}
                    className="px-2.5 py-1 rounded-lg border border-app-border bg-app-bg text-xs text-app-text focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-all font-medium"
                  >
                    <option value="All Skills">All Skills ({candidateSkills.length})</option>
                    {candidateSkills.slice(0, 25).map((skill) => (
                      <option key={skill} value={skill}>
                        {skill}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Search + Filters */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-app-text-muted" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by role or company…"
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-app-border bg-app-surface text-sm text-app-text placeholder:text-app-text-muted focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-all"
            />
          </div>
          <div className="relative">
            <MapPin size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-app-text-muted" />
            <input
              type="text"
              value={locationFilter}
              onChange={(e) => setLocationFilter(e.target.value)}
              placeholder="Location…"
              className="w-full sm:w-40 pl-9 pr-3 py-2.5 rounded-xl border border-app-border bg-app-surface text-sm text-app-text placeholder:text-app-text-muted focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-all"
            />
          </div>
          <select
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            className="px-3 py-2.5 rounded-xl border border-app-border bg-app-surface text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-all"
          >
            {["All", "Full-time", "Part-time", "Remote", "Contract", "Internship"].map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <select
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            className="px-3 py-2.5 rounded-xl border border-app-border bg-app-surface text-sm text-app-text focus:outline-none focus:ring-2 focus:ring-blue-500/40 transition-all"
          >
            {[
              "All Domains",
              "AI/ML",
              "Backend Engineering",
              "Finance & Banking",
              "Consulting & Strategy",
              "Design & Creative",
              "Marketing & Growth",
              "Human Resources",
              "Sales & Business Dev",
              "Operations & Logistics",
              "Healthcare & Life Sciences",
            ].map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-app-border gap-6">
          {(["recommended", "all", "saved"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-2.5 text-sm font-semibold border-b-2 transition-all capitalize ${
                activeTab === tab
                  ? "border-blue-600 text-blue-600 dark:border-blue-400 dark:text-blue-400"
                  : "border-transparent text-app-text-muted hover:text-app-text"
              }`}
            >
              {tab === "recommended" ? "Recommended For You" : tab === "all" ? "All Jobs" : `Saved (${savedJobs.size})`}
            </button>
          ))}
        </div>

        {/* Jobs List */}
        {loading && displayJobs.length === 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 animate-pulse">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="bg-app-surface border border-app-border rounded-2xl p-5 space-y-3">
                <div className="h-5 w-48 bg-gray-200 dark:bg-gray-800 rounded" />
                <div className="h-4 w-32 bg-gray-200 dark:bg-gray-800 rounded" />
                <div className="h-10 w-full bg-gray-100 dark:bg-gray-850 rounded-xl" />
              </div>
            ))}
          </div>
        ) : error && displayJobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            <AlertCircle size={32} className="text-red-400" />
            <p className="text-sm text-app-text-muted">{error}</p>
            <button
              onClick={fetchJobs}
              className="px-4 py-2 rounded-xl bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 transition-colors"
            >
              Try Again
            </button>
          </div>
        ) : displayJobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3.5 text-center bg-app-surface border border-app-border rounded-2xl p-8">
            <div className="w-12 h-12 rounded-2xl bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 flex items-center justify-center">
              <Target size={24} />
            </div>
            <p className="text-base font-bold text-app-text">
              {activeTab === "saved"
                ? "No saved jobs yet"
                : activeTab === "recommended"
                ? "No strong job matches found right now."
                : "No jobs match your search criteria"}
            </p>
            <p className="text-xs text-app-text-muted max-w-md leading-relaxed">
              {activeTab === "saved"
                ? "Bookmark jobs to save them here."
                : activeTab === "recommended"
                ? "We only recommend jobs that achieve a 65%+ match score with your active resume, verified skills, and target roles without domain mismatches."
                : "Try adjusting your search query, location, or domain filters."}
            </p>
            {activeTab === "recommended" ? (
              <div className="flex flex-wrap items-center justify-center gap-2.5 mt-2">
                <button
                  type="button"
                  onClick={fetchJobs}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-bold hover:bg-blue-700 transition-colors shadow-xs"
                >
                  <RefreshCw size={12} /> Refresh Recommendations
                </button>
                <Link
                  href="/candidate/resumes"
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-app-border text-xs font-semibold text-app-text hover:bg-app-bg transition-colors"
                >
                  <FileText size={12} /> Update Target Roles
                </Link>
                <Link
                  href="/candidate/learning"
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-app-border text-xs font-semibold text-app-text hover:bg-app-bg transition-colors"
                >
                  <Zap size={12} /> Start Learning Skills
                </Link>
                <button
                  type="button"
                  onClick={() => setActiveTab("all")}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl border border-blue-200/80 dark:border-blue-800/60 text-blue-600 dark:text-blue-400 text-xs font-semibold hover:bg-blue-50 dark:hover:bg-blue-950/30 transition-colors"
                >
                  Browse All Jobs →
                </button>
              </div>
            ) : !hasResume ? (
              <Link
                href="/candidate/resumes/upload"
                className="mt-2 flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 text-white text-xs font-bold hover:bg-blue-700 transition-colors"
              >
                <FileText size={14} /> Upload Resume
              </Link>
            ) : null}
          </div>
        ) : (
          <div className="space-y-4">
            {displayJobs.map((job) => (
              <JobCard
                key={job.id}
                job={job}
                saved={savedJobs.has(job.id)}
                onSave={handleSave}
                hasResume={hasResume}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function JobsPage() {
  return (
    <Suspense fallback={null}>
      <JobsContent />
    </Suspense>
  );
}
