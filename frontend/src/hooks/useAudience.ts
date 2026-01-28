/**
 * React Query hooks for Audience Intelligence API
 *
 * SPRINT2-T2.1: Hooks for the new /audience/* endpoints
 */
import { useQuery } from "@tanstack/react-query";
import {
  getAudienceProfile,
  getAudienceSegments,
  getAudienceSegmentUsers,
  getAudienceAggregated,
  apiKeys,
  getCreatorId,
} from "@/services/api";
import type { AudienceProfile, SegmentCount, AggregatedMetrics } from "@/services/api";

/**
 * Hook to fetch a complete audience profile for a follower
 * Returns profile with narrative, segments, and recommended actions
 */
export function useAudienceProfile(
  followerId: string,
  creatorId: string = getCreatorId()
) {
  return useQuery<AudienceProfile>({
    queryKey: apiKeys.audienceProfile(creatorId, followerId),
    queryFn: () => getAudienceProfile(creatorId, followerId),
    enabled: !!followerId && !!creatorId,
    staleTime: 2 * 60 * 1000, // 2 minutes - profiles change with conversations
    refetchOnWindowFocus: false,
  });
}

/**
 * Hook to fetch segment counts for a creator
 * Returns list of segments with follower counts
 */
export function useAudienceSegments(creatorId: string = getCreatorId()) {
  return useQuery<SegmentCount[]>({
    queryKey: apiKeys.audienceSegments(creatorId),
    queryFn: () => getAudienceSegments(creatorId),
    enabled: !!creatorId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook to fetch profiles in a specific segment
 */
export function useAudienceSegmentUsers(
  segmentName: string,
  limit: number = 20,
  creatorId: string = getCreatorId()
) {
  return useQuery<AudienceProfile[]>({
    queryKey: [...apiKeys.audienceSegmentUsers(creatorId, segmentName), limit],
    queryFn: () => getAudienceSegmentUsers(creatorId, segmentName, limit),
    enabled: !!creatorId && !!segmentName,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook to fetch aggregated audience metrics
 */
export function useAudienceAggregated(creatorId: string = getCreatorId()) {
  return useQuery<AggregatedMetrics>({
    queryKey: apiKeys.audienceAggregated(creatorId),
    queryFn: () => getAudienceAggregated(creatorId),
    enabled: !!creatorId,
    staleTime: 10 * 60 * 1000, // 10 minutes - aggregated data changes slowly
  });
}

// Re-export types for convenience
export type { AudienceProfile, SegmentCount, AggregatedMetrics };
