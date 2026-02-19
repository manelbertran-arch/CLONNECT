import { apiFetch, CREATOR_ID } from "./client";

export interface VisualOnboardingStatus {
  status: string;
  onboarding_completed: boolean;
}

export async function getVisualOnboardingStatus(creatorId: string = CREATOR_ID): Promise<VisualOnboardingStatus> {
  return apiFetch(`/onboarding/${creatorId}/visual-status`);
}

export async function completeVisualOnboarding(creatorId: string = CREATOR_ID): Promise<{ status: string; message: string }> {
  return apiFetch(`/onboarding/${creatorId}/complete`, { method: "POST" });
}
