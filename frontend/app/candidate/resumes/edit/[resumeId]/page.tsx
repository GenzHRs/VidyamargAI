"use client";

import { useEffect, useState, useRef, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { 
  ArrowLeft, Save, Terminal, Download, Copy, Check, 
  History, RotateCcw, Eye, Code, User, Briefcase, 
  GraduationCap, Folder, Award, FileText, Sparkles, 
  Plus, Trash2, RefreshCw, AlertCircle, CheckCircle2,
  ExternalLink, Layers, X, Clock
} from "lucide-react";
import { 
  resumeCenterApi, 
  ResumeItem, 
  ResumeVersionItem, 
  StructuredResumeData, 
  WorkExperience, 
  Education, 
  Project, 
  ResumeTemplateItem 
} from "@/services/resumeCenterApi";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Alert } from "@/components/ui/Alert";
import { Modal } from "@/components/ui/Modal";

interface PageProps {
  params: Promise<{ resumeId: string }>;
}

export default function ResumeEditorPage({ params }: PageProps) {
  const resolvedParams = use(params);
  const resumeId = Number(resolvedParams.resumeId);
  const router = useRouter();

  // Core Data States
  const [resume, setResume] = useState<ResumeItem | null>(null);
  const [templates, setTemplates] = useState<ResumeTemplateItem[]>([]);
  const [versions, setVersions] = useState<ResumeVersionItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Editor Form States
  const [title, setTitle] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | undefined>(undefined);
  const [personalInfo, setPersonalInfo] = useState<any>({});
  const [summary, setSummary] = useState("");
  const [experience, setExperience] = useState<WorkExperience[]>([]);
  const [education, setEducation] = useState<Education[]>([]);
  const [skillsText, setSkillsText] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [certificationsText, setCertificationsText] = useState("");

  // Editor UI & View States
  const [activeTab, setActiveTab] = useState<"personal" | "summary" | "experience" | "education" | "skills" | "projects" | "certifications">("personal");
  const [previewMode, setPreviewMode] = useState<"pdf" | "latex">("pdf");
  const [latexSource, setLatexSource] = useState<string>("");
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);

  // Status & Feedback States
  const [saveStatus, setSaveStatus] = useState<"saved" | "saving" | "unsaved">("saved");
  const [compiling, setCompiling] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [latexAvailable, setLatexAvailable] = useState<boolean | null>(null);
  const [copiedTex, setCopiedTex] = useState(false);

  // Version Drawer & Diff State
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);
  const [selectedVersionForDiff, setSelectedVersionForDiff] = useState<ResumeVersionItem | null>(null);
  const [restoringVersionId, setRestoringVersionId] = useState<number | null>(null);
  const [enhancingSection, setEnhancingSection] = useState<string | null>(null);

  // AI Assistance handler
  const handleAiEnhance = async (
    section: "summary" | "experience_bullet" | "project_description",
    text: string,
    context: string,
    onApply: (enhanced: string) => void
  ) => {
    if (!text || text.trim().length < 5) {
      setErrorMessage("Please enter some text first before using AI assistance.");
      return;
    }
    try {
      setEnhancingSection(`${section}-${context}`);
      setErrorMessage("");
      const res = await resumeCenterApi.aiEnhanceSection({ section, text, context });
      if (res && res.enhanced) {
        onApply(res.enhanced);
        setSaveStatus("unsaved");
        setSuccessMessage("Enhanced with strong active voice verbs!");
        setTimeout(() => setSuccessMessage(""), 3000);
      }
    } catch (e: any) {
      setErrorMessage(e.message || "Failed to enhance section");
    } finally {
      setEnhancingSection(null);
    }
  };

  // Initial Data Fetch
  const loadResumeData = async () => {
    try {
      setLoading(true);
      setErrorMessage("");
      const [res, tpls, vers] = await Promise.all([
        resumeCenterApi.getResume(resumeId),
        resumeCenterApi.getTemplates(),
        resumeCenterApi.getVersions(resumeId),
      ]);

      setResume(res);
      setTemplates(tpls);
      setVersions(vers);
      setTitle(res.title);
      setSelectedTemplateId(res.template_id);

      // Populate structured data
      const data = res.structured_data || {};
      setPersonalInfo(data.personal_info || {});
      setSummary(data.summary || data.professional_summary || "");
      setExperience(data.experience || data.work_experience || []);
      setEducation(data.education || []);
      setProjects(data.projects || []);

      // Skills string
      if (Array.isArray(data.skills)) {
        setSkillsText(data.skills.join(", "));
      } else if (typeof data.skills === "object" && data.skills !== null) {
        setSkillsText(
          Object.entries(data.skills)
            .map(([cat, list]) => `${cat}: ${Array.isArray(list) ? list.join(", ") : list}`)
            .join("\n")
        );
      } else {
        setSkillsText("");
      }

      // Certifications
      if (Array.isArray(data.certifications)) {
        setCertificationsText(
          data.certifications
            .map((c) => (typeof c === "string" ? c : c.name || ""))
            .join("\n")
        );
      }

      // Load LaTeX text
      try {
        const tex = await resumeCenterApi.downloadLatexText(resumeId);
        setLatexSource(tex);
      } catch (e) {
        // May not be compiled yet
      }

      // If compiled, try fetching PDF blob
      if (res.status.toUpperCase() === "COMPILED" || res.latest_pdf_url) {
        try {
          const blob = await resumeCenterApi.downloadPdfBlob(resumeId, true);
          const url = URL.createObjectURL(blob);
          setPdfBlobUrl(url);
          setLatexAvailable(true);
        } catch (e) {
          // No compiled PDF available yet
        }
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load resume");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadResumeData();
    return () => {
      if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
    };
  }, [resumeId]);

  // Clean up PDF object URLs
  useEffect(() => {
    return () => {
      if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
    };
  }, [pdfBlobUrl]);

  // Helper to reassemble structured JSON from inputs
  const assembleData = (): StructuredResumeData => {
    const skillsLines = skillsText.split("\n").filter((l) => l.trim().length > 0);
    const parsedSkills: Record<string, string[]> = {};
    const uncatSkills: string[] = [];

    skillsLines.forEach((line) => {
      if (line.includes(":")) {
        const [cat, items] = line.split(":");
        parsedSkills[cat.trim()] = items
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
      } else {
        line.split(",").forEach((s) => uncatSkills.push(s.trim()));
      }
    });

    const certs = certificationsText
      .split("\n")
      .map((c) => c.trim())
      .filter(Boolean);

    return {
      personal_info: personalInfo,
      summary,
      experience,
      education,
      skills: Object.keys(parsedSkills).length > 0 ? parsedSkills : uncatSkills,
      projects,
      certifications: certs,
    };
  };

  // Save changes action
  const handleSave = async (createNewVersion = false, summaryText?: string) => {
    try {
      setSaveStatus("saving");
      setErrorMessage("");

      const structured_data = assembleData();
      const updated = await resumeCenterApi.updateResume(resumeId, {
        title,
        template_id: selectedTemplateId,
        structured_data,
        create_new_version: createNewVersion,
        change_summary: summaryText || (createNewVersion ? "Manual revision" : undefined),
      });

      setResume(updated);
      setSaveStatus("saved");
      setSuccessMessage(createNewVersion ? "New version created!" : "Changes saved!");
      setTimeout(() => setSuccessMessage(""), 3000);

      // Refresh versions if a new version was explicitly requested
      if (createNewVersion) {
        const vers = await resumeCenterApi.getVersions(resumeId);
        setVersions(vers);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to save changes");
      setSaveStatus("unsaved");
    }
  };

  // Compile PDF action
  const handleCompile = async () => {
    try {
      setCompiling(true);
      setErrorMessage("");

      // First save current structured state
      await handleSave(false);

      const result = await resumeCenterApi.compileResume(resumeId);
      setLatexAvailable(Boolean(result.latex_available));

      // Refresh LaTeX text
      try {
        const tex = await resumeCenterApi.downloadLatexText(resumeId);
        setLatexSource(tex);
      } catch (e) {
        // Optional LaTeX source
      }

      // If compilation succeeded or PDF is available, load and display PDF preview
      if (result.status === "success" || result.latest_pdf_url || result.pdf_available) {
        const blob = await resumeCenterApi.downloadPdfBlob(resumeId, true);
        if (pdfBlobUrl) URL.revokeObjectURL(pdfBlobUrl);
        const newUrl = URL.createObjectURL(blob);
        setPdfBlobUrl(newUrl);
        setPreviewMode("pdf");
        setSuccessMessage(result.message || "Compiled to PDF successfully!");
      } else {
        setPreviewMode("latex");
        setSuccessMessage(result.message || "LaTeX source generated! Ready for Overleaf export.");
      }
      setTimeout(() => setSuccessMessage(""), 4000);
    } catch (err: any) {
      setErrorMessage(err.message || "Compilation failed. Please verify your entries and retry.");
    } finally {
      setCompiling(false);
    }
  };

  // Restore Version action
  const handleRestoreVersion = async (versionId: number) => {
    try {
      setRestoringVersionId(versionId);
      setErrorMessage("");
      await resumeCenterApi.restoreVersion(resumeId, versionId);
      setSuccessMessage("Version restored successfully!");
      setTimeout(() => setSuccessMessage(""), 3000);
      setHistoryDrawerOpen(false);
      await loadResumeData();
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to restore version");
    } finally {
      setRestoringVersionId(null);
    }
  };

  // Downloads
  const downloadPdf = async () => {
    try {
      const blob = await resumeCenterApi.downloadPdfBlob(resumeId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${title.replace(/[^a-zA-Z0-9_-]/g, "_")}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setErrorMessage(err.message || "PDF download failed. Compile resume first.");
    }
  };

  const downloadLatex = async () => {
    try {
      const tex = await resumeCenterApi.downloadLatexText(resumeId);
      const blob = new Blob([tex], { type: "text/x-tex;charset=utf-8" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${title.replace(/[^a-zA-Z0-9_-]/g, "_")}.tex`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setErrorMessage(err.message || "LaTeX download failed");
    }
  };

  const copyLatexToClipboard = () => {
    if (!latexSource) return;
    navigator.clipboard.writeText(latexSource);
    setCopiedTex(true);
    setTimeout(() => setCopiedTex(false), 2000);
  };

  // Sub-forms for Experience, Projects, etc.
  const addExperience = () => {
    setExperience([...experience, { title: "", company: "", bullets: [""] }]);
    setSaveStatus("unsaved");
  };

  const removeExperience = (idx: number) => {
    setExperience(experience.filter((_, i) => i !== idx));
    setSaveStatus("unsaved");
  };

  const updateExperience = (idx: number, field: keyof WorkExperience, val: any) => {
    const updated = [...experience];
    updated[idx] = { ...updated[idx], [field]: val };
    setExperience(updated);
    setSaveStatus("unsaved");
  };

  const addExpBullet = (expIdx: number) => {
    const updated = [...experience];
    updated[expIdx].bullets = [...(updated[expIdx].bullets || []), ""];
    setExperience(updated);
    setSaveStatus("unsaved");
  };

  const updateExpBullet = (expIdx: number, bIdx: number, val: string) => {
    const updated = [...experience];
    const bullets = [...(updated[expIdx].bullets || [])];
    bullets[bIdx] = val;
    updated[expIdx].bullets = bullets;
    setExperience(updated);
    setSaveStatus("unsaved");
  };

  const removeExpBullet = (expIdx: number, bIdx: number) => {
    const updated = [...experience];
    updated[expIdx].bullets = (updated[expIdx].bullets || []).filter((_, i) => i !== bIdx);
    setExperience(updated);
    setSaveStatus("unsaved");
  };

  if (loading) {
    return (
      <div className="p-16 text-center text-app-text-muted space-y-3">
        <RefreshCw size={28} className="animate-spin mx-auto text-blue-600" />
        <p className="text-xs font-semibold">Loading resume editor...</p>
      </div>
    );
  }

  const tabs = [
    { id: "personal", name: "Personal", icon: User },
    { id: "summary", name: "Summary", icon: FileText },
    { id: "experience", name: "Experience", icon: Briefcase },
    { id: "education", name: "Education", icon: GraduationCap },
    { id: "skills", name: "Skills", icon: Code },
    { id: "projects", name: "Projects", icon: Folder },
    { id: "certifications", name: "Certifications", icon: Award },
  ] as const;

  return (
    <div className="p-4 md:p-6 max-w-[1600px] mx-auto space-y-4 font-sans">
      {/* Top Header Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-app-card p-4 rounded-2xl border border-app-border">
        <div className="flex items-center gap-3">
          <Link 
            href="/candidate/resumes" 
            className="p-2 rounded-xl border border-app-border hover:bg-app-surface text-app-text-muted hover:text-app-text transition-colors"
            title="Back to Resumes"
          >
            <ArrowLeft size={16} />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={title}
                onChange={(e) => {
                  setTitle(e.target.value);
                  setSaveStatus("unsaved");
                }}
                className="text-base font-extrabold text-app-text bg-transparent border-b border-transparent hover:border-app-border focus:border-blue-500 focus:outline-none transition-colors"
              />
              <span className="font-mono bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-800 text-[10px] font-bold px-2 py-0.5 rounded-full">
                v{resume?.version_number || 1}
              </span>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-app-text-muted mt-0.5">
              <span>Template: {resume?.template_name || "ATS Classic"}</span>
              <span>•</span>
              <span className="flex items-center gap-1">
                {saveStatus === "saving" ? (
                  <RefreshCw size={10} className="animate-spin text-blue-500" />
                ) : saveStatus === "saved" ? (
                  <CheckCircle2 size={10} className="text-emerald-500" />
                ) : (
                  <Clock size={10} className="text-amber-500" />
                )}
                {saveStatus === "saving" ? "Saving..." : saveStatus === "saved" ? "All changes saved" : "Unsaved changes"}
              </span>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Template Switcher */}
          <div className="flex items-center gap-1.5">
            <Layers size={14} className="text-blue-600 hidden sm:block" />
            <select
              value={selectedTemplateId || ""}
              onChange={(e) => {
                const newId = Number(e.target.value);
                setSelectedTemplateId(newId);
                setSaveStatus("unsaved");
                const matched = templates.find((t) => t.id === newId);
                if (matched) {
                  setSuccessMessage(`Switched to "${matched.name}". Click "Compile PDF" to re-render layout.`);
                  setTimeout(() => setSuccessMessage(""), 4000);
                }
              }}
              className="py-1.5 px-3 text-xs rounded-xl border border-app-border bg-app-surface text-app-text font-semibold focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.ats_score}% ATS)
                </option>
              ))}
            </select>
          </div>

          {/* Version History Button */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setHistoryDrawerOpen(true)}
            className="text-xs"
          >
            <History size={13} className="mr-1.5" />
            History ({versions.length})
          </Button>

          {/* Save Button */}
          <Button
            variant="outline"
            size="sm"
            disabled={saveStatus === "saving"}
            onClick={() => handleSave(false)}
            data-agent-action="save-resume"
            className="text-xs"
          >
            <Save size={13} className="mr-1.5" />
            Save
          </Button>

          {/* Compile PDF Button */}
          <Button
            size="sm"
            disabled={compiling}
            onClick={handleCompile}
            className="bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs shadow-sm"
          >
            <Terminal size={13} className={`mr-1.5 ${compiling ? "animate-spin" : ""}`} />
            {compiling ? "Compiling..." : "Compile PDF"}
          </Button>
        </div>
      </div>

      {/* Notifications */}
      {successMessage && <Alert variant="success">{successMessage}</Alert>}
      {errorMessage && <Alert variant="error">{errorMessage}</Alert>}

      {/* Two-Panel Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-[calc(100vh-240px)]">
        {/* LEFT PANEL: Structured Editor (6 or 7 cols) */}
        <div className="lg:col-span-6 space-y-4 flex flex-col">
          {/* Section Navigation Tabs */}
          <div className="flex overflow-x-auto gap-1.5 border-b border-app-border pb-2">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                    isActive
                      ? "bg-blue-600 text-white shadow-xs"
                      : "bg-app-card border border-app-border text-app-text-muted hover:text-app-text hover:bg-app-surface"
                  }`}
                >
                  <Icon size={13} />
                  <span>{tab.name}</span>
                </button>
              );
            })}
          </div>

          {/* Active Tab Form Container */}
          <Card className="flex-1 p-5 bg-app-card border-app-border overflow-y-auto space-y-5">
            {/* Personal Info Tab */}
            {activeTab === "personal" && (
              <div className="space-y-4">
                <h3 className="text-xs font-bold uppercase tracking-wider text-app-text-muted">
                  Personal & Contact Details
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-medium text-app-text mb-1">Full Name</label>
                    <input
                      type="text"
                      value={personalInfo.full_name || personalInfo.name || ""}
                      onChange={(e) => {
                        setPersonalInfo({ ...personalInfo, full_name: e.target.value });
                        setSaveStatus("unsaved");
                      }}
                      className="w-full text-xs px-3 py-2 rounded-xl border border-app-border bg-app-surface text-app-text"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-app-text mb-1">Email</label>
                    <input
                      type="email"
                      value={personalInfo.email || ""}
                      onChange={(e) => {
                        setPersonalInfo({ ...personalInfo, email: e.target.value });
                        setSaveStatus("unsaved");
                      }}
                      className="w-full text-xs px-3 py-2 rounded-xl border border-app-border bg-app-surface text-app-text"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-app-text mb-1">Phone</label>
                    <input
                      type="text"
                      value={personalInfo.phone || ""}
                      onChange={(e) => {
                        setPersonalInfo({ ...personalInfo, phone: e.target.value });
                        setSaveStatus("unsaved");
                      }}
                      className="w-full text-xs px-3 py-2 rounded-xl border border-app-border bg-app-surface text-app-text"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-app-text mb-1">Location</label>
                    <input
                      type="text"
                      value={personalInfo.location || personalInfo.address || ""}
                      onChange={(e) => {
                        setPersonalInfo({ ...personalInfo, location: e.target.value });
                        setSaveStatus("unsaved");
                      }}
                      className="w-full text-xs px-3 py-2 rounded-xl border border-app-border bg-app-surface text-app-text"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-app-text mb-1">LinkedIn</label>
                    <input
                      type="text"
                      value={personalInfo.linkedin || ""}
                      onChange={(e) => {
                        setPersonalInfo({ ...personalInfo, linkedin: e.target.value });
                        setSaveStatus("unsaved");
                      }}
                      className="w-full text-xs px-3 py-2 rounded-xl border border-app-border bg-app-surface text-app-text"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-app-text mb-1">GitHub</label>
                    <input
                      type="text"
                      value={personalInfo.github || ""}
                      onChange={(e) => {
                        setPersonalInfo({ ...personalInfo, github: e.target.value });
                        setSaveStatus("unsaved");
                      }}
                      className="w-full text-xs px-3 py-2 rounded-xl border border-app-border bg-app-surface text-app-text"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Summary Tab */}
            {activeTab === "summary" && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-app-text-muted">
                    Professional Summary
                  </h3>
                  <button
                    onClick={() =>
                      handleAiEnhance("summary", summary, title, (enhanced) => setSummary(enhanced))
                    }
                    disabled={enhancingSection === `summary-${title}`}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300 border border-purple-200 dark:border-purple-800 hover:bg-purple-100 dark:hover:bg-purple-900/50 transition-colors"
                  >
                    <Sparkles size={12} className={enhancingSection === `summary-${title}` ? "animate-spin text-purple-600" : ""} />
                    <span>{enhancingSection === `summary-${title}` ? "Enhancing..." : "AI Polish Summary"}</span>
                  </button>
                </div>
                <textarea
                  rows={8}
                  value={summary}
                  onChange={(e) => {
                    setSummary(e.target.value);
                    setSaveStatus("unsaved");
                  }}
                  className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-app-border bg-app-surface text-app-text leading-relaxed"
                  placeholder="2-3 sentence overview highlighting your background, core technical strengths, and impact..."
                />
              </div>
            )}

            {/* Experience Tab */}
            {activeTab === "experience" && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-app-text-muted">
                    Work Experience ({experience.length})
                  </h3>
                  <Button size="sm" onClick={addExperience} className="text-xs bg-blue-600 text-white">
                    <Plus size={12} className="mr-1" /> Add Position
                  </Button>
                </div>

                {experience.map((exp, idx) => (
                  <div key={idx} className="p-4 rounded-xl border border-app-border bg-app-surface/50 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-app-text">Position #{idx + 1}</span>
                      <button onClick={() => removeExperience(idx)} className="text-red-500 p-1">
                        <Trash2 size={13} />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[11px] font-medium text-app-text mb-1">Job Title / Designation</label>
                        <input
                          type="text"
                          value={exp.title || exp.designation || exp.role || ""}
                          data-agent-field="resume.designation"
                          onChange={(e) => {
                            const val = e.target.value;
                            updateExperience(idx, "title", val);
                            updateExperience(idx, "designation", val);
                            updateExperience(idx, "role", val);
                          }}
                          className="w-full text-xs px-3 py-1.5 rounded-lg border border-app-border bg-app-surface text-app-text font-semibold"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-app-text mb-1">Company / Employer</label>
                        <input
                          type="text"
                          value={exp.company || exp.employer || ""}
                          data-agent-field="resume.company"
                          onChange={(e) => {
                            const val = e.target.value;
                            updateExperience(idx, "company", val);
                            updateExperience(idx, "employer", val);
                          }}
                          className="w-full text-xs px-3 py-1.5 rounded-lg border border-app-border bg-app-surface text-app-text font-semibold"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-app-text mb-1">Dates</label>
                        <input
                          type="text"
                          value={`${exp.start_date || ""} - ${exp.end_date || ""}`}
                          onChange={(e) => {
                            const [start, end] = e.target.value.split("-");
                            updateExperience(idx, "start_date", start?.trim());
                            updateExperience(idx, "end_date", end?.trim());
                          }}
                          className="w-full text-xs px-3 py-1.5 rounded-lg border border-app-border bg-app-surface text-app-text"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-app-text mb-1">Location</label>
                        <input
                          type="text"
                          value={exp.location || ""}
                          onChange={(e) => updateExperience(idx, "location", e.target.value)}
                          className="w-full text-xs px-3 py-1.5 rounded-lg border border-app-border bg-app-surface text-app-text"
                        />
                      </div>
                    </div>

                    {/* Bullets */}
                    <div className="space-y-1.5 pt-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-semibold text-app-text-muted">Bullet Points</span>
                        <button onClick={() => addExpBullet(idx)} className="text-xs text-blue-600 hover:underline">
                          + Add Bullet
                        </button>
                      </div>
                      {(exp.bullets || []).map((bullet, bIdx) => (
                        <div key={bIdx} className="flex items-center gap-2">
                          <input
                            type="text"
                            value={bullet}
                            onChange={(e) => updateExpBullet(idx, bIdx, e.target.value)}
                            className="flex-1 text-xs px-3 py-1.5 rounded-lg border border-app-border bg-app-surface text-app-text"
                            placeholder="Action verb + core task + measurable business or technical outcome..."
                          />
                          <button
                            type="button"
                            onClick={() =>
                              handleAiEnhance(
                                "experience_bullet",
                                bullet,
                                `${exp.title || "Software Engineer"} at ${exp.company || "Company"}`,
                                (enhanced) => updateExpBullet(idx, bIdx, enhanced)
                              )
                            }
                            disabled={enhancingSection === `experience_bullet-${exp.title || "Software Engineer"} at ${exp.company || "Company"}`}
                            className="p-1.5 rounded-lg border border-purple-200 dark:border-purple-800 text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-950/40"
                            title="AI Polish Bullet with Action Verb"
                          >
                            <Sparkles size={12} className={enhancingSection === `experience_bullet-${exp.title || "Software Engineer"} at ${exp.company || "Company"}` ? "animate-spin text-purple-600" : ""} />
                          </button>
                          <button onClick={() => removeExpBullet(idx, bIdx)} className="text-app-text-muted hover:text-red-500 p-1" title="Remove bullet">
                            <Trash2 size={12} />
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Education Tab */}
            {activeTab === "education" && (
              <div className="space-y-4">
                <h3 className="text-xs font-bold uppercase tracking-wider text-app-text-muted">Education</h3>
                {education.map((edu, idx) => (
                  <div key={idx} className="p-4 rounded-xl border border-app-border bg-app-surface/50 space-y-3">
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div>
                        <label className="block text-[11px] font-medium text-app-text mb-1">Degree</label>
                        <input
                          type="text"
                          value={edu.degree || ""}
                          onChange={(e) => {
                            const updated = [...education];
                            updated[idx].degree = e.target.value;
                            setEducation(updated);
                            setSaveStatus("unsaved");
                          }}
                          className="w-full text-xs px-3 py-1.5 rounded-lg border border-app-border bg-app-surface text-app-text"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-app-text mb-1">Institution</label>
                        <input
                          type="text"
                          value={edu.institution || ""}
                          onChange={(e) => {
                            const updated = [...education];
                            updated[idx].institution = e.target.value;
                            setEducation(updated);
                            setSaveStatus("unsaved");
                          }}
                          className="w-full text-xs px-3 py-1.5 rounded-lg border border-app-border bg-app-surface text-app-text"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-app-text mb-1">Graduation / GPA</label>
                        <input
                          type="text"
                          value={edu.graduation_year || edu.gpa || ""}
                          onChange={(e) => {
                            const updated = [...education];
                            updated[idx].graduation_year = e.target.value;
                            setEducation(updated);
                            setSaveStatus("unsaved");
                          }}
                          className="w-full text-xs px-3 py-1.5 rounded-lg border border-app-border bg-app-surface text-app-text"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Skills Tab */}
            {activeTab === "skills" && (
              <div className="space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-app-text-muted">Skills</h3>
                <textarea
                  rows={8}
                  value={skillsText}
                  onChange={(e) => {
                    setSkillsText(e.target.value);
                    setSaveStatus("unsaved");
                  }}
                  className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-app-border bg-app-surface text-app-text font-mono leading-relaxed"
                />
              </div>
            )}

            {/* Projects Tab */}
            {activeTab === "projects" && (
              <div className="space-y-4">
                <h3 className="text-xs font-bold uppercase tracking-wider text-app-text-muted">Projects</h3>
                {projects.map((proj, idx) => (
                  <div key={idx} className="p-4 rounded-xl border border-app-border bg-app-surface/50 space-y-3">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[11px] font-medium text-app-text mb-1">Name</label>
                        <input
                          type="text"
                          value={proj.name || ""}
                          onChange={(e) => {
                            const updated = [...projects];
                            updated[idx].name = e.target.value;
                            setProjects(updated);
                            setSaveStatus("unsaved");
                          }}
                          className="w-full text-xs px-3 py-1.5 rounded-lg border border-app-border bg-app-surface text-app-text"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-app-text mb-1">Technologies</label>
                        <input
                          type="text"
                          value={proj.tech_stack || proj.technologies || ""}
                          onChange={(e) => {
                            const updated = [...projects];
                            updated[idx].tech_stack = e.target.value;
                            setProjects(updated);
                            setSaveStatus("unsaved");
                          }}
                          className="w-full text-xs px-3 py-1.5 rounded-lg border border-app-border bg-app-surface text-app-text"
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Certifications Tab */}
            {activeTab === "certifications" && (
              <div className="space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-app-text-muted">Certifications</h3>
                <textarea
                  rows={6}
                  value={certificationsText}
                  onChange={(e) => {
                    setCertificationsText(e.target.value);
                    setSaveStatus("unsaved");
                  }}
                  className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-app-border bg-app-surface text-app-text leading-relaxed"
                />
              </div>
            )}
          </Card>
        </div>

        {/* RIGHT PANEL: Live Preview & LaTeX Source (6 cols) */}
        <div className="lg:col-span-6 flex flex-col space-y-4">
          {/* Preview Controls Bar */}
          <div className="flex items-center justify-between bg-app-card p-3 rounded-2xl border border-app-border">
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setPreviewMode("pdf")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                  previewMode === "pdf"
                    ? "bg-blue-600 text-white shadow-xs"
                    : "text-app-text-muted hover:text-app-text"
                }`}
              >
                <Eye size={13} />
                <span>PDF Preview</span>
              </button>
              <button
                onClick={() => setPreviewMode("latex")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-all ${
                  previewMode === "latex"
                    ? "bg-blue-600 text-white shadow-xs"
                    : "text-app-text-muted hover:text-app-text"
                }`}
              >
                <Code size={13} />
                <span>LaTeX Source</span>
              </button>
            </div>

            <div className="flex items-center gap-2">
              {previewMode === "latex" && (
                <button
                  onClick={copyLatexToClipboard}
                  className="p-1.5 rounded-lg border border-app-border hover:bg-app-surface text-app-text-muted hover:text-app-text text-xs flex items-center gap-1"
                  title="Copy LaTeX"
                >
                  {copiedTex ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
                  <span className="text-[11px] font-semibold">{copiedTex ? "Copied" : "Copy"}</span>
                </button>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={downloadLatex}
                className="text-xs"
                title="Download .tex"
              >
                Download TeX
              </Button>
              {pdfBlobUrl && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => window.open(pdfBlobUrl, "_blank")}
                  className="text-xs"
                  title="Open PDF in new tab"
                >
                  <ExternalLink size={13} className="mr-1" />
                  Pop-out
                </Button>
              )}
              <Button
                size="sm"
                onClick={downloadPdf}
                className="bg-blue-600 hover:bg-blue-700 text-white text-xs"
                title="Download PDF"
              >
                <Download size={13} className="mr-1" />
                PDF
              </Button>
            </div>
          </div>

          {/* Preview Screen Container */}
          <Card className="relative flex-1 bg-app-card border-app-border overflow-hidden rounded-2xl min-h-[550px] flex flex-col">
            {compiling && (
              <div className="absolute inset-0 bg-app-card/85 backdrop-blur-xs z-20 flex flex-col items-center justify-center space-y-3 p-6 text-center">
                <RefreshCw size={36} className="text-blue-500 animate-spin" />
                <div className="space-y-1">
                  <h4 className="text-sm font-bold text-app-text">Compiling Resume PDF</h4>
                  <p className="text-xs text-app-text-muted max-w-xs">
                    Rendering typography, ATS formatting, and document layout...
                  </p>
                </div>
              </div>
            )}

            {previewMode === "pdf" ? (
              pdfBlobUrl ? (
                <div className="relative flex-1 w-full h-full min-h-[550px] bg-slate-900/5 dark:bg-slate-950/30 flex flex-col">
                  <object
                    data={`${pdfBlobUrl}#toolbar=1&view=FitH`}
                    type="application/pdf"
                    className="w-full flex-1 min-h-[550px] rounded-2xl"
                  >
                    <iframe
                      src={`${pdfBlobUrl}#toolbar=1`}
                      title="Resume PDF Preview"
                      className="w-full flex-1 min-h-[550px] border-none rounded-2xl"
                    />
                  </object>
                </div>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-4">
                  <div className="w-14 h-14 rounded-2xl bg-blue-500/10 dark:bg-blue-500/20 flex items-center justify-center text-blue-600 dark:text-blue-400">
                    <Terminal size={28} className={compiling ? "animate-spin" : ""} />
                  </div>
                  <div className="space-y-1.5 max-w-sm">
                    <h4 className="text-base font-bold text-app-text">
                      {errorMessage ? "Compilation Needs Attention" : "Resume Not Yet Compiled"}
                    </h4>
                    <p className="text-xs text-app-text-muted leading-relaxed">
                      {errorMessage
                        ? errorMessage
                        : "Click the \"Compile PDF\" button above or \"Compile Now\" below to render this resume into an Overleaf-grade PDF document."}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    onClick={handleCompile}
                    disabled={compiling}
                    className="bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-4 py-2 shadow-sm transition-all hover:scale-[1.02] active:scale-[0.98]"
                  >
                    <Terminal size={14} className="mr-1.5" />
                    {errorMessage ? "Retry Compilation" : "Compile Now"}
                  </Button>
                </div>
              )
            ) : (
              <div className="flex-1 p-4 bg-slate-950 text-slate-100 font-mono text-xs overflow-y-auto max-h-[600px] rounded-2xl">
                <pre className="whitespace-pre-wrap leading-relaxed">{latexSource || "LaTeX source will appear here once saved or compiled."}</pre>
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* VERSION HISTORY DRAWER / MODAL */}
      <Modal
        isOpen={historyDrawerOpen}
        onClose={() => setHistoryDrawerOpen(false)}
        title="Resume Version History"
        className="max-w-2xl"
      >
        <div className="space-y-4 pt-2">
          <p className="text-xs text-app-text-muted">
            All document revisions are securely stored. You can view past versions or restore any previous snapshot at any time.
          </p>

          <div className="divide-y divide-app-border max-h-80 overflow-y-auto">
            {versions.map((v) => (
              <div key={v.id} className="py-3 flex items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-xs text-app-text">
                      Version {v.version_number}
                    </span>
                    {v.is_current && (
                      <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 text-[10px]">
                        Current
                      </Badge>
                    )}
                  </div>
                  <span className="text-[11px] text-app-text-muted block mt-0.5">
                    {v.created_at ? new Date(v.created_at).toLocaleString() : "Earlier"} • {v.change_summary || "Document revision"}
                  </span>
                </div>

                {!v.is_current && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={restoringVersionId === v.id}
                    onClick={() => handleRestoreVersion(v.id)}
                    className="text-xs"
                  >
                    <RotateCcw size={12} className="mr-1" />
                    {restoringVersionId === v.id ? "Restoring..." : "Restore"}
                  </Button>
                )}
              </div>
            ))}
          </div>

          <div className="flex justify-end pt-3 border-t border-app-border">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setHistoryDrawerOpen(false)}
              className="text-xs"
            >
              Close
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
