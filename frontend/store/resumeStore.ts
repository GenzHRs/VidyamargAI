import { create } from "zustand";
import { apiService } from "@/services/api";
import { resumeCenterApi } from "@/services/resumeCenterApi";
import { useDashboardStore } from "./dashboardStore";

export interface ActiveResumeInfo {
  id: number;
  title: string;
  source_type: string;
  template_id?: number;
  current_version_id?: number;
  file_name?: string;
  original_file_url?: string;
  latest_pdf_url?: string;
  is_active: boolean;
  status: string;
  created_at?: string;
  updated_at?: string;
}

export interface ResumeState {
  hasResume: boolean;
  activeResume: ActiveResumeInfo | null;
  primaryDesignation: string | null;
  targetRoles: string[];
  roleEvidence: any[];
  structuredData: Record<string, any> | null;
  draftData: Record<string, any> | null;
  isDirty: boolean;
  candidateId: number | null;
  versionNumber: number;
  isLoading: boolean;
  error: string | null;

  fetchActiveResume: () => Promise<void>;
  setActiveResume: (resumeId: number) => Promise<boolean>;
  replaceResume: (file: File) => Promise<{ success: boolean; message: string }>;
  updateDraftField: (fieldPath: string, value: any) => { prevValue: any; newValue: any };
  saveDraft: () => Promise<boolean>;
  resetDraft: () => void;
}

export const useResumeStore = create<ResumeState>((set, get) => ({
  hasResume: false,
  activeResume: null,
  primaryDesignation: null,
  targetRoles: [],
  roleEvidence: [],
  structuredData: null,
  draftData: null,
  isDirty: false,
  candidateId: null,
  versionNumber: 1,
  isLoading: true,
  error: null,

  fetchActiveResume: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await apiService.getActiveResume();
      if (res && res.has_resume) {
        const sData = res.structured_data || {};
        set({
          hasResume: true,
          activeResume: res.active_resume,
          primaryDesignation: res.primary_designation || null,
          targetRoles: res.target_roles || [],
          roleEvidence: res.role_evidence || [],
          structuredData: sData,
          draftData: JSON.parse(JSON.stringify(sData)),
          isDirty: false,
          candidateId: res.candidate_id,
          versionNumber: res.version_number || 1,
          isLoading: false,
        });
      } else {
        set({
          hasResume: false,
          activeResume: null,
          primaryDesignation: null,
          targetRoles: [],
          roleEvidence: [],
          structuredData: null,
          draftData: null,
          isDirty: false,
          isLoading: false,
        });
      }
    } catch (err: any) {
      console.error("Failed to fetch global active resume:", err);
      set({ isLoading: false, error: err.message || "Failed to load active resume" });
    }
  },

  setActiveResume: async (resumeId: number) => {
    try {
      await apiService.setActiveResume(resumeId);
      await get().fetchActiveResume();
      apiService.invalidateDashboardSummary();
      useDashboardStore.getState().invalidateDashboard();
      return true;
    } catch (err: any) {
      console.error("Failed to set active resume:", err);
      return false;
    }
  },

  replaceResume: async (file: File) => {
    set({ isLoading: true, error: null });
    try {
      const res = await resumeCenterApi.uploadResume(file);
      await get().fetchActiveResume();
      apiService.invalidateDashboardSummary();
      useDashboardStore.getState().invalidateDashboard();
      set({ isLoading: false });
      return {
        success: true,
        message: res.message || "Resume updated successfully. Your new resume is now active."
      };
    } catch (err: any) {
      console.error("Failed to replace active resume:", err);
      const errDetail = err.response?.data?.detail || err.message || "New resume could not be processed. Your current resume is still active.";
      set({ isLoading: false, error: errDetail });
      return {
        success: false,
        message: errDetail
      };
    }
  },

  updateDraftField: (fieldPath: string, value: any) => {
    const state = get();
    const currentDraft = state.draftData ? JSON.parse(JSON.stringify(state.draftData)) : {};
    let prevValue: any = undefined;

    // Field path resolution (e.g., "designation", "resume.designation", "experience[0].designation")
    const cleanPath = fieldPath.replace(/^resume\./, "");
    
    // Check if modifying root field or nested array field
    const expMatch = cleanPath.match(/^experience\[(\d+)\]\.(.+)$/);
    if (expMatch && Array.isArray(currentDraft.experience)) {
      const idx = parseInt(expMatch[1], 10);
      const subProp = expMatch[2];
      if (currentDraft.experience[idx]) {
        prevValue = currentDraft.experience[idx][subProp];
        currentDraft.experience[idx][subProp] = value;
      }
    } else {
      prevValue = currentDraft[cleanPath];
      currentDraft[cleanPath] = value;
    }

    set({
      draftData: currentDraft,
      isDirty: true,
    });

    return { prevValue, newValue: value };
  },

  saveDraft: async () => {
    const state = get();
    if (!state.isDirty || !state.draftData) return true;

    try {
      await apiService.updateProfile(state.draftData);
      set({
        structuredData: JSON.parse(JSON.stringify(state.draftData)),
        isDirty: false,
      });
      return true;
    } catch (err) {
      console.error("Failed to persist resume draft:", err);
      return false;
    }
  },

  resetDraft: () => {
    const state = get();
    if (state.structuredData) {
      set({
        draftData: JSON.parse(JSON.stringify(state.structuredData)),
        isDirty: false,
      });
    }
  },
}));
