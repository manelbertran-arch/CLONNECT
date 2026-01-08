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
  getFAQs,
  addFAQ,
  deleteFAQ,
  updateFAQ,
  getAbout,
  updateAbout,
  generateKnowledge,
  deleteKnowledge,
  getRevenueStats,
  getPurchases,
  recordPurchase,
  getBookings,
  getCalendarStats,
  getBookingLinks,
  getCalendlySyncStatus,
  createBookingLink,
  deleteBookingLink,
  cancelBooking,
  clearBookingHistory,
  deleteHistoryItem,
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
  getVisualOnboardingStatus,
  completeVisualOnboarding,
  // Copilot
  getCopilotPending,
  getCopilotStatus,
  approveCopilotResponse,
  discardCopilotResponse,
  toggleCopilotMode,
  getCopilotNotifications,
  approveAllCopilot,
  apiKeys,
} from "@/services/api";
import type { UpdateConnectionData } from "@/services/api";
import type { RunNurturingParams, CreateBookingLinkData, RecordPurchaseData } from "@/services/api";
import type { CreateLeadData, UpdateLeadData } from "@/services/api";
import type { Product } from "@/types/api";
import { getCreatorId } from "@/services/api";

/**
 * Hook to fetch dashboard overview
 * Auto-refreshes every 5 seconds
 */
export function useDashboard(creatorId: string = getCreatorId()) {
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
export function useConversations(creatorId: string = getCreatorId(), limit = 50) {
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
export function useFollowerDetail(followerId: string | null, creatorId: string = getCreatorId()) {
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
export function useLeads(creatorId: string = getCreatorId()) {
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
export function useMetrics(creatorId: string = getCreatorId()) {
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
export function useCreatorConfig(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.config(creatorId),
    queryFn: () => getCreatorConfig(creatorId),
    staleTime: 30000, // Config changes less frequently
  });
}

/**
 * Hook to fetch products
 */
export function useProducts(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.products(creatorId),
    queryFn: () => getProducts(creatorId),
    staleTime: 60000,
  });
}

/**
 * Hook to toggle bot status
 */
export function useToggleBot(creatorId: string = getCreatorId()) {
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
export function useUpdateConfig(creatorId: string = getCreatorId()) {
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
export function useSendMessage(creatorId: string = getCreatorId()) {
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
export function useUpdateLeadStatus(creatorId: string = getCreatorId()) {
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
export function useRevenue(creatorId: string = getCreatorId(), days: number = 30) {
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
export function usePurchases(creatorId: string = getCreatorId()) {
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

// =============================================================================
// CALENDAR / BOOKINGS HOOKS
// =============================================================================

/**
 * Hook to fetch bookings
 */
export function useBookings(creatorId: string = getCreatorId(), upcoming: boolean = false) {
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
export function useCalendarStats(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.calendarStats(creatorId),
    queryFn: () => getCalendarStats(creatorId),
    staleTime: 60000,
  });
}

/**
 * Hook to fetch booking links
 */
export function useBookingLinks(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.bookingLinks(creatorId),
    queryFn: () => getBookingLinks(creatorId),
    staleTime: 300000,
  });
}

/**
 * Hook to fetch Calendly sync status (check if connected)
 */
export function useCalendlySyncStatus(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: ["calendly-sync-status", creatorId],
    queryFn: () => getCalendlySyncStatus(creatorId),
    staleTime: 60000,
  });
}

/**
 * Hook to create a booking link
 */
export function useCreateBookingLink(creatorId: string = getCreatorId()) {
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
export function useDeleteBookingLink(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (linkId: string) => deleteBookingLink(creatorId, linkId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.bookingLinks(creatorId) });
    },
  });
}

/**
 * Hook to cancel a booking (scheduled call)
 */
export function useCancelBooking(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bookingId: string) => cancelBooking(creatorId, bookingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.bookings(creatorId, true) });
      queryClient.invalidateQueries({ queryKey: apiKeys.calendarStats(creatorId) });
    },
  });
}

/**
 * Hook to clear all booking history (completed/cancelled)
 */
export function useClearBookingHistory(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => clearBookingHistory(creatorId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.bookings(creatorId, true) });
      queryClient.invalidateQueries({ queryKey: apiKeys.calendarStats(creatorId) });
    },
  });
}

/**
 * Hook to delete a single history item
 */
export function useDeleteHistoryItem(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (bookingId: string) => deleteHistoryItem(creatorId, bookingId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.bookings(creatorId, true) });
      queryClient.invalidateQueries({ queryKey: apiKeys.calendarStats(creatorId) });
    },
  });
}

// =============================================================================
// NURTURING HOOKS
// =============================================================================

/**
 * Hook to fetch nurturing sequences
 */
export function useNurturingSequences(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.nurturingSequences(creatorId),
    queryFn: () => getNurturingSequences(creatorId),
    staleTime: 60000,
  });
}

/**
 * Hook to fetch nurturing stats
 */
export function useNurturingStats(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.nurturingStats(creatorId),
    queryFn: () => getNurturingStats(creatorId),
    staleTime: 30000,
  });
}

/**
 * Hook to fetch nurturing followups
 */
