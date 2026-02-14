import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getVisualOnboardingStatus, completeVisualOnboarding, getCreatorId } from "@/services/api";

export function useVisualOnboardingStatus(creatorId: string = getCreatorId()) {
  return useQuery({ queryKey: ["visualOnboarding", creatorId], queryFn: () => getVisualOnboardingStatus(creatorId), staleTime: Infinity });
}

export function useCompleteVisualOnboarding(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => completeVisualOnboarding(creatorId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["visualOnboarding", creatorId] }); },
  });
}
