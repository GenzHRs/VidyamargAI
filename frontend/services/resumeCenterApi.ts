/**
 * Resume Center API Client
 * Connects frontend to the production Resume Center backend endpoints with cookie/token auth,
 * CSRF headers, and full type safety.
 */

const getApiBaseUrl = (): string => {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");
  if (typeof window !== "undefined" && window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1") {
    return "https://vidyamargai-production-2c1f.up.railway.app/api/v1";
  }
  return "http://localhost:8000/api/v1";
};


function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function getAuthHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "Accept": "application/json",
  };
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const csrf = getCsrfToken();
  if (csrf) {
    headers["X-CSRF-Token"] = csrf;
  }
  return headers;
}

export async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = 10000
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let combinedSignal: AbortSignal = controller.signal;
  if (options.signal) {
    if (options.signal.aborted) {
      clearTimeout(timeoutId);
      throw new Error("Request was aborted");
    }
    options.signal.addEventListener("abort", () => {
      controller.abort();
    });
  }

  try {
    const res = await fetch(url, {
      ...options,
      signal: combinedSignal,
    });
    return res;
  } catch (error: any) {
    if (error?.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

export interface PersonalInfo {
  full_name?: string;
  name?: string;
  email?: string;
  phone?: string;
  location?: string;
  address?: string;
  linkedin?: string;
  github?: string;
  portfolio?: string;
  custom_links?: Array<{ label: string; url: string } | string>;
}

export interface WorkExperience {
  title?: string;
  role?: string;
  designation?: string;
  company?: string;
  employer?: string;
  location?: string;
  employment_location?: string;
  start_date?: string;
  end_date?: string;
  bullets?: string[];
  responsibilities?: string[];
}

export interface Project {
  name?: string;
  title?: string;
  technologies?: string;
  tech_stack?: string;
  start_date?: string;
  end_date?: string;
  link?: string;
  url?: string;
  bullets?: string[];
}

export interface Education {
  degree?: string;
  institution?: string;
  university?: string;
  location?: string;
  start_date?: string;
  end_date?: string;
  graduation_year?: string;
  gpa?: string;
  honors?: string;
}

export interface Certification {
  name?: string;
  issuer?: string;
  date?: string;
}

export interface StructuredResumeData {
  personal_info?: PersonalInfo;
  summary?: string;
  professional_summary?: string;
  career_objective?: string;
  skills?: Record<string, string[]> | string[];
  experience?: WorkExperience[];
  work_experience?: WorkExperience[];
  projects?: Project[];
  education?: Education[];
  certifications?: Array<Certification | string>;
  custom_sections?: Array<{ title: string; content: string }>;
}

export interface ComprehensiveExtractedProfile {
  personal_info?: {
    full_name?: string | null;
    first_name?: string | null;
    middle_name?: string | null;
    last_name?: string | null;
    professional_title?: string | null;
    email?: string | null;
    additional_emails?: string[];
    phone?: string | null;
    additional_phones?: string[];
    location?: string | null;
    city?: string | null;
    state?: string | null;
    country?: string | null;
    linkedin_url?: string | null;
    github_url?: string | null;
    portfolio_url?: string | null;
    custom_links?: Array<{ label: string; url: string }>;
  };
  professional_summary?: {
    summary?: string | null;
    career_objective?: string | null;
    years_of_experience?: number | null;
    areas_of_specialization?: string[];
    career_interests?: string[];
  };
  skills?: {
    programming_languages?: string[];
    frameworks_libraries?: string[];
    databases?: string[];
    cloud_platforms?: string[];
    developer_tools?: string[];
    ai_ml_technologies?: string[];
    soft_skills?: string[];
    domain_knowledge?: string[];
    other_skills?: string[];
    all_raw_skills?: string[];
  };
  work_experience?: Array<{
    employer?: string;
    company?: string;
    designation?: string;
    role?: string;
    title?: string;
    job_title?: string;
    employment_location?: string | null;
    start_date?: string | null;
    end_date?: string | null;
    is_current?: boolean;
    employment_type?: string | null;
    responsibilities?: string[];
    achievements?: string[];
    technologies?: string[];
    metrics?: string[];
    original_text?: string | null;
  }>;
  education?: Array<{
    degree?: string;
    field_of_study?: string | null;
    institution?: string;
    location?: string | null;
    start_date?: string | null;
    end_date?: string | null;
    graduation_year?: string | null;
    grade?: string | null;
    relevant_coursework?: string[];
    achievements?: string[];
    thesis?: string | null;
  }>;
  projects?: Array<{
    name?: string;
    description?: string | null;
    problem?: string | null;
    solution?: string | null;
    technologies?: string[];
    responsibilities?: string[];
    features?: string[];
    results_metrics?: string[];
    duration?: string | null;
    link?: string | null;
    project_type?: string | null;
  }>;
  certifications?: Array<{
    name?: string;
    issuing_organization?: string | null;
    issue_date?: string | null;
    expiration_date?: string | null;
    credential_id?: string | null;
    credential_url?: string | null;
    training_type?: string | null;
  }>;
  achievements?: string[];
  publications?: Array<{
    title?: string;
    publisher?: string | null;
    date?: string | null;
    url?: string | null;
  }>;
  languages?: Array<{
    language?: string;
    proficiency?: string | null;
  }>;
  custom_sections?: Array<{
    section_title?: string;
    original_content?: string;
    structured_content?: any;
  }>;
  confidence_score?: number;
  missing_fields?: string[];
  extraction_warnings?: string[];
}

export interface ResumeTemplateItem {
  id: number;
  name: string;
  slug: string;
  description: string;
  category: string;
  ats_score: number;
  license_name: string;
  license_url?: string;
  preview_image?: string;
  is_active: boolean;
  latex_template?: string;
}

export interface ResumeItem {
  id: number;
  title: string;
  source_type: string;
  template_id?: number;
  template_name?: string;
  template_slug?: string;
  current_version_id?: number;
  version_number: number;
  original_file_url?: string;
  latest_pdf_url?: string;
  latest_tex_url?: string;
  status: string;
  is_active?: boolean;
  is_verified?: boolean;
  extraction_status?: string;
  created_at?: string;
  updated_at?: string;
  structured_data?: StructuredResumeData;
  change_summary?: string;
}

export interface ResumeVersionItem {
  id: number;
  version_number: number;
  change_summary?: string;
  created_at?: string;
  is_current: boolean;
  pdf_file_url?: string;
  structured_data: StructuredResumeData;
}

export interface SuggestedChange {
  section: string;
  original: string;
  proposed: string;
  reason: string;
  requires_confirmation: boolean;
}

export interface TailoredResumeOutput {
  job_title: string;
  company: string;
  required_skills: string[];
  preferred_skills: string[];
  responsibilities: string[];
  matching_skills: string[];
  missing_requirements: string[];
  transferable_skills: string[];
  suggested_changes: SuggestedChange[];
  final_resume_data: StructuredResumeData;
  ats_keywords: string[];
  warnings: string[];
}

export interface SourceResumeForTailoring {
  resume_id: number;
  title: string;
  template_id?: number;
  structured_data: StructuredResumeData;
  raw_text_length: number;
  source_type: string;
}

export interface RenderTailoredTemplateResponse {
  template_id: number;
  template_name: string;
  template_slug: string;
  latex_source: string;
  preview_url: string;
  compiled_success: boolean;
}

export interface SaveTailoredResumeResponse {
  message: string;
  resume_id: number;
  version_id: number;
  title: string;
  template_id: number;
  template_name: string;
  latest_pdf_url?: string;
  source_resume_id: number;
}

export interface ScoreExplanation {
  positive_factors: string[];
  negative_factors: string[];
  summary: string;
  disclaimer: string;
}

export interface SkillGapClassification {
  critical_gaps: string[];
  important_gaps: string[];
  optional_gaps: string[];
}

export interface ApplicationReadiness {
  readiness_level: "HIGH" | "MEDIUM" | "LOW";
  score: number;
  required_skills_count: number;
  matched_skills_count: number;
  partial_skills_count: number;
  missing_skills_count: number;
  critical_missing_count: number;
  recommendation: string;
  reasoning: string[];
}

export interface ApplicationFieldItem {
  field_key: string;
  field_label: string;
  field_type: "EXACT_FIELD" | "SEMANTIC_FIELD" | "MISSING_INFORMATION" | "USER_CONFIRMATION_REQUIRED";
  value?: any;
  source: string;
  confidence: number;
  user_confirmed: boolean;
}

export interface PreparedApplication {
  status: "DRAFT" | "PREPARED" | "REVIEW_REQUIRED" | "CONFIRMED" | "SUBMITTED";
  job_title: string;
  company: string;
  exact_fields: ApplicationFieldItem[];
  semantic_fields: ApplicationFieldItem[];
  missing_fields: ApplicationFieldItem[];
  requires_user_confirmation: boolean;
  submission_allowed: boolean;
}

export interface JDOptimizeRequest {
  resume_id?: number;
  job_description: string;
  template_id?: number;
  job_title?: string;
  company?: string;
  job_id?: number;
  application_id?: number;
  force_new?: boolean;
  rendering_mode?: "template" | "original_layout";
}

export interface JDOptimizeResponse {
  optimization_id: number;
  master_resume_id: number;
  job_id?: number | null;
  application_id?: number | null;
  ats_score: number;
  resume_match_score?: number;
  keyword_match: number;
  experience_match: number;
  technical_match: number;
  responsibility_match: number;
  alignment_score: number;
  quality_score?: number;
  truthfulness_score: number;
  score_breakdown?: Record<string, number>;
  score_explanation?: ScoreExplanation;
  skill_gaps?: SkillGapClassification;
  application_readiness?: ApplicationReadiness;
  prepared_application?: PreparedApplication;
  optimized_resume: StructuredResumeData;
  matched_skills: string[];
  partial_matches: string[];
  missing_skills: string[];
  recommendations: string[];
  ats_report: Record<string, any>;
  job_title: string;
  dynamic_title?: string;
  generated_title?: string;
  company: string;
  is_submitted?: boolean;
  is_immutable?: boolean;
  submitted_at?: string | null;
  submitted_artifact_url?: string | null;
  jd_hash?: string | null;
  content_hash?: string | null;
  optimization_version?: number;
  template_version?: string | null;
  rendering_mode?: string;
  fidelity_tier?: string;
  candidate_approved?: boolean;
  approved_at?: string | null;
  approval_hash?: string | null;
  approval_notes?: string | null;
  layout_validation_status?: string;
  layout_warnings?: string[];
  created_at?: string | null;
  updated_at?: string | null;
  evidence_items: Array<{
    requirement: string;
    evidence: string;
    match_type: string;
    confidence: number;
    category?: string | null;
  }>;
}

class ResumeCenterApiService {
  // ── TEMPLATES ─────────────────────────────────────────────────────────────
  async getTemplates(signal?: AbortSignal): Promise<ResumeTemplateItem[]> {
    try {
      const res = await fetchWithTimeout(
        `${getApiBaseUrl()}/resume-templates`,
        {
          headers: getAuthHeaders(),
          credentials: "include",
          signal,
        },
        10000
      );
      if (!res.ok) return [];
      return res.json();
    } catch (err) {
      console.warn("getTemplates fetch warning:", err);
      return [];
    }
  }

  async getTemplate(id: number, signal?: AbortSignal): Promise<ResumeTemplateItem> {
    const res = await fetchWithTimeout(
      `${getApiBaseUrl()}/resume-templates/${id}`,
      {
        headers: getAuthHeaders(),
        credentials: "include",
        signal,
      },
      10000
    );
    if (!res.ok) throw new Error("Failed to load resume template details");
    return res.json();
  }

  // ── RESUMES CRUD ──────────────────────────────────────────────────────────
  async getResumes(search?: string, statusFilter?: string, signal?: AbortSignal): Promise<ResumeItem[]> {
    const headers = getAuthHeaders() as Record<string, string>;
    if (!headers["Authorization"]) {
      return [];
    }
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (statusFilter) params.set("status_filter", statusFilter);
    const qs = params.toString() ? `?${params.toString()}` : "";

    const res = await fetchWithTimeout(
      `${getApiBaseUrl()}/resumes${qs}`,
      {
        headers,
        credentials: "include",
        signal,
      },
      10000
    );

    if (res.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("token");
        window.location.href = "/login";
      }
      throw new Error("Session expired. Please log in again.");
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Failed to fetch resumes from server (HTTP ${res.status})`);
    }

    return res.json();
  }

  async getResume(id: number, signal?: AbortSignal): Promise<ResumeItem> {
    const res = await fetchWithTimeout(
      `${getApiBaseUrl()}/resumes/${id}`,
      {
        headers: getAuthHeaders(),
        credentials: "include",
        signal,
      },
      10000
    );
    if (!res.ok) throw new Error("Failed to load resume");
    return res.json();
  }

  async createResume(data: {
    title: string;
    template_id?: number;
    structured_data: StructuredResumeData;
  }): Promise<ResumeItem> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resumes`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to create resume");
    }
    return res.json();
  }

  async updateResume(
    id: number,
    data: {
      title?: string;
      template_id?: number;
      status?: string;
      structured_data?: StructuredResumeData;
      change_summary?: string;
      create_new_version?: boolean;
    }
  ): Promise<ResumeItem> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resumes/${id}`, {
      method: "PATCH",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to update resume");
    }
    return res.json();
  }

  async deleteResume(id: number): Promise<{ message: string; id: number }> {
    const res = await fetch(`${getApiBaseUrl()}/resumes/${id}`, {
      method: "DELETE",
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) throw new Error("Failed to delete resume");
    return res.json();
  }

  // ── UPLOAD & EXTRACTION ──────────────────────────────────────────────────
  async uploadResume(
    file: File,
    title?: string,
    templateId?: number
  ): Promise<{
    message: string;
    resume_id: number;
    version_id: number;
    title: string;
    file_name?: string;
    file_size?: number;
    file_hash?: string;
    page_count?: number;
    original_file_url: string;
    extraction_status: string;
    confidence_score: number;
    missing_fields: string[];
    warnings: string[];
    is_duplicate?: boolean;
    structured_data: ComprehensiveExtractedProfile;
    template_compatible_data?: StructuredResumeData;
    raw_text_preview?: string;
    layout_info?: any;
  }> {
    const formData = new FormData();
    formData.append("file", file);
    if (title) formData.append("title", title);
    if (templateId) formData.append("template_id", templateId.toString());

    const headers: Record<string, string> = {};
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const csrf = getCsrfToken();
    if (csrf) headers["X-CSRF-Token"] = csrf;

    const res = await fetch(`${getApiBaseUrl()}/resumes/upload`, {
      method: "POST",
      headers,
      credentials: "include",
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Upload failed");
    }
    return res.json();
  }

  async getExtraction(resumeId: number): Promise<{
    resume_id: number;
    title: string;
    file_name?: string;
    file_type?: string;
    file_size?: number;
    page_count?: number;
    file_hash?: string;
    original_file_url?: string;
    extraction_status: string;
    extraction_confidence?: number;
    is_verified: boolean;
    raw_text: string;
    layout_info?: any;
    confidence_score: number;
    missing_fields: string[];
    warnings: string[];
    structured_data: ComprehensiveExtractedProfile;
    normalized?: any;
  }> {
    const res = await fetch(`${getApiBaseUrl()}/resumes/${resumeId}/extraction`, {
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) throw new Error("Failed to load resume extraction");
    return res.json();
  }

  async verifyExtraction(
    resumeId: number,
    payload: { structured_data: ComprehensiveExtractedProfile; raw_text?: string }
  ): Promise<{
    message: string;
    resume_id: number;
    is_verified: boolean;
    extraction_status: string;
    structured_data: ComprehensiveExtractedProfile;
  }> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resumes/${resumeId}/extraction/verify`, {
      method: "PUT",
      headers,
      credentials: "include",
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Verification failed");
    }
    return res.json();
  }

  async getCandidateProfileData(): Promise<{
    has_profile: boolean;
    resume_id?: number;
    resume_title?: string;
    is_verified?: boolean;
    profile_data?: ComprehensiveExtractedProfile;
    template_compatible_data?: StructuredResumeData;
  }> {
    const res = await fetch(`${getApiBaseUrl()}/candidate/profile-data`, {
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) throw new Error("Failed to load candidate profile");
    return res.json();
  }

  // ── VERSIONS ──────────────────────────────────────────────────────────────
  async getVersions(resumeId: number): Promise<ResumeVersionItem[]> {
    const res = await fetch(`${getApiBaseUrl()}/resumes/${resumeId}/versions`, {
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) throw new Error("Failed to load version history");
    return res.json();
  }

  async createVersion(
    resumeId: number,
    data: { structured_data: StructuredResumeData; change_summary?: string }
  ): Promise<{ message: string; version_id: number; version_number: number }> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resumes/${resumeId}/versions`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Failed to save new version");
    return res.json();
  }

  async restoreVersion(
    resumeId: number,
    versionId: number
  ): Promise<{ message: string; new_version_id: number; new_version_number: number }> {
    const res = await fetch(`${getApiBaseUrl()}/resumes/${resumeId}/versions/${versionId}/restore`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) throw new Error("Failed to restore version");
    return res.json();
  }

  // ── COMPILATION & DOWNLOAD ────────────────────────────────────────────────
  async compileResume(resumeId: number): Promise<{
    status: string;
    latex_available: boolean;
    pdf_available?: boolean;
    compiler?: string;
    message: string;
    latest_pdf_url?: string;
    latest_tex_url?: string;
    pdf_size_bytes?: number;
  }> {
    const res = await fetch(`${getApiBaseUrl()}/resumes/${resumeId}/compile`, {
      method: "POST",
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Compilation failed");
    }
    return res.json();
  }

  async downloadPdfBlob(resumeId: number, isPreview = false): Promise<Blob> {
    const endpoint = isPreview
      ? `${getApiBaseUrl()}/resumes/${resumeId}/preview/pdf`
      : `${getApiBaseUrl()}/resumes/${resumeId}/download/pdf`;
    const res = await fetch(endpoint, {
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "PDF generation or download failed. Please compile the resume first.");
    }
    const buffer = await res.arrayBuffer();
    return new Blob([buffer], { type: "application/pdf" });
  }

  async downloadLatexText(resumeId: number): Promise<string> {
    const res = await fetch(`${getApiBaseUrl()}/resumes/${resumeId}/download/latex`, {
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) throw new Error("LaTeX download failed");
    return res.text();
  }

  // ── JD TAILORING ──────────────────────────────────────────────────────────
  async analyzeJd(data: {
    job_title: string;
    company: string;
    job_description: string;
    resume_id?: number;
  }): Promise<TailoredResumeOutput> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resume-tailoring/analyze-jd`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "JD analysis failed");
    }
    return res.json();
  }

  async generateTailoredResume(data: {
    resume_id: number;
    job_title: string;
    company: string;
    job_description: string;
    location?: string;
    seniority?: string;
    template_id?: number;
  }): Promise<{
    analysis: TailoredResumeOutput;
    original_resume: StructuredResumeData;
    proposed_resume: StructuredResumeData;
    suggested_changes: SuggestedChange[];
    warnings: string[];
  }> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resume-tailoring/generate`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Tailoring generation failed");
    }
    return res.json();
  }

  async approveTailoring(
    resumeId: number,
    data: {
      approved_resume_data: StructuredResumeData;
      change_summary?: string;
      create_new_resume?: boolean;
      new_title?: string;
    }
  ): Promise<{ message: string; resume_id: number; version_id: number; title: string }> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resume-tailoring/${resumeId}/approve`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Approval failed");
    }
    return res.json();
  }

  async getSourceResumeForTailoring(resumeId: number): Promise<SourceResumeForTailoring> {
    const res = await fetch(`${getApiBaseUrl()}/resume-tailoring/source/${resumeId}`, {
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to load source resume data for tailoring");
    }
    return res.json();
  }

  async renderTailoredTemplate(data: {
    source_resume_id: number;
    selected_template_id: number;
    tailored_resume_data: StructuredResumeData;
  }): Promise<RenderTailoredTemplateResponse> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resume-tailoring/render-template`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to render template preview");
    }
    return res.json();
  }

  getTailoredPreviewUrl(sourceResumeId: number, templateId: number): string {
    return `${getApiBaseUrl()}/resume-tailoring/preview/${sourceResumeId}/${templateId}`;
  }

  async fetchTailoredPreviewBlob(sourceResumeId: number, templateId: number): Promise<Blob> {
    const res = await fetch(`${getApiBaseUrl()}/resume-tailoring/preview/${sourceResumeId}/${templateId}`, {
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) throw new Error("Could not load preview PDF");
    return res.blob();
  }

  async saveTailoredResume(data: {
    source_resume_id: number;
    selected_template_id: number;
    tailored_resume_data: StructuredResumeData;
    job_title: string;
    company_name: string;
    job_description: string;
    custom_title?: string;
  }): Promise<SaveTailoredResumeResponse> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resume-tailoring/save`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to save tailored resume");
    }
    return res.json();
  }

  // ── AI ASSISTANCE ──────────────────────────────────────────────────────────
  async aiEnhanceSection(data: {
    section: "summary" | "experience_bullet" | "project_description";
    text: string;
    context?: string;
  }): Promise<{ section: string; original: string; enhanced: string }> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resumes/ai-enhance`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "AI enhancement failed");
    }
    return res.json();
  }

  // ── JD-DRIVEN ATS OPTIMIZATION ENGINE ──────────────────────────────────────
  async optimizeResume(data: JDOptimizeRequest): Promise<JDOptimizeResponse> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resume/optimize`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to optimize resume for target job");
    }
    return res.json();
  }

  async getOptimization(id: number): Promise<JDOptimizeResponse> {
    const res = await fetch(`${getApiBaseUrl()}/resume/optimize/${id}`, {
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) throw new Error("Could not retrieve optimization record");
    return res.json();
  }

  getOptimizedPdfUrl(optimizationId: number): string {
    return `${getApiBaseUrl()}/resume/optimize/${optimizationId}/download/pdf`;
  }

  getOptimizedDocxUrl(optimizationId: number): string {
    return `${getApiBaseUrl()}/resume/optimize/${optimizationId}/download/docx`;
  }

  async saveOptimizedResume(optimizationId: number, data: {
    custom_title?: string;
    template_id?: number;
    set_as_active?: boolean;
  }): Promise<{ message: string; resume_id: number; title: string; ats_score: number; pdf_url: string }> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";

    const res = await fetch(`${getApiBaseUrl()}/resume/optimize/${optimizationId}/save-as-resume`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to save optimized resume");
    }
    return res.json();
  }

  async prepareApplication(optimizationId: number): Promise<PreparedApplication> {
    const headers = getAuthHeaders() as Record<string, string>;
    const res = await fetch(`${getApiBaseUrl()}/resume/optimize/${optimizationId}/prepare-application`, {
      method: "POST",
      headers,
      credentials: "include",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to prepare application");
    }
    return res.json();
  }

  async confirmApplication(optimizationId: number, data: { confirmed_fields?: Record<string, any>; user_acknowledged: boolean }): Promise<{ status: string; message: string; prepared_application: PreparedApplication }> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";
    const res = await fetch(`${getApiBaseUrl()}/resume/optimize/${optimizationId}/confirm-application`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to confirm application");
    }
    return res.json();
  }

  async getApplicationResumeSnapshot(applicationId: number): Promise<JDOptimizeResponse> {
    const res = await fetch(`${getApiBaseUrl()}/applications/${applicationId}/resume-snapshot`, {
      headers: getAuthHeaders(),
      credentials: "include",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Could not retrieve resume snapshot for this application");
    }
    return res.json();
  }

  async approveOptimization(optimizationId: number, data: { user_acknowledged: boolean; notes?: string; accepted_warnings?: string[] }): Promise<{ status: string; message: string; optimization_id: number; approved_at: string; approval_hash: string; optimization: JDOptimizeResponse }> {
    const headers = getAuthHeaders() as Record<string, string>;
    headers["Content-Type"] = "application/json";
    const res = await fetch(`${getApiBaseUrl()}/resume/optimize/${optimizationId}/approve`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to approve optimization revision");
    }
    return res.json();
  }
}

export const resumeCenterApi = new ResumeCenterApiService();

