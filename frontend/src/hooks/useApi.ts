/**
 * React Query hooks for API data fetching
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getDashboardOverview,
  getConversations,
  getArchivedConversations,
  restoreConversation,
  getLeads,
  getMetrics,
  getCreatorConfig,
  updateCreatorConfig,
  toggleBot,
  getProducts,
  addProduct,
  updateProduct,
  deleteProduct,
  getFollowerDetail,
  sendMessage,
  updateLeadStatus,
  createManualLead,
  updateLead,
  deleteLead,
  archiveConversation,
  markConversationSpam,
  deleteConversation,
  getKnowledge,
  deleteKnowledge,
  getRevenueStats,
  getPurchases,
  recordPurchase,
  getBookings,
  getCalendarStats,
  getBookingLinks,
  createBookingLink,
  deleteBookingLink,
  getNurturingSequences,
  getNurturingStats,
  getNurturingFollowups,
  toggleNurturingSequence,
  updateNurturingSequence,
  getNurturingEnrolled,
  cancelNurturing,
  runNurturing,
  addContent,
  getConnections,
  updateConnection,
  disconnectPlatform,
  apiKeys,
} from "@/services/api";
import type { UpdateConnectionData } from "@/services/api";
import type { RunNurturingParams, CreateBookingLinkData, RecordPurchaseData } from "@/services/api";
import type { CreateLeadData, UpdateLeadData } from "@/services/api";
import type { Product } from "@/types/api";

const CREATOR_ID = import.meta.env.VITE_CREATOR_ID || "manel";

/**
 * Hook to fetch dashboard overview
 * Auto-refreshes every 5 seconds
 */
export function useDashboard(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.dashboard(creatorId),
    queryFn: () => getDashboardOverview(creatorId),
    refetchInterval: 5000, // Refetch every 5 seconds
    staleTime: 2000, // Consider data stale after 2 seconds
  });
}

/**
 * Hook to fetch conversations
 * Auto-refreshes every 5 seconds
 */
export function useConversations(creatorId: string = CREATOR_ID, limit = 50) {
  return useQuery({
    queryKey: apiKeys.conversations(creatorId),
    queryFn: () => getConversations(creatorId, limit),
    refetchInterval: 5000, // Refetch every 5 seconds
    staleTime: 2000,
  });
}

/**
 * Hook to fetch a specific follower's conversation history
 * Auto-refreshes every 5 seconds when viewing a conversation
 */
export function useFollowerDetail(followerId: string | null, creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.follower(creatorId, followerId || ""),
    queryFn: () => getFollowerDetail(creatorId, followerId!),
    enabled: !!followerId, // Only fetch when we have a followerId
    refetchInterval: 5000, // Refetch every 5 seconds for real-time updates
    staleTime: 2000,
  });
}

/**
 * Hook to fetch leads
 * Auto-refreshes every 10 seconds
 */
export function useLeads(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.leads(creatorId),
    queryFn: () => getLeads(creatorId),
    refetchInterval: 10000, // Refetch every 10 seconds
    staleTime: 5000,
  });
}

/**
 * Hook to fetch metrics
 */
export function useMetrics(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.metrics(creatorId),
    queryFn: () => getMetrics(creatorId),
    refetchInterval: 5000,
    staleTime: 2000,
  });
}

/**
 * Hook to fetch creator config
 */
export function useCreatorConfig(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.config(creatorId),
    queryFn: () => getCreatorConfig(creatorId),
    staleTime: 30000, // Config changes less frequently
  });
}

/**
 * Hook to fetch products
 */
export function useProducts(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.products(creatorId),
    queryFn: () => getProducts(creatorId),
    staleTime: 60000,
  });
}

/**
 * Hook to toggle bot status
 */
export function useToggleBot(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ active, reason = "" }: { active: boolean; reason?: string }) =>
      toggleBot(creatorId, active, reason),
    onSuccess: () => {
      // Invalidate dashboard and config queries
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.config(creatorId) });
    },
  });
}

/**
 * Hook to update creator config
 */
export function useUpdateConfig(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (config: Parameters<typeof updateCreatorConfig>[1]) =>
      updateCreatorConfig(creatorId, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.config(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

/**
 * Hook to send a manual message to a follower
 */
export function useSendMessage(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ followerId, message }: { followerId: string; message: string }) =>
      sendMessage(creatorId, followerId, message),
    onSuccess: (_, variables) => {
      // Invalidate the follower detail to refresh conversation history
      queryClient.invalidateQueries({
        queryKey: apiKeys.follower(creatorId, variables.followerId)
      });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
    },
  });
}

/**
 * Hook to update lead status (for drag & drop in pipeline)
 */
