/**
 * React Query hooks for Intelligence API
 */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getIntelligenceDashboard,
  getIntelligencePredictions,
  getIntelligenceRecommendations,
  getIntelligencePatterns,
  getWeeklyReport,
  generateWeeklyReport,
  apiKeys,
  getCreatorId,
} from "@/services/api";
import type {
  IntelligenceDashboardResponse,
  WeeklyReportResponse,
} from "@/services/api";

/**
 * Hook to fetch Intelligence Dashboard
 * Includes KPIs, predictions, recommendations, and patterns
 */
export function useIntelligenceDashboard(
  creatorId: string = getCreatorId(),
  days: number = 30
) {
  return useQuery({
    queryKey: [...apiKeys.intelligenceDashboard(creatorId), days],
    queryFn: () => getIntelligenceDashboard(creatorId, days),
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchInterval: 5 * 60 * 1000, // Refresh every 5 minutes
  });
}

/**
 * Hook to fetch predictions
 */
export function useIntelligencePredictions(
  creatorId: string = getCreatorId(),
  predictionType?: 'conversion' | 'churn' | 'revenue'
) {
  return useQuery({
    queryKey: [...apiKeys.intelligencePredictions(creatorId), predictionType],
    queryFn: () => getIntelligencePredictions(creatorId, predictionType),
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch recommendations
 */
export function useIntelligenceRecommendations(
  creatorId: string = getCreatorId(),
  category?: 'content' | 'action' | 'product' | 'timing'
) {
  return useQuery({
    queryKey: apiKeys.intelligenceRecommendations(creatorId, category),
    queryFn: () => getIntelligenceRecommendations(creatorId, category),
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch patterns
 */
export function useIntelligencePatterns(
  creatorId: string = getCreatorId(),
  days: number = 30
) {
  return useQuery({
    queryKey: [...apiKeys.intelligencePatterns(creatorId), days],
    queryFn: () => getIntelligencePatterns(creatorId, days),
    staleTime: 10 * 60 * 1000, // 10 minutes - patterns change less frequently
  });
}

/**
 * Hook to fetch weekly report
 */
export function useWeeklyReport(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.intelligenceWeeklyReport(creatorId),
    queryFn: () => getWeeklyReport(creatorId),
    staleTime: 60 * 60 * 1000, // 1 hour - reports don't change often
    retry: 1, // Only retry once - might not exist yet
  });
}

/**
 * Hook to generate a new weekly report
 */
export function useGenerateWeeklyReport(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => generateWeeklyReport(creatorId),
    onSuccess: () => {
      // Invalidate the weekly report query to refetch
      queryClient.invalidateQueries({
        queryKey: apiKeys.intelligenceWeeklyReport(creatorId),
      });
    },
  });
}

/**
 * Combined hook for the full Intelligence Dashboard view
 * Fetches dashboard data and handles loading/error states
 */
export function useFullIntelligenceDashboard(
  creatorId: string = getCreatorId()
) {
  const dashboardQuery = useIntelligenceDashboard(creatorId);
  const weeklyReportQuery = useWeeklyReport(creatorId);

  return {
    dashboard: dashboardQuery.data,
    weeklyReport: weeklyReportQuery.data,
    isLoading: dashboardQuery.isLoading,
    isError: dashboardQuery.isError,
    error: dashboardQuery.error,
    refetch: () => {
      dashboardQuery.refetch();
      weeklyReportQuery.refetch();
    },
  };
}