export function useNurturingFollowups(creatorId: string = getCreatorId(), status?: string) {
  return useQuery({
    queryKey: apiKeys.nurturingFollowups(creatorId),
    queryFn: () => getNurturingFollowups(creatorId, status),
    staleTime: 30000,
  });
}

/**
 * Hook to toggle nurturing sequence
 */
export function useToggleNurturingSequence(creatorId: string = getCreatorId()) {
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
export function useUpdateNurturingSequence(creatorId: string = getCreatorId()) {
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
export function useNurturingEnrolled(creatorId: string = getCreatorId(), sequenceType: string) {
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
export function useCancelNurturing(creatorId: string = getCreatorId()) {
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

// =============================================================================
// PRODUCTS MUTATION HOOKS
// =============================================================================

/**
 * Hook to add a product
 */
export function useAddProduct(creatorId: string = getCreatorId()) {
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
export function useUpdateProduct(creatorId: string = getCreatorId()) {
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
export function useDeleteProduct(creatorId: string = getCreatorId()) {
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
export function useAddContent(creatorId: string = getCreatorId()) {
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
export function useKnowledge(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.knowledge(creatorId),
    queryFn: () => getKnowledge(creatorId),
    staleTime: 60 * 1000,
  });
}

/**
 * Hook to delete a knowledge base item
 */
export function useDeleteKnowledge(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deleteKnowledge(creatorId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) });
    },
  });
}

/**
 * Hook to add a FAQ
 */
export function useAddFAQ(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ question, answer }: { question: string; answer: string }) =>
      addFAQ(creatorId, question, answer),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) });
    },
  });
}

/**
 * Hook to delete a FAQ
 */
export function useDeleteFAQ(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deleteFAQ(creatorId, itemId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) });
    },
  });
}

/**
 * Hook to update an existing FAQ
 */
export function useUpdateFAQ(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, question, answer }: { itemId: string; question: string; answer: string }) =>
      updateFAQ(creatorId, itemId, { question, answer }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) });
    },
  });
}

/**
 * Hook to generate knowledge with AI
 */
export function useGenerateKnowledge() {
  return useMutation({
    mutationFn: ({ prompt, type }: { prompt: string; type: "faqs" | "about" }) =>
      generateKnowledge(prompt, type),
  });
}

/**
 * Hook to update About section
 */
export function useUpdateAbout(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { bio: string; specialties: string; experience: string; audience: string }) =>
      updateAbout(creatorId, data),
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
export function useCreateManualLead(creatorId: string = getCreatorId()) {
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
export function useUpdateLead(creatorId: string = getCreatorId()) {
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
export function useDeleteLead(creatorId: string = getCreatorId()) {
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
export function useArchiveConversation(creatorId: string = getCreatorId()) {
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
export function useMarkConversationSpam(creatorId: string = getCreatorId()) {
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
export function useDeleteConversation(creatorId: string = getCreatorId()) {
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
export function useArchivedConversations(creatorId: string = getCreatorId()) {
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
export function useRestoreConversation(creatorId: string = getCreatorId()) {
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
export function useConnections(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.connections(creatorId),
    queryFn: () => getConnections(creatorId),
    staleTime: 60000, // 1 minute
  });
}

/**
 * Hook to update a connection
 */
export function useUpdateConnection(creatorId: string = getCreatorId()) {
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
export function useDisconnectPlatform(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (platform: string) => disconnectPlatform(creatorId, platform),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.connections(creatorId) });
      queryClient.invalidateQueries({ queryKey: ["onboarding"] });
    },
  });
}

// =============================================================================
// VISUAL ONBOARDING HOOKS
// =============================================================================

/**
 * Hook to fetch visual onboarding status
 */
export function useVisualOnboardingStatus(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: ["visualOnboarding", creatorId],
    queryFn: () => getVisualOnboardingStatus(creatorId),
    staleTime: Infinity, // Don't refetch - this rarely changes
  });
}

/**
 * Hook to mark visual onboarding as complete
 */
export function useCompleteVisualOnboarding(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => completeVisualOnboarding(creatorId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["visualOnboarding", creatorId] });
    },
  });
}

// =============================================================================
// COPILOT HOOKS
// =============================================================================

/**
 * Hook to fetch pending copilot responses
 */
export function useCopilotPending(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.copilotPending(creatorId),
    queryFn: () => getCopilotPending(creatorId),
    refetchInterval: 5000, // Poll every 5 seconds
    staleTime: 2000,
  });
}

/**
 * Hook to fetch copilot status
 */
export function useCopilotStatus(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.copilotStatus(creatorId),
    queryFn: () => getCopilotStatus(creatorId),
    refetchInterval: 10000,
    staleTime: 5000,
  });
}

/**
 * Hook to approve a copilot response
 */
export function useApproveCopilotResponse(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId, editedText }: { messageId: string; editedText?: string }) =>
      approveCopilotResponse(creatorId, messageId, editedText),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotPending(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotStatus(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
    },
  });
}

/**
 * Hook to discard a copilot response
 */
export function useDiscardCopilotResponse(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) => discardCopilotResponse(creatorId, messageId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotPending(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotStatus(creatorId) });
    },
  });
}

/**
 * Hook to toggle copilot mode
 */
export function useToggleCopilotMode(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => toggleCopilotMode(creatorId, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotStatus(creatorId) });
    },
  });
}

/**
 * Hook to approve all pending responses
 */
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
