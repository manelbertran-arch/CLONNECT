import { apiFetch } from "./client";

export interface AudienceProfile {
  follower_id: string;
  username?: string;
  name?: string;
  platform?: string;
  profile_pic_url?: string;
  first_contact?: string;
  last_contact?: string;
  total_messages: number;
  interests: string[];
  products_discussed: string[];
  purchase_intent_score: number;
  is_lead: boolean;
  is_customer: boolean;
  funnel_phase?: string;
  funnel_context: Record<string, unknown>;
  narrative?: string;
  segments: string[];
  recommended_action?: string;
  action_priority?: 'low' | 'medium' | 'high' | 'urgent';
  objections: Array<{ type: string; handled: boolean; suggestion: string }>;
  days_inactive: number;
  last_message_role?: string;
  email?: string;
  phone?: string;
  notes?: string;
  deal_value?: number;
  tags: string[];
}

export interface SegmentCount {
  segment: string;
  count: number;
}

export interface AggregatedMetrics {
  total_followers: number;
  top_interests: Array<{ interest: string; count: number }>;
  top_objections: Array<{ objection: string; count: number }>;
  funnel_distribution: Record<string, number>;
}

export async function getAudienceProfile(creatorId: string, followerId: string): Promise<AudienceProfile> {
  return apiFetch(`/audience/${creatorId}/profile/${followerId}`);
}

export async function getAudienceSegments(creatorId: string): Promise<SegmentCount[]> {
  return apiFetch(`/audience/${creatorId}/segments`);
}

export async function getAudienceSegmentUsers(creatorId: string, segmentName: string, limit: number = 20): Promise<AudienceProfile[]> {
  return apiFetch(`/audience/${creatorId}/segments/${segmentName}?limit=${limit}`);
}

export async function getAudienceAggregated(creatorId: string): Promise<AggregatedMetrics> {
  return apiFetch(`/audience/${creatorId}/aggregated`);
}
