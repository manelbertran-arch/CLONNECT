import { apiFetch, CREATOR_ID } from "./client";

export interface ConnectionStatus {
  connected: boolean;
  username?: string;
  masked_token?: string;
  token_expires_at?: string;
  days_remaining?: number;
}

export interface AllConnections {
  instagram: ConnectionStatus;
  telegram: ConnectionStatus;
  whatsapp: ConnectionStatus;
  stripe: ConnectionStatus;
  paypal: ConnectionStatus;
  hotmart: ConnectionStatus;
  calendly: ConnectionStatus;
}

export interface UpdateConnectionData {
  token?: string;
  page_id?: string;
  phone_id?: string;
}

export interface OAuthStartResponse {
  auth_url: string;
  state: string;
}

export async function getConnections(creatorId: string = CREATOR_ID): Promise<AllConnections> {
  return apiFetch(`/connections/${creatorId}`);
}

export async function updateConnection(creatorId: string = CREATOR_ID, platform: string, data: UpdateConnectionData): Promise<{ status: string; platform: string }> {
  return apiFetch(`/connections/${creatorId}/${platform}`, { method: "POST", body: JSON.stringify(data) });
}

export async function disconnectPlatform(creatorId: string = CREATOR_ID, platform: string): Promise<{ status: string; platform: string }> {
  return apiFetch(`/connections/${creatorId}/${platform}`, { method: "DELETE" });
}

export async function startOAuth(platform: string, creatorId: string = CREATOR_ID): Promise<OAuthStartResponse> {
  return apiFetch(`/oauth/${platform}/start?creator_id=${creatorId}`);
}
