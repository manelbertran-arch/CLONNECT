import { apiFetch, CREATOR_ID } from "./client";

export interface ContextMessage {
  role: string;
  content: string;
  timestamp: string;
}

export interface CopilotCandidate {
  content: string;
  temperature: number;
  confidence: number;
  rank: number;
}

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
  conversation_context?: ContextMessage[];
  candidates?: CopilotCandidate[];
  confidence?: number;
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

export async function getCopilotPending(creatorId: string = CREATOR_ID, limit: number = 500): Promise<{ creator_id: string; pending_count: number; pending_responses: PendingResponse[] }> {
  return apiFetch(`/copilot/${creatorId}/pending?limit=${limit}`);
}

export async function getCopilotStatus(creatorId: string = CREATOR_ID): Promise<CopilotStatus> {
  return apiFetch(`/copilot/${creatorId}/status`);
}

export async function approveCopilotResponse(creatorId: string = CREATOR_ID, messageId: string, editedText?: string, chosenIndex?: number): Promise<{ success: boolean; message_id: string; was_edited: boolean; final_text: string }> {
  return apiFetch(`/copilot/${creatorId}/approve/${messageId}`, { method: "POST", body: JSON.stringify({ edited_text: editedText, chosen_index: chosenIndex }) });
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

export async function getPendingForLead(creatorId: string = CREATOR_ID, leadId: string): Promise<{ pending: PendingResponse | null }> {
  return apiFetch(`/copilot/${creatorId}/pending-for-lead/${leadId}`);
}

export async function discardAllCopilot(creatorId: string = CREATOR_ID): Promise<{ success: boolean; discarded_count: number }> {
  return apiFetch(`/copilot/${creatorId}/discard-all`, { method: "POST" });
}

export interface CopilotStats {
  creator_id: string;
  period_days: number;
  total_actions: number;
  approved: number;
  edited: number;
  discarded: number;
  manual_override: number;
  approval_rate: number;
  edit_rate: number;
  discard_rate: number;
  manual_rate: number;
  avg_response_time_ms: number | null;
  avg_confidence: number | null;
  edit_categories: Record<string, number>;
}

export interface CopilotComparison {
  message_id: string;
  bot_original: string;
  creator_final: string;
  action: string;
  edit_diff: { length_delta: number; categories: string[] } | null;
  confidence: number | null;
  response_time_ms: number | null;
  created_at: string;
  username: string;
  platform: string;
  is_identical?: boolean;
  source?: string;
}

export async function getCopilotStats(creatorId: string = CREATOR_ID, days: number = 30): Promise<CopilotStats> {
  return apiFetch(`/copilot/${creatorId}/stats?days=${days}`);
}

export async function getCopilotComparisons(creatorId: string = CREATOR_ID, limit: number = 500): Promise<{ creator_id: string; comparisons: CopilotComparison[]; count: number; has_more: boolean }> {
  return apiFetch(`/copilot/${creatorId}/comparisons?limit=${limit}`);
}
