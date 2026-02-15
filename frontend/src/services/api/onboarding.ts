import { apiFetch, CREATOR_ID } from "./client";

export interface VisualOnboardingStatus {
  status: string;
  onboarding_completed: boolean;
}

export interface SetupProgress {
  status: "not_started" | "in_progress" | "completed" | "error";
  progress: number;
  current_step?: string;
  steps: {
    instagram_connected: boolean;
    posts_imported: number;
    tone_profile_generated: boolean;
    tone_summary: string | null;
    content_indexed: number;
    dms_imported: number;
    leads_created: number;
    youtube_detected: boolean;
    youtube_videos_imported: number;
    website_detected: boolean;
    website_url: string | null;
  };
  errors: string[];
}

export async function getVisualOnboardingStatus(creatorId: string = CREATOR_ID): Promise<VisualOnboardingStatus> {
  return apiFetch(`/onboarding/${creatorId}/visual-status`);
}

export async function completeVisualOnboarding(creatorId: string = CREATOR_ID): Promise<{ status: string; message: string }> {
  return apiFetch(`/onboarding/${creatorId}/complete`, { method: "POST" });
}

export async function startFullSetup(creatorId: string = CREATOR_ID): Promise<{ status: string; message: string; creator_id: string }> {
  return apiFetch(`/onboarding/full-setup/${creatorId}`, { method: "POST" });
}

export async function getSetupProgress(creatorId: string = CREATOR_ID): Promise<SetupProgress> {
  return apiFetch(`/onboarding/full-setup/${creatorId}/progress`);
}
