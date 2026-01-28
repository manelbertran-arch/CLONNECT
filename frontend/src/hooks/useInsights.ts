/**
 * React Query hooks for Insights API
 *
 * SPRINT3-T3.2: Hooks for the /insights/* endpoints
 */
import { useQuery } from "@tanstack/react-query";
import {
  getTodayMission,
  getWeeklyInsights,
  getWeeklyMetrics,
  apiKeys,
  getCreatorId,
} from "@/services/api";
import type {
  TodayMission,
  WeeklyInsights,
  WeeklyMetrics,
} from "@/services/api";

/**
 * Hook to fetch today's mission
 * Returns hot leads, pending responses, and bookings
 */
export function useTodayMission(creatorId: string = getCreatorId()) {
  return useQuery<TodayMission>({
    queryKey: apiKeys.insightsToday(creatorId),
    queryFn: () => getTodayMission(creatorId),
    enabled: !!creatorId,
    staleTime: 2 * 60 * 1000, // 2 minutes - mission changes frequently
    refetchOnWindowFocus: true,
  });
}

/**
 * Hook to fetch weekly insights
 * Returns content, trend, product, and competition insights
 */
export function useWeeklyInsights(creatorId: string = getCreatorId()) {
  return useQuery<WeeklyInsights>({
    queryKey: apiKeys.insightsWeekly(creatorId),
    queryFn: () => getWeeklyInsights(creatorId),
    enabled: !!creatorId,
    staleTime: 10 * 60 * 1000, // 10 minutes - insights change slowly
  });
}

/**
 * Hook to fetch weekly metrics
 * Returns revenue, sales, response rate with deltas
 */
export function useWeeklyMetrics(creatorId: string = getCreatorId()) {
  return useQuery<WeeklyMetrics>({
    queryKey: apiKeys.insightsMetrics(creatorId),
    queryFn: () => getWeeklyMetrics(creatorId),
    enabled: !!creatorId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

// Re-export types for convenience
export type { TodayMission, WeeklyInsights, WeeklyMetrics };
