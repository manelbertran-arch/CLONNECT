import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getRevenueStats, getPurchases, recordPurchase, apiKeys, getCreatorId } from "@/services/api";
import type { RecordPurchaseData } from "@/services/api";

export function useRevenue(creatorId: string = getCreatorId(), days: number = 30) {
  return useQuery({
    queryKey: apiKeys.revenue(creatorId, days),
    queryFn: () => getRevenueStats(creatorId, days),
    staleTime: 60000,
    refetchInterval: 60000,
  });
}

export function usePurchases(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.purchases(creatorId),
    queryFn: () => getPurchases(creatorId),
    staleTime: 30000,
    refetchInterval: 30000,
  });
}

export function useRecordPurchase(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: RecordPurchaseData) => recordPurchase(creatorId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.purchases(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.revenue(creatorId, 30) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}
