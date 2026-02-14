import { apiFetch } from "./client";

export interface TopicAggregation {
  topic: string;
  count: number;
  percentage: number;
  quotes: string[];
  users: string[];
}

export interface ObjectionAggregation {
  objection: string;
  count: number;
  percentage: number;
  quotes: string[];
  suggestion: string;
  resolved_count: number;
  pending_count: number;
}

export interface CompetitionMention {
  competitor: string;
  count: number;
  sentiment: "positivo" | "neutral" | "negativo";
  context: string[];
  suggestion: string;
}

export interface TrendItem {
  term: string;
  count_this_week: number;
  count_last_week: number;
  growth_percentage: number;
  quotes: string[];
}

export interface ContentRequest {
  topic: string;
  count: number;
  questions: string[];
  suggestion: string;
}

export interface PerceptionItem {
  aspect: string;
  positive_count: number;
  negative_count: number;
  quotes_positive: string[];
  quotes_negative: string[];
}

export interface TopicsResponse {
  total_conversations: number;
  topics: TopicAggregation[];
}

export interface ObjectionsResponse {
  total_with_objections: number;
  objections: ObjectionAggregation[];
}

export interface CompetitionResponse {
  total_mentions: number;
  competitors: CompetitionMention[];
}

export interface TrendsResponse {
  period: string;
  trends: TrendItem[];
}

export interface ContentRequestsResponse {
  total_requests: number;
  requests: ContentRequest[];
}

export interface PerceptionResponse {
  total_analyzed: number;
  perceptions: PerceptionItem[];
}

export async function getAudienciaTopics(creatorId: string, limit: number = 10): Promise<TopicsResponse> {
  return apiFetch(`/audiencia/${creatorId}/topics?limit=${limit}`);
}

export async function getAudienciaPassions(creatorId: string, limit: number = 10): Promise<TopicsResponse> {
  return apiFetch(`/audiencia/${creatorId}/passions?limit=${limit}`);
}

export async function getAudienciaFrustrations(creatorId: string, limit: number = 10): Promise<ObjectionsResponse> {
  return apiFetch(`/audiencia/${creatorId}/frustrations?limit=${limit}`);
}

export async function getAudienciaCompetition(creatorId: string, limit: number = 10): Promise<CompetitionResponse> {
  return apiFetch(`/audiencia/${creatorId}/competition?limit=${limit}`);
}

export async function getAudienciaTrends(creatorId: string, limit: number = 10): Promise<TrendsResponse> {
  return apiFetch(`/audiencia/${creatorId}/trends?limit=${limit}`);
}

export async function getAudienciaContentRequests(creatorId: string, limit: number = 10): Promise<ContentRequestsResponse> {
  return apiFetch(`/audiencia/${creatorId}/content-requests?limit=${limit}`);
}

export async function getAudienciaPurchaseObjections(creatorId: string, limit: number = 10): Promise<ObjectionsResponse> {
  return apiFetch(`/audiencia/${creatorId}/purchase-objections?limit=${limit}`);
}

export async function getAudienciaPerception(creatorId: string): Promise<PerceptionResponse> {
  return apiFetch(`/audiencia/${creatorId}/perception`);
}
