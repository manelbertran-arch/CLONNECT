import { useQuery } from "@tanstack/react-query";
import { getAutolearningDashboard, apiKeys, getCreatorId } from "@/services/api";

export function useAutolearningDashboard(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.autolearningDashboard(creatorId),
    queryFn: () => getAutolearningDashboard(creatorId),
    staleTime: 60_000,
    gcTime: 300_000,
  });
}
