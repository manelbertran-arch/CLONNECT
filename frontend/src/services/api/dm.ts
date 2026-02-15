import { apiFetch, CREATOR_ID } from "./client";
import type { ConversationsResponse, FollowerDetailResponse } from "./client";

export interface CreateLeadData {
  name: string;
  platform?: string;
  email?: string;
  phone?: string;
  notes?: string;
}

export interface UpdateLeadData {
  name?: string;
  email?: string;
  phone?: string;
  notes?: string;
  status?: string;
}

// Conversation type for archived responses
interface Conversation {
  follower_id: string;
  [key: string]: any;
}

export async function getConversations(creatorId: string = CREATOR_ID, limit: number = 50, offset: number = 0): Promise<ConversationsResponse> {
  return apiFetch<ConversationsResponse>(`/dm/conversations/${creatorId}?limit=${limit}&offset=${offset}`);
}

export async function getLeads(creatorId: string = CREATOR_ID): Promise<any> {
  return apiFetch(`/dm/leads/${creatorId}`);
}

export async function getMetrics(creatorId: string = CREATOR_ID): Promise<any> {
  return apiFetch(`/dm/metrics/${creatorId}`);
}

export async function getFollowerDetail(creatorId: string = CREATOR_ID, followerId: string): Promise<FollowerDetailResponse> {
  return apiFetch<FollowerDetailResponse>(`/dm/follower/${creatorId}/${followerId}`);
}

export async function sendMessage(creatorId: string = CREATOR_ID, followerId: string, message: string): Promise<{ status: string; sent: boolean; platform: string; follower_id: string }> {
  return apiFetch(`/dm/send/${creatorId}`, { method: "POST", body: JSON.stringify({ follower_id: followerId, message }) });
}

export async function markConversationRead(creatorId: string = CREATOR_ID, followerId: string): Promise<{ status: string; message: string }> {
  return apiFetch(`/dm/conversations/${creatorId}/${followerId}/mark-read`, { method: "POST" });
}

export async function updateLeadStatus(creatorId: string = CREATOR_ID, followerId: string, status: string): Promise<{ status: string; follower_id: string; new_status: string; purchase_intent: number }> {
  return apiFetch(`/dm/follower/${creatorId}/${followerId}/status`, { method: "PUT", body: JSON.stringify({ status }) });
}

export async function createManualLead(creatorId: string = CREATOR_ID, data: CreateLeadData): Promise<{ status: string; lead: any }> {
  return apiFetch(`/dm/leads/${creatorId}/manual`, { method: "POST", body: JSON.stringify(data) });
}

export async function updateLead(creatorId: string = CREATOR_ID, leadId: string, data: UpdateLeadData): Promise<{ status: string; lead: any }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function deleteLead(creatorId: string = CREATOR_ID, leadId: string): Promise<{ status: string; deleted: boolean; lead_id: string }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}`, { method: "DELETE" });
}

export async function archiveConversation(creatorId: string = CREATOR_ID, conversationId: string): Promise<{ status: string }> {
  return apiFetch(`/dm/conversations/${creatorId}/${conversationId}/archive`, { method: "POST" });
}

export async function markConversationSpam(creatorId: string = CREATOR_ID, conversationId: string): Promise<{ status: string }> {
  return apiFetch(`/dm/conversations/${creatorId}/${conversationId}/spam`, { method: "POST" });
}

export async function deleteConversation(creatorId: string = CREATOR_ID, conversationId: string): Promise<{ status: string }> {
  return apiFetch(`/dm/conversations/${creatorId}/${conversationId}`, { method: "DELETE" });
}

export async function getArchivedConversations(creatorId: string = CREATOR_ID): Promise<{ status: string; conversations: Conversation[] }> {
  return apiFetch(`/dm/conversations/${creatorId}/archived`);
}

export async function restoreConversation(creatorId: string = CREATOR_ID, conversationId: string): Promise<{ status: string; restored?: boolean }> {
  return apiFetch(`/dm/conversations/${creatorId}/${conversationId}/restore`, { method: "POST" });
}