export function useUpdateLeadStatus(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      followerId,
      status
    }: {
      followerId: string;
      status: "cold" | "warm" | "hot" | "customer";
    }) => updateLeadStatus(creatorId, followerId, status),
    onSuccess: (_, variables) => {
      // Invalidate leads, conversations, and follower detail
      queryClient.invalidateQueries({ queryKey: apiKeys.leads(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({
        queryKey: apiKeys.follower(creatorId, variables.followerId)
      });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

// =============================================================================
// REVENUE / PAYMENTS HOOKS
// =============================================================================

/**
 * Hook to fetch revenue stats
 */
export function useRevenue(creatorId: string = CREATOR_ID, days: number = 30) {
  return useQuery({
    queryKey: apiKeys.revenue(creatorId, days),
    queryFn: () => getRevenueStats(creatorId, days),
    staleTime: 60000,
    refetchInterval: 60000,
  });
}

/**
 * Hook to fetch purchases
 */
export function usePurchases(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.purchases(creatorId),
    queryFn: () => getPurchases(creatorId),
    staleTime: 30000,
    refetchInterval: 30000,
  });
}

/**
 * Hook to record a purchase
 */
export function useRecordPurchase(creatorId: string = CREATOR_ID) {
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

// =============================================================================
// CALENDAR / BOOKINGS HOOKS
// =============================================================================

/**
 * Hook to fetch bookings
 */
export function useBookings(creatorId: string = CREATOR_ID, upcoming: boolean = false) {
  return useQuery({
    queryKey: apiKeys.bookings(creatorId, upcoming),
    queryFn: () => getBookings(creatorId, upcoming),
    staleTime: 30000,
    refetchInterval: 30000,
  });
}

/**
 * Hook to fetch calendar stats
 */
export function useCalendarStats(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.calendarStats(creatorId),
    queryFn: () => getCalendarStats(creatorId),
    staleTime: 60000,
  });
}

/**
 * Hook to fetch booking links
 */
export function useBookingLinks(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.bookingLinks(creatorId),
    queryFn: () => getBookingLinks(creatorId),
    staleTime: 300000,
  });
}

/**
 * Hook to create a booking link
 */
export function useCreateBookingLink(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateBookingLinkData) => createBookingLink(creatorId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.bookingLinks(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.calendarStats(creatorId) });
    },
  });
}

/**
 * Hook to delete a booking link
 */
export function useDeleteBookingLink(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => deleteBookingLink(creatorId, linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.bookingLinks(creatorId) });
    },
  });
}

// =============================================================================
// NURTURING HOOKS
// =============================================================================

/**
 * Hook to fetch nurturing sequences
 */
export function useNurturingSequences(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.nurturingSequences(creatorId),
    queryFn: () => getNurturingSequences(creatorId),
    staleTime: 60000,
  });
}

/**
 * Hook to fetch nurturing stats
 */
export function useNurturingStats(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.nurturingStats(creatorId),
    queryFn: () => getNurturingStats(creatorId),
    staleTime: 30000,
  });
}

/**
 * Hook to fetch nurturing followups
 */
export function useNurturingFollowups(creatorId: string = CREATOR_ID, status?: string) {
  return useQuery({
    queryKey: apiKeys.nurturingFollowups(creatorId),
    queryFn: () => getNurturingFollowups(creatorId, status),
    staleTime: 30000,
  });
}

/**
 * Hook to toggle nurturing sequence
 */
export function useToggleNurturingSequence(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sequenceType: string) => toggleNurturingSequence(creatorId, sequenceType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.nurturingSequences(creatorId) });
    },
  });
}

/**
 * Hook to update nurturing sequence
 */
export function useUpdateNurturingSequence(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ sequenceType, steps }: { sequenceType: string; steps: Array<{ delay_hours: number; message: string }> }) =>
      updateNurturingSequence(creatorId, sequenceType, steps),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.nurturingSequences(creatorId) });
    },
  });
}

/**
 * Hook to get enrolled followers
 */
export function useNurturingEnrolled(creatorId: string = CREATOR_ID, sequenceType: string) {
  return useQuery({
    queryKey: ["nurturingEnrolled", creatorId, sequenceType],
    queryFn: () => getNurturingEnrolled(creatorId, sequenceType),
    staleTime: 30000,
    enabled: !!sequenceType,
  });
}

/**
 * Hook to cancel nurturing for a follower
 */
export function useCancelNurturing(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ followerId, sequenceType }: { followerId: string; sequenceType?: string }) =>
      cancelNurturing(creatorId, followerId, sequenceType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.nurturingSequences(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.nurturingStats(creatorId) });
    },
  });
}

/**
 * Hook to run nurturing followups
 */
