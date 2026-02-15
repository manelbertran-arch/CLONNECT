import { apiFetch, getCreatorId } from "./client";

export interface LeadPrediction {
  lead_id: string;
  username: string;
  status: string;
  conversion_probability: number;
  confidence: number;
  factors: { engagement_level: number; current_score: number; days_since_last_activity: number };
  recommended_action: string;
}

export interface ChurnRisk {
  lead_id: string;
  username: string;
  status: string;
  churn_risk: number;
  days_inactive: number;
  recovery_action: string;
}

export interface RevenueForecast {
  current_weekly_avg: number;
  growth_trend: number;
  forecasts: Array<{ week: number; projected_revenue: number; confidence: number }>;
}

export interface Recommendation {
  category: 'content' | 'action' | 'product' | 'pricing' | 'timing';
  priority: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  reasoning?: string;
  data_points?: Record<string, any>;
  expected_impact?: Record<string, string | number>;
  action_type?: string;
  action_data?: Record<string, any>;
}

export interface IntelligenceDashboardResponse {
  status: string;
  creator_id: string;
  generated_at: string;
  analysis_period_days: number;
  patterns: {
    temporal: {
      best_hours: Array<{ hour: number; messages: number; users: number }>;
      best_days: Array<{ day: string; messages: number; users: number }>;
      peak_activity_hour: number;
      peak_activity_day: string;
    };
    conversation: {
      intent_distribution: Record<string, number>;
      avg_messages_per_user: number;
      max_messages_per_user: number;
    };
    conversion: {
      top_products_mentioned: Array<{ name: string; mentions: number }>;
    };
  };
  predictions: {
    hot_leads: LeadPrediction[];
    total_hot_leads: number;
    churn_risks: ChurnRisk[];
    total_at_risk: number;
    revenue_forecast: RevenueForecast;
  };
  recommendations: Recommendation[];
  kpis: {
    peak_activity_hour: number;
    peak_activity_day: string;
    avg_messages_per_user: number;
    intent_distribution: Record<string, number>;
  };
}

export interface WeeklyReportResponse {
  status: string;
  creator_id: string;
  report: {
    period: { start: string; end: string };
    metrics_summary: {
      conversations: number; messages: number; new_leads: number;
      conversions: number; revenue: number; conversion_rate: number;
    };
    vs_previous_week: Record<string, number>;
    patterns: Record<string, any>;
    predictions: {
      hot_leads: LeadPrediction[];
      churn_risks: ChurnRisk[];
      revenue_forecast: RevenueForecast;
    };
    recommendations: {
      content: Recommendation[];
      actions: Recommendation[];
      products: Recommendation[];
    };
    executive_summary: string;
    key_wins: string[];
    areas_to_improve: string[];
    this_week_focus: string[];
  };
}

export async function getIntelligenceDashboard(creatorId: string = getCreatorId(), days: number = 30): Promise<IntelligenceDashboardResponse> {
  return apiFetch(`/intelligence/${creatorId}/dashboard?days=${days}`);
}

export async function getIntelligencePredictions(creatorId: string = getCreatorId(), predictionType?: 'conversion' | 'churn' | 'revenue'): Promise<any> {
  const params = predictionType ? `?prediction_type=${predictionType}` : '';
  return apiFetch(`/intelligence/${creatorId}/predictions${params}`);
}

export async function getIntelligenceRecommendations(creatorId: string = getCreatorId(), category?: 'content' | 'action' | 'product' | 'timing'): Promise<any> {
  const params = category ? `?category=${category}` : '';
  return apiFetch(`/intelligence/${creatorId}/recommendations${params}`);
}

export async function getIntelligencePatterns(creatorId: string = getCreatorId(), days: number = 30): Promise<any> {
  return apiFetch(`/intelligence/${creatorId}/patterns?days=${days}`);
}

export async function getWeeklyReport(creatorId: string = getCreatorId()): Promise<WeeklyReportResponse> {
  return apiFetch(`/intelligence/${creatorId}/report/weekly`);
}

export async function generateWeeklyReport(creatorId: string = getCreatorId()): Promise<WeeklyReportResponse> {
  return apiFetch(`/intelligence/${creatorId}/report/generate`, { method: 'POST' });
}
