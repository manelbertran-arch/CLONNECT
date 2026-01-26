/**
 * React Query hooks for Analytics API
 * Business Intelligence dashboard data fetching
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getCreatorId, API_URL, getAuthToken } from "@/services/api";

// =============================================================================
// API FETCH HELPER
// =============================================================================

async function analyticsFetch<T>(endpoint: string): Promise<T> {
  const token = getAuthToken();
  const response = await fetch(`${API_URL}/api/analytics${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
  });

  if (!response.ok) {
    throw new Error(`Analytics API error: ${response.status}`);
  }

  return response.json();
}

async function analyticsPost<T>(endpoint: string, body?: object): Promise<T> {
  const token = getAuthToken();
  const response = await fetch(`${API_URL}/api/analytics${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    throw new Error(`Analytics API error: ${response.status}`);
  }

  return response.json();
}

// =============================================================================
// QUERY KEYS
// =============================================================================

export const analyticsKeys = {
  summary: (creatorId: string, period: string) => ["analytics", "summary", creatorId, period] as const,
  instagram: (creatorId: string, period: string) => ["analytics", "instagram", creatorId, period] as const,
  audience: (creatorId: string, period: string) => ["analytics", "audience", creatorId, period] as const,
  sales: (creatorId: string, period: string) => ["analytics", "sales", creatorId, period] as const,
  predictions: (creatorId: string) => ["analytics", "predictions", creatorId] as const,
  reports: (creatorId: string) => ["analytics", "reports", creatorId] as const,
  trends: (creatorId: string, metric: string, period: string) => ["analytics", "trends", creatorId, metric, period] as const,
};

// =============================================================================
// TYPES
// =============================================================================

export interface AnalyticsSummary {
  period: string;
  kpis: {
    revenue: { value: number; change: number; trend: 'up' | 'down' | 'stable' };
    conversions: { value: number; change: number; trend: 'up' | 'down' | 'stable' };
    leads: { value: number; change: number; trend: 'up' | 'down' | 'stable' };
    dms: { value: number; change: number; trend: 'up' | 'down' | 'stable' };
    posts: { value: number; change: number; trend: 'up' | 'down' | 'stable' };
    sentiment: { value: number; change: number; trend: 'up' | 'down' | 'stable' };
  };
}

export interface InstagramAnalytics {
  total_posts: number;
  by_type: Record<string, { count: number; avg_engagement: number }>;
  top_posts: Array<{
    id: string;
    caption: string;
    media_type: string;
    likes: number;
    comments: number;
    created_at: string;
  }>;
  best_time: {
    hour: number;
    day: string;
    insight: string;
  } | null;
  post_to_dm_correlation: Array<{
    post_id: string;
    caption: string;
    media_type: string;
    dms_generated: number;
  }>;
  rag_documents_count: number;
}

export interface AudienceAnalytics {
  total_messages: number;
  unique_users: number;
  avg_messages_per_user: number;
  sentiment: {
    average: number;
    distribution: Record<string, number>;
  };
  intent_distribution: Array<{
    intent: string;
    count: number;
    percentage: number;
  }>;
  objections: Array<{
    type: string;
    count: number;
    percentage: number;
    examples: string[];
  }>;
  questions: {
    total: number;
    samples: Array<{ content: string }>;
  };
  funnel: Array<{
    stage: string;
    count: number;
    percentage: number;
  }>;
}

export interface SalesAnalytics {
  summary: {
    total_revenue: number;
    previous_revenue: number;
    revenue_change: number;
    total_sales: number;
    sales_change: number;
    avg_ticket: number;
  };
  by_product: Array<{
    id: string;
    name: string;
    price: number;
    mentions: number;
    category: string;
    is_active: boolean;
  }>;
  revenue_trend: Array<{
    date: string;
    value: number;
  }>;
}

export interface PredictionsData {
  hot_leads: Array<{
    lead_id: string;
    username: string;
    conversion_probability: number;
    recommended_action: string;
  }>;
  total_hot_leads: number;
  churn_risks: Array<{
    lead_id: string;
    username: string;
    churn_risk: number;
    days_inactive: number;
  }>;
  total_at_risk: number;
  revenue_forecast: {
    forecasts: Array<{
      week: number;
      projected_revenue: number;
      confidence: number;
    }>;
    growth_trend: number;
  };
  recommendations: {
    content: Array<{
      priority: 'high' | 'medium' | 'low';
      category: string;
      title: string;
      description: string;
    }>;
    actions: Array<{
      priority: 'high' | 'medium' | 'low';
      category: string;
      title: string;
      description: string;
    }>;
  };
}

export interface WeeklyReport {
  id: string;
  week_start: string;
  week_end: string;
  executive_summary: string;
  metrics_summary: Record<string, number>;
  key_wins: string[];
  areas_to_improve: string[];
  created_at: string;
}

export interface TrendData {
  data: Array<{
    date: string;
    value: number;
  }>;
}

// =============================================================================
// HOOKS
// =============================================================================

/**
 * Hook to fetch analytics summary (6 KPIs)
 */
export function useAnalyticsSummary(
  creatorId: string = getCreatorId(),
  period: string = '30d'
) {
  return useQuery({
    queryKey: analyticsKeys.summary(creatorId, period),
    queryFn: () => analyticsFetch<AnalyticsSummary>(`/${creatorId}/summary?period=${period}`),
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchInterval: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch Instagram analytics
 */
export function useInstagramAnalytics(
  creatorId: string = getCreatorId(),
  period: string = '30d'
) {
  return useQuery({
    queryKey: analyticsKeys.instagram(creatorId, period),
    queryFn: () => analyticsFetch<InstagramAnalytics>(`/${creatorId}/instagram?period=${period}`),
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch audience/DM analytics
 */
export function useAudienceAnalytics(
  creatorId: string = getCreatorId(),
  period: string = '30d'
) {
  return useQuery({
    queryKey: analyticsKeys.audience(creatorId, period),
    queryFn: () => analyticsFetch<AudienceAnalytics>(`/${creatorId}/audience?period=${period}`),
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch sales analytics
 */
export function useSalesAnalytics(
  creatorId: string = getCreatorId(),
  period: string = '30d'
) {
  return useQuery({
    queryKey: analyticsKeys.sales(creatorId, period),
    queryFn: () => analyticsFetch<SalesAnalytics>(`/${creatorId}/sales?period=${period}`),
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch predictions (hot leads, churn risks, forecasts)
 */
export function usePredictions(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: analyticsKeys.predictions(creatorId),
    queryFn: () => analyticsFetch<PredictionsData>(`/${creatorId}/predictions`),
    staleTime: 10 * 60 * 1000, // 10 minutes - predictions change less frequently
  });
}

/**
 * Hook to fetch reports list
 */
export function useReports(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: analyticsKeys.reports(creatorId),
    queryFn: () => analyticsFetch<{ reports: WeeklyReport[] }>(`/${creatorId}/reports`),
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Hook to generate a new report
 */
export function useGenerateReport(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => analyticsPost<WeeklyReport>(`/${creatorId}/reports/generate`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: analyticsKeys.reports(creatorId) });
    },
  });
}

/**
 * Hook to fetch trend data for charts
 */
export function useTrends(
  creatorId: string = getCreatorId(),
  metric: string = 'revenue',
  period: string = '30d'
) {
  return useQuery({
    queryKey: analyticsKeys.trends(creatorId, metric, period),
    queryFn: () => analyticsFetch<TrendData>(`/${creatorId}/trends?metric=${metric}&period=${period}`),
    staleTime: 5 * 60 * 1000,
  });
}
