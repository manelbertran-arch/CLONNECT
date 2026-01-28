/**
 * React Query hooks for Audiencia API
 *
 * SPRINT4-T4.2: Hooks for the /audiencia/* endpoints (Tu Audiencia page)
 */
import { useQuery } from "@tanstack/react-query";
import {
  getAudienciaTopics,
  getAudienciaPassions,
  getAudienciaFrustrations,
  getAudienciaCompetition,
  getAudienciaTrends,
  getAudienciaContentRequests,
  getAudienciaPurchaseObjections,
  getAudienciaPerception,
  apiKeys,
  getCreatorId,
} from "@/services/api";
import type {
  TopicsResponse,
  ObjectionsResponse,
  CompetitionResponse,
  TrendsResponse,
  ContentRequestsResponse,
  PerceptionResponse,
} from "@/services/api";

/**
 * Hook to fetch topics - what the audience talks about
 */
export function useAudienciaTopics(creatorId: string = getCreatorId(), limit: number = 10) {
  return useQuery<TopicsResponse>({
    queryKey: apiKeys.audienciaTopics(creatorId),
    queryFn: () => getAudienciaTopics(creatorId, limit),
    enabled: !!creatorId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook to fetch passions - topics with high engagement
 */
export function useAudienciaPassions(creatorId: string = getCreatorId(), limit: number = 10) {
  return useQuery<TopicsResponse>({
    queryKey: apiKeys.audienciaPassions(creatorId),
    queryFn: () => getAudienciaPassions(creatorId, limit),
    enabled: !!creatorId,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch frustrations - what frustrates the audience
 */
export function useAudienciaFrustrations(creatorId: string = getCreatorId(), limit: number = 10) {
  return useQuery<ObjectionsResponse>({
    queryKey: apiKeys.audienciaFrustrations(creatorId),
    queryFn: () => getAudienciaFrustrations(creatorId, limit),
    enabled: !!creatorId,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch competition - competitor mentions
 */
export function useAudienciaCompetition(creatorId: string = getCreatorId(), limit: number = 10) {
  return useQuery<CompetitionResponse>({
    queryKey: apiKeys.audienciaCompetition(creatorId),
    queryFn: () => getAudienciaCompetition(creatorId, limit),
    enabled: !!creatorId,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch trends - emerging topics
 */
export function useAudienciaTrends(creatorId: string = getCreatorId(), limit: number = 10) {
  return useQuery<TrendsResponse>({
    queryKey: apiKeys.audienciaTrends(creatorId),
    queryFn: () => getAudienciaTrends(creatorId, limit),
    enabled: !!creatorId,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch content requests - what content they want
 */
export function useAudienciaContentRequests(creatorId: string = getCreatorId(), limit: number = 10) {
  return useQuery<ContentRequestsResponse>({
    queryKey: apiKeys.audienciaContentRequests(creatorId),
    queryFn: () => getAudienciaContentRequests(creatorId, limit),
    enabled: !!creatorId,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch purchase objections - why they don't buy
 */
export function useAudienciaPurchaseObjections(creatorId: string = getCreatorId(), limit: number = 10) {
  return useQuery<ObjectionsResponse>({
    queryKey: apiKeys.audienciaPurchaseObjections(creatorId),
    queryFn: () => getAudienciaPurchaseObjections(creatorId, limit),
    enabled: !!creatorId,
    staleTime: 5 * 60 * 1000,
  });
}

/**
 * Hook to fetch perception - what they think about you
 */
export function useAudienciaPerception(creatorId: string = getCreatorId()) {
  return useQuery<PerceptionResponse>({
    queryKey: apiKeys.audienciaPerception(creatorId),
    queryFn: () => getAudienciaPerception(creatorId),
    enabled: !!creatorId,
    staleTime: 5 * 60 * 1000,
  });
}

// Re-export types for convenience
export type {
  TopicsResponse,
  ObjectionsResponse,
  CompetitionResponse,
  TrendsResponse,
  ContentRequestsResponse,
  PerceptionResponse,
};
