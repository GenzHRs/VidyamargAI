"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { 
  Upload, FilePlus2, FileEdit, Sparkles, Download, 
  Trash2, Eye, RefreshCw, FileText, Search, Filter, 
  CheckCircle2, Clock, AlertCircle, ArrowRight, ExternalLink,
  Layers, ShieldCheck, Terminal
} from "lucide-react";
import { resumeCenterApi, ResumeItem } from "@/services/resumeCenterApi";
import { useResumeStore } from "@/store/resumeStore";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import { Alert } from "@/components/ui/Alert";
import { EmptyState } from "@/components/ui/EmptyState";

const getInitialResumes = (): ResumeItem[] => {
  if (typeof window !== "undefined") {
    try {
      const cached = localStorage.getItem("cache_candidate_resumes");
      if (cached) {
        const parsed = JSON.parse(cached);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {}

    const storeActive = useResumeStore.getState().activeResume;
    if (storeActive) {
      return [{
        id: storeActive.id,
        title: storeActive.title || "Master Resume",
        source_type: storeActive.source_type || "uploaded",
        version_number: 1,
        is_active: true,
        status: storeActive.status || "active",
        created_at: storeActive.created_at || new Date().toISOString(),
        updated_at: storeActive.updated_at || new Date().toISOString(),
      }];
    }
  }
  return [];
};

export default function ResumeCenterDashboard() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const {
    activeResume,
    primaryDesignation,
    targetRoles,
    fetchActiveResume,
    replaceResume,
    isLoading: isStoreLoading
  } = useResumeStore();

  const {
    data: resumes = [],
    isLoading: isQueryLoading,
    isFetching,
    isError,
    error: queryError,
    refetch: refetchResumes,
  } = useQuery<ResumeItem[]>({
    queryKey: ["candidate", "resumes"],
    queryFn: async ({ signal }) => {
      const list = await resumeCenterApi.getResumes(undefined, undefined, signal);
      if (Array.isArray(list) && typeof window !== "undefined") {
        try {
          localStorage.setItem("cache_candidate_resumes", JSON.stringify(list));
        } catch {}
      }
      return list;
    },
    initialData: () => getInitialResumes(),
    placeholderData: keepPreviousData,
    staleTime: 60 * 1000,
  });

  type ResumePageState = "initial" | "loading" | "success" | "empty" | "error";

  const pageState: ResumePageState = useMemo(() => {
    if (isError && resumes.length === 0) {
      return "error";
    }
    if (isQueryLoading && resumes.length === 0) {
      return "loading";
    }
    if (!isQueryLoading && !isError && resumes.length === 0) {
      return "empty";
    }
    if (resumes.length > 0) {
      return "success";
    }
    return "initial";
  }, [isQueryLoading, isError, resumes.length]);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [compilingId, setCompilingId] = useState<number | null>(null);
  const [isReplacing, setIsReplacing] = useState(false);

  // Delete modal state
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [resumeToDelete, setResumeToDelete] = useState<ResumeItem | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const fetchResumes = async () => {
    try {
      setErrorMessage("");
      await refetchResumes();
      await fetchActiveResume({ forceRefresh: true });
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load resumes");
    }
  };

  useEffect(() => {
    fetchActiveResume();
  }, [fetchActiveResume]);


  const handleReplaceFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsReplacing(true);
    setErrorMessage("");
    setSuccessMessage("");
    try {
      const res = await replaceResume(file);
      if (res.success) {
        setSuccessMessage(res.message);
        await fetchResumes();
      } else {
        setErrorMessage(res.message);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to replace active resume");
    } finally {
      setIsReplacing(false);
      e.target.value = "";
    }
  };

  const latestResumeId = resumes.length > 0 ? resumes[0].id : null;

  // Filtered resumes
  const filteredResumes = useMemo(() => {
    return resumes.filter((r) => {
      const matchesSearch =
        r.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (r.template_name && r.template_name.toLowerCase().includes(searchQuery.toLowerCase())) ||
        r.source_type.toLowerCase().includes(searchQuery.toLowerCase());
      
      let matchesStatus = true;
      if (statusFilter === "active") {
        matchesStatus = Boolean(r.is_active || r.status?.toLowerCase() === "active");
      } else if (statusFilter === "tailored") {
        matchesStatus = r.source_type === "tailored" || r.status?.toLowerCase() === "tailored";
      } else if (statusFilter === "compiled") {
        matchesStatus = Boolean(r.latest_pdf_url) || r.status?.toLowerCase() === "compiled";
      } else if (statusFilter === "archived") {
        matchesStatus = r.status?.toLowerCase() === "archived";
      } else if (statusFilter === "draft") {
        const isAct = Boolean(r.is_active || r.status?.toLowerCase() === "active");
        const isComp = Boolean(r.latest_pdf_url) || r.status?.toLowerCase() === "compiled";
        const isTail = r.source_type === "tailored" || r.status?.toLowerCase() === "tailored";
        matchesStatus = !isAct && !isComp && !isTail && r.status?.toLowerCase() !== "archived";
      }

      return matchesSearch && matchesStatus;
    });
  }, [resumes, searchQuery, statusFilter]);

  // Actions
  const handleCompile = async (id: number) => {
    try {
      setCompilingId(id);
      setErrorMessage("");
      const result = await resumeCenterApi.compileResume(id);
      if (result.latex_available) {
        setSuccessMessage("Resume compiled to PDF successfully!");
      } else {
        setSuccessMessage("LaTeX source generated successfully. (PDF compilation ready for export)");
      }
      setTimeout(() => setSuccessMessage(""), 4000);
      await fetchResumes();
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to compile resume");
    } finally {
      setCompilingId(null);
    }
  };

  const handleDownloadPdf = async (resume: ResumeItem) => {
    try {
      setErrorMessage("");
      const blob = await resumeCenterApi.downloadPdfBlob(resume.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${resume.title.replace(/[^a-zA-Z0-9_-]/g, "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setErrorMessage(err.message || "PDF download failed. Try compiling the resume first.");
    }
  };

  const handleDownloadLatex = async (resume: ResumeItem) => {
    try {
      setErrorMessage("");
      const texContent = await resumeCenterApi.downloadLatexText(resume.id);
      const blob = new Blob([texContent], { type: "text/x-tex;charset=utf-8" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${resume.title.replace(/[^a-zA-Z0-9_-]/g, "_")}.tex`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setErrorMessage(err.message || "LaTeX download failed");
    }
  };

  const confirmDelete = async () => {
    if (!resumeToDelete) return;
    try {
      setIsDeleting(true);
      await resumeCenterApi.deleteResume(resumeToDelete.id);
      setSuccessMessage(`Deleted "${resumeToDelete.title}"`);
      setTimeout(() => setSuccessMessage(""), 3000);
      setDeleteModalOpen(false);
      setResumeToDelete(null);
      await fetchResumes();
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to delete resume");
    } finally {
      setIsDeleting(false);
    }
  };

  const getStatusBadge = (resume: ResumeItem) => {
    const s = (resume.status || "").toUpperCase();
    const isAct = Boolean(resume.is_active || s === "ACTIVE");

    if (isAct) {
      if (resume.source_type === "tailored") {
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300 border border-purple-200 dark:border-purple-800">
            <Sparkles size={12} />
            Active • Tailored
          </span>
        );
      }
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
          <CheckCircle2 size={12} />
          Active
        </span>
      );
    }

    if (resume.source_type === "tailored" || s === "TAILORED") {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300 border border-purple-200 dark:border-purple-800">
          <Sparkles size={12} />
          JD Tailored
        </span>
      );
    }

    if (s === "COMPILED" || resume.latest_pdf_url) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
          <FileText size={12} />
          Compiled
        </span>
      );
    }

    if (s === "ARCHIVED") {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border border-slate-200 dark:border-slate-700">
          Archived
        </span>
      );
    }

    if (s === "VERIFIED" || resume.is_verified) {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
          <CheckCircle2 size={12} />
          Verified
        </span>
      );
    }

    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
        <Clock size={12} />
        Draft
      </span>
    );
  };

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8 font-sans">
      {/* Notifications */}
      {successMessage && (
        <Alert variant="success" className="animate-in fade-in slide-in-from-top-2">
          {successMessage}
        </Alert>
      )}
      {errorMessage && (
        <Alert variant="error" className="animate-in fade-in slide-in-from-top-2">
          {errorMessage}
        </Alert>
      )}
      {isError && resumes.length > 0 && (
        <Alert variant="warning" className="flex items-center justify-between animate-in fade-in slide-in-from-top-2">
          <span>Unable to sync latest resume updates: {(queryError as Error)?.message || "Service unavailable"}. Showing cached data.</span>
          <Button size="sm" variant="outline" onClick={() => refetchResumes()} className="text-xs ml-4">
            Retry Sync
          </Button>
        </Alert>
      )}

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-gray-200 dark:border-gray-800 pb-5">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-app-text">Resume</h1>
          <p className="text-xs text-app-text-muted mt-1 leading-normal">
            Manage your single active resume, ATS analysis, versions, and LaTeX templates.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/candidate/resumes/templates">
            <Button variant="outline" className="text-xs font-semibold">
              <Layers size={15} className="mr-1.5" />
              <span>Browse 15 Templates</span>
            </Button>
          </Link>
          <Link href="/candidate/resumes/new" data-agent-action="create-resume">
            <Button className="bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs shadow-sm">
              <FilePlus2 size={15} className="mr-1.5" />
              <span>Create New Resume</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* SINGLE ACTIVE RESUME CARD */}
      <Card className="p-6 md:p-8 bg-gradient-to-r from-slate-900/90 via-blue-950/80 to-slate-900/90 border border-blue-500/30 text-white shadow-xl rounded-3xl relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-4 max-w-3xl">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className="bg-emerald-500/20 text-emerald-300 border-emerald-500/40 text-xs px-3 py-1 font-bold">
                <CheckCircle2 size={13} className="mr-1.5 inline" /> CURRENT ACTIVE RESUME
              </Badge>
              <span className="text-xs text-blue-200/70">
                Used globally across Jobs, AI Agent, AI Mentor, Interview & Profile
              </span>
            </div>

            {activeResume ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-500/20 flex items-center justify-center text-blue-400 border border-blue-400/30">
                    <FileText size={22} />
                  </div>
                  <div>
                    <h3 className="text-xl font-bold text-white tracking-tight">
                      {activeResume.title || activeResume.file_name || "Active Resume"}
                    </h3>
                    <p className="text-xs text-blue-200/70">
                      Filename: {activeResume.file_name || "resume.pdf"}
                    </p>
                  </div>
                </div>

                {/* Primary Designation & Target Roles */}
                <div className="pt-2 space-y-2 border-t border-blue-500/20">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-semibold text-blue-300">Primary Designation:</span>
                    <span className="text-sm font-bold text-white px-2.5 py-0.5 rounded-lg bg-blue-500/20 border border-blue-400/30">
                      {primaryDesignation || "Extracting Designation..."}
                    </span>
                  </div>

                  {targetRoles && targetRoles.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 pt-1">
                      <span className="text-xs font-semibold text-blue-300 mr-1">Target Roles:</span>
                      {targetRoles.map((role, idx) => (
                        <span key={idx} className="text-xs px-2.5 py-0.5 rounded-md bg-slate-800/80 text-blue-200 border border-slate-700 font-medium">
                          {role}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="space-y-1">
                <h3 className="text-lg font-bold text-white">No Active Resume Uploaded Yet</h3>
                <p className="text-xs text-blue-200/70">
                  Upload your resume to generate your primary designation, target roles, and enable AI job matching.
                </p>
              </div>
            )}
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 shrink-0">
            <label className="cursor-pointer">
              <input
                type="file"
                accept=".pdf,.docx,.doc,.txt,.tex"
                onChange={handleReplaceFileChange}
                className="hidden"
                disabled={isReplacing}
              />
              <span className="inline-flex items-center justify-center w-full sm:w-auto bg-blue-600 hover:bg-blue-500 text-white font-semibold shadow-lg shadow-blue-600/30 text-xs py-2.5 px-4 rounded-xl transition-all">
                <RefreshCw size={14} className={`mr-2 ${isReplacing ? "animate-spin" : ""}`} />
                {isReplacing ? "Processing New Resume..." : "Replace Active Resume"}
              </span>
            </label>

            {activeResume && (
              <Link href={`/candidate/resumes/edit/${activeResume.id}`}>
                <Button variant="outline" className="w-full sm:w-auto bg-white/10 hover:bg-white/20 text-white border-white/20 text-xs py-2.5 px-4">
                  <Eye size={14} className="mr-2" /> View Active Resume
                </Button>
              </Link>
            )}
          </div>
        </div>
      </Card>

      {/* EXACTLY FOUR PROFESSIONAL CARDS */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-bold text-app-text tracking-tight">Core Resume Workflows</h2>
          <span className="text-xs text-app-text-muted font-medium">Select a workflow to begin</span>
        </div>

        <div className="grid cq-grid-4col gap-4 sm:gap-6">
          {/* Card 1: Upload Resume */}
          <Card className="flex flex-col justify-between p-6 bg-app-card border-app-border hover:border-blue-500/50 hover:shadow-lg transition-all duration-200 group">
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 flex items-center justify-center border border-blue-200/50 dark:border-blue-800/30 group-hover:scale-105 transition-transform">
                <Upload size={24} />
              </div>
              <div className="space-y-1.5">
                <h3 className="text-lg font-bold text-app-text group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                  1. Upload Resume
                </h3>
                <p className="text-xs text-app-text-muted leading-relaxed">
                  Upload PDF, Word (DOCX), TXT, or TeX. Magic-byte validated, 10MB limit, parsed into editable sections while preserving your original file.
                </p>
              </div>
            </div>
            <div className="pt-6 mt-4 border-t border-app-border/60">
              <Link href="/candidate/resumes/upload" className="w-full" data-agent-action="upload-resume">
                <Button className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs py-2.5">
                  Upload Resume
                  <ArrowRight size={14} className="ml-1.5" />
                </Button>
              </Link>
            </div>
          </Card>

          {/* Card 2: Create New Resume */}
          <Card className="flex flex-col justify-between p-6 bg-app-card border-app-border hover:border-indigo-500/50 hover:shadow-lg transition-all duration-200 group">
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-400 flex items-center justify-center border border-indigo-200/50 dark:border-indigo-800/30 group-hover:scale-105 transition-transform">
                <FilePlus2 size={24} />
              </div>
              <div className="space-y-1.5">
                <h3 className="text-lg font-bold text-app-text group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                  2. Create New Resume
                </h3>
                <p className="text-xs text-app-text-muted leading-relaxed">
                  Start from scratch or select from 15 Overleaf LaTeX templates (Software, Data, Business, Academic, Minimal) with 88%–99% ATS ratings.
                </p>
              </div>
            </div>
            <div className="pt-6 mt-4 border-t border-app-border/60">
              <Link href="/candidate/resumes/new" className="w-full">
                <Button className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs py-2.5">
                  Create New Resume
                  <ArrowRight size={14} className="ml-1.5" />
                </Button>
              </Link>
            </div>
          </Card>

          {/* Card 3: Edit Existing Resume */}
          <Card className="flex flex-col justify-between p-6 bg-app-card border-app-border hover:border-emerald-500/50 hover:shadow-lg transition-all duration-200 group">
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 flex items-center justify-center border border-emerald-200/50 dark:border-emerald-800/30 group-hover:scale-105 transition-transform">
                <FileEdit size={24} />
              </div>
              <div className="space-y-1.5">
                <h3 className="text-lg font-bold text-app-text group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                  3. Edit Existing Resume
                </h3>
                <p className="text-xs text-app-text-muted leading-relaxed">
                  Two-panel live editor with form on left, live PDF/LaTeX preview on right, version history drawer, diff tracking, and one-click compile.
                </p>
              </div>
            </div>
            <div className="pt-6 mt-4 border-t border-app-border/60">
              {latestResumeId ? (
                <Link href={`/candidate/resumes/edit/${latestResumeId}`} className="w-full">
                  <Button className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs py-2.5">
                    Open Latest Resume
                    <ArrowRight size={14} className="ml-1.5" />
                  </Button>
                </Link>
              ) : (
                <Button 
                  onClick={() => router.push("/candidate/resumes/upload")}
                  className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs py-2.5"
                >
                  Upload First Resume
                  <ArrowRight size={14} className="ml-1.5" />
                </Button>
              )}
            </div>
          </Card>

          {/* Card 4: JD-Based Resume Update */}
          <Card className="flex flex-col justify-between p-6 bg-app-card border-app-border hover:border-purple-500/50 hover:shadow-lg transition-all duration-200 group">
            <div className="space-y-4">
              <div className="w-12 h-12 rounded-2xl bg-purple-50 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400 flex items-center justify-center border border-purple-200/50 dark:border-purple-800/30 group-hover:scale-105 transition-transform">
                <Sparkles size={24} />
              </div>
              <div className="space-y-1.5">
                <h3 className="text-lg font-bold text-app-text group-hover:text-purple-600 dark:group-hover:text-purple-400 transition-colors">
                  4. JD-Based Resume Update
                </h3>
                <p className="text-xs text-app-text-muted leading-relaxed">
                  Target a job description. Identifies matched vs missing skills, generates tailored content with strict anti-hallucination checks and side-by-side review.
                </p>
              </div>
            </div>
            <div className="pt-6 mt-4 border-t border-app-border/60">
              {latestResumeId ? (
                <Link href={`/candidate/resumes/tailor/${latestResumeId}`} className="w-full">
                  <Button className="w-full bg-purple-600 hover:bg-purple-700 text-white font-semibold text-xs py-2.5">
                    Tailor for JD
                    <ArrowRight size={14} className="ml-1.5" />
                  </Button>
                </Link>
              ) : (
                <Button 
                  onClick={() => router.push("/candidate/resumes/upload")}
                  className="w-full bg-purple-600 hover:bg-purple-700 text-white font-semibold text-xs py-2.5"
                >
                  Upload Resume First
                  <ArrowRight size={14} className="ml-1.5" />
                </Button>
              )}
            </div>
          </Card>
        </div>
      </section>

      {/* Candidate Resumes Table / Card List */}
      <section className="space-y-4 pt-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-app-text tracking-tight">Your Resumes & Versions</h2>
            <p className="text-xs text-app-text-muted mt-0.5">
              Manage all uploaded, drafted, compiled, and JD-tailored resumes in private storage.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {/* Search Input */}
            <div className="relative">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-app-text-muted" />
              <input
                type="text"
                placeholder="Search resumes..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-3 py-1.5 text-xs rounded-xl border border-app-border bg-app-surface text-app-text focus:outline-none focus:ring-2 focus:ring-blue-500 w-48 sm:w-60"
              />
            </div>

            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="py-1.5 px-3 text-xs rounded-xl border border-app-border bg-app-surface text-app-text focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Statuses</option>
              <option value="active">Active</option>
              <option value="compiled">Compiled</option>
              <option value="tailored">JD Tailored</option>
              <option value="archived">Archived</option>
              <option value="draft">Draft</option>
            </select>

            <Button
              variant="outline"
              size="sm"
              onClick={fetchResumes}
              className="text-xs"
              title="Refresh"
            >
              <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
            </Button>
          </div>
        </div>

        {pageState === "loading" ? (
          <div className="p-12 text-center text-app-text-muted space-y-3 bg-app-card rounded-2xl border border-app-border">
            <RefreshCw size={24} className="animate-spin mx-auto text-blue-600" />
            <p className="text-xs font-semibold">Connecting to secure resume repository...</p>
          </div>
        ) : pageState === "error" ? (
          <div className="p-8 text-center bg-red-500/10 border border-red-500/30 rounded-2xl space-y-3">
            <AlertCircle className="w-10 h-10 text-red-500 mx-auto" />
            <h3 className="text-sm font-bold text-app-text">Unable to Load Resumes</h3>
            <p className="text-xs text-app-text-muted max-w-md mx-auto">
              {(queryError as Error)?.message || errorMessage || "The resume service is currently unreachable. Please check your connection."}
            </p>
            <div className="flex justify-center gap-3 pt-2">
              <Button
                onClick={() => {
                  setErrorMessage("");
                  refetchResumes();
                }}
                className="bg-blue-600 hover:bg-blue-500 text-white text-xs"
              >
                <RefreshCw size={13} className="mr-1.5" />
                Retry
              </Button>
              <Link href="/candidate/resumes/upload">
                <Button variant="outline" className="text-xs">
                  <Upload size={13} className="mr-1.5" />
                  Upload New Resume
                </Button>
              </Link>
            </div>
          </div>
        ) : pageState === "empty" ? (
          <EmptyState
            title="No resumes yet"
            description="Upload your current resume or create a fresh one using an ATS-optimized Overleaf LaTeX template."
            icon={<FileText size={36} className="text-blue-500" />}
            action={
              <div className="flex flex-wrap gap-3 mt-4">
                <Link href="/candidate/resumes/upload">
                  <Button className="bg-blue-600 hover:bg-blue-700 text-white text-xs">
                    <Upload size={14} className="mr-1.5" />
                    Upload Existing Resume
                  </Button>
                </Link>
                <Link href="/candidate/resumes/templates">
                  <Button variant="outline" className="text-xs">
                    <Layers size={14} className="mr-1.5" />
                    Browse Templates
                  </Button>
                </Link>
              </div>
            }
          />
        ) : filteredResumes.length === 0 ? (
          <EmptyState
            title="No matching resumes found"
            description="Try adjusting your search query or status filter."
            icon={<FileText size={36} className="text-blue-500" />}
          />
        ) : (
          <div className="overflow-hidden rounded-2xl border border-app-border bg-app-card shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-app-text">
                <thead className="bg-app-surface/60 border-b border-app-border text-app-text-muted uppercase text-[10px] tracking-wider font-bold">
                  <tr>
                    <th className="py-3.5 px-4">Resume Title & Version</th>
                    <th className="py-3.5 px-4">Source & Template</th>
                    <th className="py-3.5 px-4">Status</th>
                    <th className="py-3.5 px-4">Last Updated</th>
                    <th className="py-3.5 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-app-border/60">
                  {filteredResumes.map((resume) => (
                    <tr 
                      key={resume.id}
                      data-agent-resource="resume"
                      data-resume-id={resume.id}
                      className="hover:bg-app-surface/40 transition-colors group"
                    >
                      <td className="py-4 px-4 font-semibold">
                        <div className="flex items-center gap-2.5">
                          <div className="w-8 h-8 rounded-lg bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0 border border-blue-200/50 dark:border-blue-800/30">
                            <FileText size={16} />
                          </div>
                          <div>
                            <Link 
                              href={`/candidate/resumes/edit/${resume.id}`}
                              className="font-bold text-app-text hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                            >
                              {resume.title}
                            </Link>
                            <div className="flex items-center gap-2 mt-0.5 text-[11px] text-app-text-muted">
                              <span className="font-mono bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded text-[10px]">
                                v{resume.version_number}
                              </span>
                              {resume.change_summary && (
                                <span className="truncate max-w-[200px]" title={resume.change_summary}>
                                  • {resume.change_summary}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="py-4 px-4">
                        <div className="space-y-1">
                          <span className="font-medium text-app-text block">
                            {resume.template_name || "ATS Classic"}
                          </span>
                          <span className="text-[10px] text-app-text-muted capitalize">
                            Source: {resume.source_type.replace(/_/g, " ")}
                          </span>
                        </div>
                      </td>
                      <td className="py-4 px-4">
                        {getStatusBadge(resume)}
                      </td>
                      <td className="py-4 px-4 text-app-text-muted">
                        {resume.updated_at 
                          ? new Date(resume.updated_at).toLocaleDateString(undefined, {
                              year: "numeric",
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit"
                            })
                          : "Recently"}
                      </td>
                      <td className="py-4 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {/* Compile Button */}
                          <button
                            onClick={() => handleCompile(resume.id)}
                            disabled={compilingId === resume.id}
                            className="p-1.5 rounded-lg text-app-text-muted hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950/30 transition-colors"
                            title="Compile LaTeX & PDF"
                          >
                            <Terminal size={15} className={compilingId === resume.id ? "animate-spin text-blue-600" : ""} />
                          </button>

                          {/* Edit Button */}
                          <Link
                            href={`/candidate/resumes/edit/${resume.id}`}
                            className="p-1.5 rounded-lg text-app-text-muted hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 transition-colors"
                            title="Edit Resume"
                          >
                            <FileEdit size={15} />
                          </Link>

                          {/* Tailor for JD Button */}
                          <Link
                            href={`/candidate/resumes/tailor/${resume.id}`}
                            className="p-1.5 rounded-lg text-app-text-muted hover:text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-950/30 transition-colors"
                            title="Tailor for Job Description"
                          >
                            <Sparkles size={15} />
                          </Link>

                          {/* Download PDF */}
                          <button
                            onClick={() => handleDownloadPdf(resume)}
                            className="p-1.5 rounded-lg text-app-text-muted hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950/30 transition-colors"
                            title="Download PDF"
                          >
                            <Download size={15} />
                          </button>

                          {/* Download TeX */}
                          <button
                            onClick={() => handleDownloadLatex(resume)}
                            className="p-1.5 rounded-lg text-app-text-muted hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-950/30 transition-colors font-mono text-[10px] font-bold"
                            title="Download LaTeX Source (.tex)"
                          >
                            TeX
                          </button>

                          {/* Delete Resume */}
                          <button
                            onClick={() => {
                              setResumeToDelete(resume);
                              setDeleteModalOpen(true);
                            }}
                            className="p-1.5 rounded-lg text-app-text-muted hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                            title="Delete Resume"
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        title="Delete Resume"
        className="max-w-md"
      >
        <div className="space-y-4 pt-2">
          <p className="text-xs text-app-text-secondary leading-relaxed">
            Are you sure you want to permanently delete{" "}
            <span className="font-bold text-app-text">
              &quot;{resumeToDelete?.title}&quot;
            </span>{" "}
            and all its associated versions? This action cannot be undone.
          </p>
          <div className="flex items-center justify-end gap-3 pt-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeleteModalOpen(false)}
              disabled={isDeleting}
              className="text-xs"
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={confirmDelete}
              disabled={isDeleting}
              className="bg-red-600 hover:bg-red-700 text-white font-semibold text-xs"
            >
              {isDeleting ? "Deleting..." : "Delete Permanently"}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