export function useRunNurturing(creatorId: string = CREATOR_ID) {
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

// =============================================================================
// PRODUCTS MUTATION HOOKS
// =============================================================================

/**
 * Hook to add a product
 */
export function useAddProduct(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (product: Omit<Product, "id">) => addProduct(creatorId, product),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.products(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

/**
 * Hook to update a product
 */
export function useUpdateProduct(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ productId, product }: { productId: string; product: Partial<Product> }) =>
      updateProduct(creatorId, productId, product),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.products(creatorId) });
    },
  });
}

/**
 * Hook to delete a product
 */
export function useDeleteProduct(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (productId: string) => deleteProduct(creatorId, productId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.products(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

// =============================================================================
// CONTENT / RAG HOOKS
// =============================================================================

/**
 * Hook to add content to knowledge base
 */
export function useAddContent(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ text, docType = "faq" }: { text: string; docType?: string }) =>
      addContent(creatorId, text, docType),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) });
    },
  });
}

/**
 * Hook to fetch knowledge base items
 */
export function useKnowledge(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.knowledge(creatorId),
    queryFn: () => getKnowledge(creatorId),
    staleTime: 60 * 1000,
  });
}

/**
 * Hook to delete a knowledge base item
 */
export function useDeleteKnowledge(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deleteKnowledge(creatorId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) });
    },
  });
}

// =============================================================================
// LEAD MANAGEMENT HOOKS
// =============================================================================

/**
 * Hook to create a manual lead
 */
export function useCreateManualLead(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateLeadData) => createManualLead(creatorId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.leads(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

/**
 * Hook to update a lead
 */
export function useUpdateLead(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: string; data: UpdateLeadData }) =>
      updateLead(creatorId, leadId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: apiKeys.leads(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.follower(creatorId, variables.leadId) });
    },
  });
}

/**
 * Hook to delete a lead
 */
export function useDeleteLead(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (leadId: string) => deleteLead(creatorId, leadId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.leads(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

// =============================================================================
// CONVERSATION ACTION HOOKS
// =============================================================================

/**
 * Hook to archive a conversation
 */
export function useArchiveConversation(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => archiveConversation(creatorId, conversationId),
    onMutate: async (conversationId: string) => {
      await queryClient.cancelQueries({ queryKey: apiKeys.conversations(creatorId) });
      const previousData = queryClient.getQueryData(apiKeys.conversations(creatorId));
      queryClient.setQueryData(apiKeys.conversations(creatorId), (old: any) => {
        if (!old) return old;
        return {
          ...old,
          conversations: old.conversations.filter((c: any) => c.follower_id !== conversationId),
          count: old.count - 1
        };
      });
      return { previousData };
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(apiKeys.conversations(creatorId), context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

/**
 * Hook to mark a conversation as spam
 */
export function useMarkConversationSpam(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => markConversationSpam(creatorId, conversationId),
    onMutate: async (conversationId: string) => {
      await queryClient.cancelQueries({ queryKey: apiKeys.conversations(creatorId) });
      const previousData = queryClient.getQueryData(apiKeys.conversations(creatorId));
      queryClient.setQueryData(apiKeys.conversations(creatorId), (old: any) => {
        if (!old) return old;
        return {
          ...old,
          conversations: old.conversations.filter((c: any) => c.follower_id !== conversationId),
          count: old.count - 1
        };
      });
      return { previousData };
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(apiKeys.conversations(creatorId), context.previousData);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

/**
 * Hook to delete a conversation
 */
export function useDeleteConversation(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => deleteConversation(creatorId, conversationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

/**
 * Hook to fetch archived/spam conversations
 */
export function useArchivedConversations(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.archivedConversations(creatorId),
    queryFn: () => getArchivedConversations(creatorId),
    select: (data) => data.conversations || [],
    refetchInterval: 30000,
  });
}

/**
 * Hook to restore an archived/spam conversation
 */
export function useRestoreConversation(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => restoreConversation(creatorId, conversationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.archivedConversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

// =============================================================================
// CONNECTIONS HOOKS
// =============================================================================

/**
 * Hook to fetch all connections status
 */
export function useConnections(creatorId: string = CREATOR_ID) {
  return useQuery({
    queryKey: apiKeys.connections(creatorId),
    queryFn: () => getConnections(creatorId),
    staleTime: 60000, // 1 minute
  });
}

/**
 * Hook to update a connection
 */
export function useUpdateConnection(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ platform, data }: { platform: string; data: UpdateConnectionData }) =>
      updateConnection(creatorId, platform, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.connections(creatorId) });
      queryClient.invalidateQueries({ queryKey: ["onboarding"] });
    },
  });
}

/**
 * Hook to disconnect a platform
 */
export function useDisconnectPlatform(creatorId: string = CREATOR_ID) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (platform: string) => disconnectPlatform(creatorId, platform),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.connections(creatorId) });
      queryClient.invalidateQueries({ queryKey: ["onboarding"] });
    },
  });
}
