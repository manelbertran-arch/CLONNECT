import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getConnections, updateConnection, disconnectPlatform, apiKeys, getCreatorId } from "@/services/api";
import type { UpdateConnectionData } from "@/services/api";

export function useConnections(creatorId: string = getCreatorId()) {
  return useQuery({ queryKey: apiKeys.connections(creatorId), queryFn: () => getConnections(creatorId), staleTime: 60000 });
}

export function useUpdateConnection(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ platform, data }: { platform: string; data: UpdateConnectionData }) => updateConnection(creatorId, platform, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.connections(creatorId) }); queryClient.invalidateQueries({ queryKey: ["onboarding"] }); },
  });
}

export function useDisconnectPlatform(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (platform: string) => disconnectPlatform(creatorId, platform),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.connections(creatorId) }); queryClient.invalidateQueries({ queryKey: ["onboarding"] }); },
  });
}
