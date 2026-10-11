/**
 * AI Application Autofill API Client
 * Provides frontend methods for AI Application Form filling and entitlement checks.
 */

import { getBaseUrl } from "@/services/api";

function getAuthHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    "Accept": "application/json",
    "Content-Type": "application/json",
  };
  const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export interface MappedFieldDetail {
  label: string;
  value: string;
  is_available: boolean;
}

export interface AutofillMapResponse {
  status: string;
  message: string;
  can_autofill: boolean;
  upgrade_required?: boolean;
  user_subscription?: string;
  active_resume_title?: string;
  mapped_fields: Record<string, MappedFieldDetail>;
  review_prompt?: string;
}

export interface SemanticQuestionResponse {
  status: string;
  question?: string;
  answer?: string;
  message?: string;
}

export const autofillApi = {
  async checkEntitlement(): Promise<{ can_autofill: boolean; subscription_tier: string; message: string }> {
    const res = await fetch(`${getBaseUrl()}/applications/autofill/status`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) throw new Error("Failed to check entitlement");
    return res.json();
  },

  async mapForm(targetUrl?: string, fields?: Array<{ id?: string; name?: string; label?: string }>): Promise<AutofillMapResponse> {
    const res = await fetch(`${getBaseUrl()}/applications/autofill/map`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({
        target_url: targetUrl,
        form_fields: fields || []
      })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "AI Application Autofill requires Plus or Pro subscription.");
    }
    return res.json();
  },

  async answerQuestion(question: string): Promise<SemanticQuestionResponse> {
    const res = await fetch(`${getBaseUrl()}/applications/autofill/semantic-question`, {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ question })
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Failed to answer semantic question.");
    }
    return res.json();
  }
};
