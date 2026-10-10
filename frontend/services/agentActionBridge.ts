import { AppRouterInstance } from "next/dist/shared/lib/app-router-context.shared-runtime";
import { useResumeStore } from "@/store/resumeStore";
import { useAuthStore } from "@/store/authStore";
import { useGlobalAgentStore } from "@/store/globalAgentStore";
import { apiService } from "@/services/api";
import { APP_ROUTES } from "@/config/routes";

export interface AgentCommand {
  command_id: string;
  workflow_id?: string;
  tool: string;
  arguments: Record<string, any>;
  dependencies?: string[];
}

export interface CommandExecutionResult {
  command_id: string;
  status: "succeeded" | "failed" | "cancelled";
  output?: Record<string, any>;
  verification_evidence?: Record<string, any>;
  error?: string;
}

export interface BoundedUIState {
  current_route: string;
  page_ready: boolean;
  active_resume_id: number | null;
  active_job_id: number | null;
  theme: "dark" | "light";
  is_dirty: boolean;
  draft_designation: string | null;
  draft_company: string | null;
  is_agent_open: boolean;
}

class AgentActionBridgeService {
  private router: AppRouterInstance | null = null;
  private activeJobId: number | null = null;
  private activeAppId: number | null = null;
  private activeCourseId: number | null = null;
  private activeInterviewId: number | null = null;

  public registerRouter(routerInstance: AppRouterInstance) {
    this.router = routerInstance;
  }

  public unregisterRouter() {
    this.router = null;
  }

  public get_ui_state(): BoundedUIState {
    const pathname = typeof window !== "undefined" ? window.location.pathname : "/candidate/dashboard";
    const resumeStore = useResumeStore.getState();
    const globalAgentStore = useGlobalAgentStore.getState();

    const isDark = typeof document !== "undefined" && document.documentElement.classList.contains("dark");
    const draftData = resumeStore.draftData || {};

    return {
      current_route: pathname,
      page_ready: true,
      active_resume_id: resumeStore.activeResume?.id ?? null,
      active_job_id: this.activeJobId,
      theme: isDark ? "dark" : "light",
      is_dirty: resumeStore.isDirty,
      draft_designation: draftData.designation || (draftData.experience?.[0]?.designation ?? null),
      draft_company: draftData.company || (draftData.experience?.[0]?.company ?? null),
      is_agent_open: globalAgentStore.isOpen,
    };
  }

