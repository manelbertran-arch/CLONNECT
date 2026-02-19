import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getCopilotPending, getCopilotStatus, approveCopilotResponse,
  discardCopilotResponse, toggleCopilotMode, approveAllCopilot,
  getCopilotStats, getCopilotComparisons, getPendingForLead,
  trackManualCopilotResponse, getLearningProgress,
  apiKeys, getCreatorId,
} from "@/services/api";

export function useCopilotPending(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.copilotPending(creatorId),
    queryFn: () => getCopilotPending(creatorId),
    refetchInterval: 15000,
    staleTime: 30000,
    gcTime: 5 * 60 * 1000,
    refetchIntervalInBackground: false,
  });
}

export function useCopilotStatus(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.copilotStatus(creatorId),
    queryFn: () => getCopilotStatus(creatorId),
    refetchInterval: 30000,
    staleTime: 60000,
    gcTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

export function useApproveCopilotResponse(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId, editedText }: { messageId: string; editedText?: string }) => approveCopilotResponse(creatorId, messageId, editedText),
    onMutate: async ({ messageId }) => {
      await queryClient.cancelQueries({ queryKey: apiKeys.copilotPending(creatorId) });
      const previousData = queryClient.getQueryData(apiKeys.copilotPending(creatorId));
      queryClient.setQueryData(apiKeys.copilotPending(creatorId), (old: { pending_responses: Array<{ id: string }>; pending_count: number } | undefined) => {
        if (!old) return old;
        return { ...old, pending_responses: old.pending_responses.filter((r) => r.id !== messageId), pending_count: Math.max(0, old.pending_count - 1) };
      });
      return { previousData };
    },
    onError: (_err, _variables, context) => {
      if (context?.previousData) queryClient.setQueryData(apiKeys.copilotPending(creatorId), context.previousData);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotPending(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotStatus(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: ["copilotPendingForLead"] });
    },
  });
}

export function useDiscardCopilotResponse(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) => discardCopilotResponse(creatorId, messageId),
    onMutate: async (messageId: string) => {
      await queryClient.cancelQueries({ queryKey: apiKeys.copilotPending(creatorId) });
      const previousData = queryClient.getQueryData(apiKeys.copilotPending(creatorId));
      queryClient.setQueryData(apiKeys.copilotPending(creatorId), (old: { pending_responses: Array<{ id: string }>; pending_count: number } | undefined) => {
        if (!old) return old;
        return { ...old, pending_responses: old.pending_responses.filter((r) => r.id !== messageId), pending_count: Math.max(0, old.pending_count - 1) };
      });
      return { previousData };
    },
    onError: (_err, _messageId, context) => {
      if (context?.previousData) queryClient.setQueryData(apiKeys.copilotPending(creatorId), context.previousData);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotPending(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotStatus(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: ["copilotPendingForLead"] });
    },
  });
}

export function useToggleCopilotMode(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => toggleCopilotMode(creatorId, enabled),
    onMutate: async (enabled: boolean) => {
      await queryClient.cancelQueries({ queryKey: apiKeys.copilotStatus(creatorId) });
      const previousStatus = queryClient.getQueryData(apiKeys.copilotStatus(creatorId));
      queryClient.setQueryData(apiKeys.copilotStatus(creatorId), (old: { copilot_enabled?: boolean } | undefined) => ({ ...old, copilot_enabled: enabled }));
      return { previousStatus };
    },
    onError: (_err, _enabled, context) => {
      if (context?.previousStatus) queryClient.setQueryData(apiKeys.copilotStatus(creatorId), context.previousStatus);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotStatus(creatorId) });
    },
  });
}

export function useApproveAllCopilot(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => approveAllCopilot(creatorId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotPending(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotStatus(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
    },
  });
}

export function useCopilotStats(days: number = 30, creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.copilotStats(creatorId, days),
    queryFn: () => getCopilotStats(creatorId, days),
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
}

export function useLearningProgress(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.copilotLearning(creatorId),
    queryFn: () => getLearningProgress(creatorId),
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
}

export function useCopilotComparisons(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.copilotComparisons(creatorId),
    queryFn: () => getCopilotComparisons(creatorId),
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
}

export function useTrackManualCopilot(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, content }: { leadId: string; content: string }) =>
      trackManualCopilotResponse(creatorId, leadId, content),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotPending(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotStatus(creatorId) });
      queryClient.invalidateQueries({ queryKey: ["copilotPendingForLead"] });
    },
  });
}

export function usePendingForLead(leadId: string | null, creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.copilotPendingForLead(creatorId, leadId || ""),
    queryFn: () => getPendingForLead(creatorId, leadId!),
    enabled: !!leadId,
    staleTime: 10000,
    gcTime: 60000,
    refetchInterval: 15000,
  });
}
