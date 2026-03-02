import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getDashboardOverview, toggleBot, getMetrics, getCreatorConfig, updateCreatorConfig, apiKeys, getCreatorId } from "@/services/api";

export function useDashboard(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.dashboard(creatorId),
    queryFn: () => getDashboardOverview(creatorId),
    refetchInterval: 60000,
    refetchIntervalInBackground: false,
    staleTime: 30000,
  });
}

export function useMetrics(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.metrics(creatorId),
    queryFn: () => getMetrics(creatorId),
    refetchInterval: 60000,
    refetchIntervalInBackground: false,
    staleTime: 30000,
  });
}

export function useCreatorConfig(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.config(creatorId),
    queryFn: () => getCreatorConfig(creatorId),
    staleTime: 30000,
  });
}

export function useToggleBot(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ active, reason = "" }: { active: boolean; reason?: string }) => toggleBot(creatorId, active, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.config(creatorId) });
    },
  });
}

export function useUpdateConfig(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: Parameters<typeof updateCreatorConfig>[1]) => updateCreatorConfig(creatorId, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.config(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}
