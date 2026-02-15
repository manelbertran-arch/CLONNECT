import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getNurturingSequences, getNurturingStats, getNurturingFollowups,
  toggleNurturingSequence, updateNurturingSequence, getNurturingEnrolled,
  cancelNurturing, runNurturing, apiKeys, getCreatorId,
} from "@/services/api";
import type { RunNurturingParams } from "@/services/api";

export function useNurturingSequences(creatorId: string = getCreatorId()) {
  return useQuery({ queryKey: apiKeys.nurturingSequences(creatorId), queryFn: () => getNurturingSequences(creatorId), staleTime: 60000 });
}

export function useNurturingStats(creatorId: string = getCreatorId()) {
  return useQuery({ queryKey: apiKeys.nurturingStats(creatorId), queryFn: () => getNurturingStats(creatorId), staleTime: 30000 });
}

export function useNurturingFollowups(creatorId: string = getCreatorId(), status?: string) {
  return useQuery({ queryKey: apiKeys.nurturingFollowups(creatorId), queryFn: () => getNurturingFollowups(creatorId, status), staleTime: 30000 });
}

export function useToggleNurturingSequence(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sequenceType: string) => toggleNurturingSequence(creatorId, sequenceType),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.nurturingSequences(creatorId) }); },
  });
}

export function useUpdateNurturingSequence(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sequenceType, steps }: { sequenceType: string; steps: Array<{ delay_hours: number; message: string }> }) => updateNurturingSequence(creatorId, sequenceType, steps),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.nurturingSequences(creatorId) }); },
  });
}

export function useNurturingEnrolled(creatorId: string = getCreatorId(), sequenceType: string) {
  return useQuery({ queryKey: ["nurturingEnrolled", creatorId, sequenceType], queryFn: () => getNurturingEnrolled(creatorId, sequenceType), staleTime: 30000, enabled: !!sequenceType });
}

export function useCancelNurturing(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ followerId, sequenceType }: { followerId: string; sequenceType?: string }) => cancelNurturing(creatorId, followerId, sequenceType),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.nurturingSequences(creatorId) }); queryClient.invalidateQueries({ queryKey: apiKeys.nurturingStats(creatorId) }); },
  });
}

export function useRunNurturing(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (params: RunNurturingParams) => runNurturing(creatorId, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.nurturingSequences(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.nurturingStats(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.nurturingFollowups(creatorId) });
    },
  });
}
