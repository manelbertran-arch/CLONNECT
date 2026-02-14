import { apiFetch } from "./client";

export interface HotLeadAction {
  follower_id: string;
  name: string;
  username: string;
  profile_pic_url?: string;
  last_message: string;
  hours_ago: number;
  product?: string;
  deal_value: number;
  context: string;
  action: string;
  purchase_intent_score: number;
}

export interface BookingInfo {
  id: string;
  title: string;
  time: string;
  attendee_name: string;
  attendee_email?: string;
  platform: string;
}

export interface TodayMission {
  potential_revenue: number;
  hot_leads: HotLeadAction[];
  pending_responses: number;
  today_bookings: BookingInfo[];
  ghost_reactivation_count: number;
}

export interface ContentInsight {
  topic: string;
  count: number;
  percentage: number;
  quotes: string[];
  suggestion: string;
}

export interface TrendInsight {
  term: string;
  count: number;
  growth: string;
  suggestion: string;
}

export interface ProductInsight {
  product_name: string;
  count: number;
  potential_revenue: number;
  suggestion: string;
}

export interface CompetitionInsight {
  competitor: string;
  count: number;
  sentiment: string;
  suggestion: string;
}

export interface WeeklyInsights {
  content?: ContentInsight;
  trend?: TrendInsight;
  product?: ProductInsight;
  competition?: CompetitionInsight;
}

export interface WeeklyMetrics {
  revenue: number;
  revenue_delta: number;
  sales_count: number;
  sales_delta: number;
  response_rate: number;
  response_delta: number;
  hot_leads_count: number;
  conversations_count: number;
  new_leads_count: number;
}

export async function getTodayMission(creatorId: string): Promise<TodayMission> {
  return apiFetch(`/insights/${creatorId}/today`);
}

export async function getWeeklyInsights(creatorId: string): Promise<WeeklyInsights> {
  return apiFetch(`/insights/${creatorId}/weekly`);
}

export async function getWeeklyMetrics(creatorId: string): Promise<WeeklyMetrics> {
  return apiFetch(`/insights/${creatorId}/metrics`);
}