  public async executeCommand(cmd: AgentCommand): Promise<CommandExecutionResult> {
    const { command_id, tool, arguments: args } = cmd;

    try {
      switch (tool) {
        case "navigate_to_route": {
          const targetPath = args.path || args.route || APP_ROUTES.dashboard;
          if (!this.router) {
            return {
              command_id,
              status: "failed",
              error: "Router instance not registered with AgentActionBridge",
            };
          }

          this.router.push(targetPath);

          // Bounded navigation verification (destination readiness check)
          await new Promise((resolve) => setTimeout(resolve, 300));
          const uiState = this.get_ui_state();
          const routeMatched = uiState.current_route === targetPath || uiState.current_route.startsWith(targetPath);

          return {
            command_id,
            status: routeMatched ? "succeeded" : "failed",
            output: { route: targetPath },
            verification_evidence: {
              current_route: uiState.current_route,
              page_ready: uiState.page_ready,
            },
            error: routeMatched ? undefined : `Navigation initiated but active route is ${uiState.current_route}`,
          };
        }

        case "change_theme": {
          const targetTheme = (args.theme || "dark").toLowerCase() === "dark" ? "dark" : "light";
          if (typeof document !== "undefined") {
            if (targetTheme === "dark") {
              document.documentElement.classList.add("dark");
              document.documentElement.classList.remove("light-theme");
            } else {
              document.documentElement.classList.remove("dark");
              document.documentElement.classList.add("light-theme");
            }
            localStorage.setItem("theme", targetTheme);
            // Dispatch CustomEvent — this is what useGlobalTheme listens to
            window.dispatchEvent(new CustomEvent("theme-change", { detail: targetTheme }));
          }
          apiService.updatePreferences(targetTheme).catch(() => {});

          const uiState = this.get_ui_state();
          const verified = uiState.theme === targetTheme;

          return {
            command_id,
            status: verified ? "succeeded" : "failed",
            output: { theme: targetTheme },
            verification_evidence: { theme: uiState.theme },
          };
        }

        case "open_resume": {
          const resumeStore = useResumeStore.getState();
          const targetId = args.resume_id || args.id || resumeStore.activeResume?.id;
          if (targetId && targetId !== resumeStore.activeResume?.id) {
            await resumeStore.setActiveResume(targetId);
          }
          if (this.router) {
            this.router.push(APP_ROUTES.resume);
          }
          await new Promise((resolve) => setTimeout(resolve, 200));

          const uiState = this.get_ui_state();
          return {
            command_id,
            status: "succeeded",
            output: { resume_id: uiState.active_resume_id },
            verification_evidence: {
              current_route: uiState.current_route,
              active_resume_id: uiState.active_resume_id,
            },
          };
        }

        case "fill_form_field": {
          const field = args.field || args.field_path || "";
          const value = args.value ?? "";
          if (!field) {
            return {
              command_id,
              status: "failed",
              error: "Field path is required for fill_form_field",
            };
          }

          const resumeStore = useResumeStore.getState();
          const { prevValue, newValue } = resumeStore.updateDraftField(field, value);

          const uiState = this.get_ui_state();
          return {
            command_id,
            status: "succeeded",
            output: {
              field,
              previous_value: prevValue,
              new_value: newValue,
              status_message: "Updated in your draft",
            },
            verification_evidence: {
              is_dirty: uiState.is_dirty,
              draft_designation: uiState.draft_designation,
              draft_company: uiState.draft_company,
            },
          };
        }

        case "save_resume": {
          const resumeStore = useResumeStore.getState();
          const saved = await resumeStore.saveDraft();

          const uiState = this.get_ui_state();
          return {
            command_id,
            status: saved ? "succeeded" : "failed",
            output: {
              saved,
              status_message: saved ? "Saved" : "Failed to persist draft",
            },
            verification_evidence: {
              is_dirty: uiState.is_dirty,
              active_resume_id: uiState.active_resume_id,
            },
            error: saved ? undefined : "Save operation failed on backend database",
          };
        }

        case "open_job": {
          this.activeJobId = args.job_id || args.id || null;
          if (this.router) {
            this.router.push(APP_ROUTES.jobs);
          }
          await new Promise((resolve) => setTimeout(resolve, 200));
          const uiState = this.get_ui_state();

          return {
            command_id,
            status: "succeeded",
            output: { job_id: this.activeJobId },
            verification_evidence: {
              current_route: uiState.current_route,
              active_job_id: this.activeJobId,
            },
          };
        }

        case "open_application": {
          this.activeAppId = args.application_id || args.id || null;
          if (this.router) {
            this.router.push(APP_ROUTES.applications);
          }
          await new Promise((resolve) => setTimeout(resolve, 200));
          const uiState = this.get_ui_state();

          return {
            command_id,
            status: "succeeded",
            output: { application_id: this.activeAppId },
            verification_evidence: { current_route: uiState.current_route },
          };
        }

        case "open_course": {
          this.activeCourseId = args.course_id || args.id || null;
          if (this.router) {
            this.router.push(APP_ROUTES.courses);
          }
          await new Promise((resolve) => setTimeout(resolve, 200));
          const uiState = this.get_ui_state();

          return {
            command_id,
            status: "succeeded",
            output: { course_id: this.activeCourseId },
            verification_evidence: { current_route: uiState.current_route },
          };
        }

        case "open_interview": {
          this.activeInterviewId = args.interview_id || args.id || null;
          if (this.router) {
            this.router.push(APP_ROUTES.interview);
          }
          await new Promise((resolve) => setTimeout(resolve, 200));
          const uiState = this.get_ui_state();

          return {
            command_id,
            status: "succeeded",
            output: { interview_id: this.activeInterviewId },
            verification_evidence: { current_route: uiState.current_route },
          };
        }

        case "read_page_context":
        case "get_ui_state": {
          const uiState = this.get_ui_state();
          return {
            command_id,
            status: "succeeded",
            output: uiState as any,
            verification_evidence: { current_route: uiState.current_route },
          };
        }

        default:
          return {
            command_id,
            status: "failed",
            error: `Tool '${tool}' is not registered with AgentActionBridge`,
          };
      }
    } catch (err: any) {
      return {
        command_id,
        status: "failed",
        error: err.message || `Error executing command ${tool}`,
      };
    }
  }
}

export const AgentActionBridge = new AgentActionBridgeService();
