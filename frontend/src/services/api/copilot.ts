import { apiFetch, CREATOR_ID } from "./client";

export interface PendingResponse {
  id: string;
  lead_id: string;
  follower_id: string;
  platform: string;
  username: string;
  full_name: string;
  user_message: string;
  suggested_response: string;
  intent: string;
  created_at: string;
  status: string;
}

export interface CopilotStatus {
  creator_id: string;
  copilot_enabled: boolean;
  pending_count: number;
  status: string;
}

export interface CopilotNotifications {
  creator_id: string;
  timestamp: string;
  new_messages_count: number;
  new_messages: any[];
  pending_count: number;
  pending_responses: PendingResponse[];
  hot_leads_count: number;
  hot_leads: any[];
}

export async function getCopilotPending(creatorId: string = CREATOR_ID, limit: number = 50): Promise<{ creator_id: string; pending_count: number; pending_responses: PendingResponse[] }> {
  return apiFetch(`/copilot/${creatorId}/pending?limit=${limit}`);
}

export async function getCopilotStatus(creatorId: string = CREATOR_ID): Promise<CopilotStatus> {
  return apiFetch(`/copilot/${creatorId}/status`);
}

export async function approveCopilotResponse(creatorId: string = CREATOR_ID, messageId: string, editedText?: string): Promise<{ success: boolean; message_id: string; was_edited: boolean; final_text: string }> {
  return apiFetch(`/copilot/${creatorId}/approve/${messageId}`, { method: "POST", body: JSON.stringify({ edited_text: editedText }) });
}

export async function discardCopilotResponse(creatorId: string = CREATOR_ID, messageId: string): Promise<{ success: boolean; message_id: string }> {
  return apiFetch(`/copilot/${creatorId}/discard/${messageId}`, { method: "POST" });
}

export async function toggleCopilotMode(creatorId: string = CREATOR_ID, enabled: boolean): Promise<{ creator_id: string; copilot_enabled: boolean; message: string }> {
  return apiFetch(`/copilot/${creatorId}/toggle`, { method: "PUT", body: JSON.stringify({ enabled }) });
}

export async function getCopilotNotifications(creatorId: string = CREATOR_ID, since?: string): Promise<CopilotNotifications> {
  const params = since ? `?since=${encodeURIComponent(since)}` : "";
  return apiFetch(`/copilot/${creatorId}/notifications${params}`);
}

export async function approveAllCopilot(creatorId: string = CREATOR_ID): Promise<{ creator_id: string; results: { approved: number; failed: number; errors: any[] } }> {
  return apiFetch(`/copilot/${creatorId}/approve-all`, { method: "POST" });
}
