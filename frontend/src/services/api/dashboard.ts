import { apiFetch, CREATOR_ID } from "./client";
import type { DashboardOverview, ToggleResponse } from "./client";

export async function getDashboardOverview(creatorId: string = CREATOR_ID): Promise<DashboardOverview> {
  return apiFetch<DashboardOverview>(`/dashboard/${creatorId}/overview`);
}

export async function toggleBot(creatorId: string = CREATOR_ID, active: boolean, reason: string = ""): Promise<ToggleResponse> {
  return apiFetch<ToggleResponse>(
    `/dashboard/${creatorId}/toggle?active=${active}&reason=${encodeURIComponent(reason)}`,
    { method: "PUT" }
  );
}
