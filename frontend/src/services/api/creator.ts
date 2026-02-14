import { apiFetch, CREATOR_ID } from "./client";
import type { CreatorConfig } from "./client";

export interface ToneProfile {
  formality: number;
  energy: number;
  warmth: number;
  emoji_usage: number;
  summary: string;
  generated_at?: string;
}

export interface ContentStats {
  posts_count: number;
  videos_count: number;
  pdfs_count: number;
  audios_count: number;
  total_indexed: number;
}

export interface TestCloneResponse {
  status: string;
  response: string;
  sources?: string[];
  tone_applied: boolean;
}

export async function getCreatorConfig(creatorId: string = CREATOR_ID): Promise<{ status: string; config: CreatorConfig }> {
  return apiFetch(`/creator/config/${creatorId}`);
}

export async function updateCreatorConfig(creatorId: string = CREATOR_ID, config: Partial<CreatorConfig>): Promise<{ status: string; config: CreatorConfig }> {
  return apiFetch(`/creator/config/${creatorId}`, { method: "PUT", body: JSON.stringify(config) });
}

export async function getToneProfile(creatorId: string = CREATOR_ID): Promise<{ status: string; tone_profile: ToneProfile | null }> {
  return apiFetch(`/creator/${creatorId}/tone-profile`);
}

export async function regenerateToneProfile(creatorId: string = CREATOR_ID): Promise<{ status: string; tone_profile: ToneProfile; message: string }> {
  return apiFetch(`/creator/${creatorId}/tone-profile/regenerate`, { method: "POST" });
}

export async function getContentStats(creatorId: string = CREATOR_ID): Promise<{ status: string; stats: ContentStats }> {
  return apiFetch(`/creator/${creatorId}/content-stats`);
}

export async function testClone(creatorId: string = CREATOR_ID, message: string): Promise<TestCloneResponse> {
  return apiFetch(`/clone/${creatorId}/test`, { method: "POST", body: JSON.stringify({ message }) });
}
