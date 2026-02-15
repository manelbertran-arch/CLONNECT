import { apiFetch, CREATOR_ID } from "./client";

export interface RunNurturingParams {
  dueOnly?: boolean;
  dryRun?: boolean;
  limit?: number;
  forceDue?: boolean;
}

export interface RunNurturingResponse {
  status: string;
  creator_id: string;
  dry_run: boolean;
  would_process?: number;
  items?: Array<{
    followup_id: string;
    follower_id: string;
    sequence_type: string;
    step: number;
    scheduled_at: string;
    message_preview: string;
    channel_guess: string;
  }>;
  processed?: number;
  sent?: number;
  simulated?: number;
  errors?: string[];
  by_sequence?: Record<string, { processed: number; sent: number; simulated: number; errors: number }>;
  stats_after?: { pending: number; sent: number; cancelled: number };
}

export async function getNurturingSequences(creatorId: string = CREATOR_ID): Promise<{ status: string; sequences: any[]; stats: any }> {
  return apiFetch(`/nurturing/${creatorId}/sequences`);
}

export async function getNurturingFollowups(creatorId: string = CREATOR_ID, status?: string): Promise<{ status: string; followups: any[]; count: number }> {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  return apiFetch(`/nurturing/${creatorId}/followups?${params}`);
}

export async function getNurturingStats(creatorId: string = CREATOR_ID): Promise<{ status: string; total: number; pending: number; sent: number; cancelled: number }> {
  return apiFetch(`/nurturing/${creatorId}/stats`);
}

export async function toggleNurturingSequence(creatorId: string = CREATOR_ID, sequenceType: string): Promise<{ status: string; sequence_type: string; is_active: boolean }> {
  return apiFetch(`/nurturing/${creatorId}/sequences/${sequenceType}/toggle`, { method: "POST", body: JSON.stringify({}) });
}

export async function updateNurturingSequence(creatorId: string = CREATOR_ID, sequenceType: string, steps: Array<{ delay_hours: number; message: string }>): Promise<{ status: string; sequence_type: string; steps: any[] }> {
  return apiFetch(`/nurturing/${creatorId}/sequences/${sequenceType}`, { method: "PUT", body: JSON.stringify({ steps }) });
}

export async function getNurturingEnrolled(creatorId: string = CREATOR_ID, sequenceType: string): Promise<{ status: string; enrolled: any[]; count: number }> {
  return apiFetch(`/nurturing/${creatorId}/sequences/${sequenceType}/enrolled`);
}

export async function cancelNurturing(creatorId: string = CREATOR_ID, followerId: string, sequenceType?: string): Promise<{ status: string; cancelled: number }> {
  const params = sequenceType ? `?sequence_type=${sequenceType}` : "";
  return apiFetch(`/nurturing/${creatorId}/cancel/${followerId}${params}`, { method: "DELETE" });
}

export async function runNurturing(creatorId: string = CREATOR_ID, params: RunNurturingParams = {}): Promise<RunNurturingResponse> {
  const queryParams = new URLSearchParams();
  if (params.dueOnly !== undefined) queryParams.append("due_only", String(params.dueOnly));
  if (params.dryRun !== undefined) queryParams.append("dry_run", String(params.dryRun));
  if (params.limit !== undefined) queryParams.append("limit", String(params.limit));
  if (params.forceDue !== undefined) queryParams.append("force_due", String(params.forceDue));
  return apiFetch(`/nurturing/${creatorId}/run?${queryParams}`, { method: "POST" });
}
