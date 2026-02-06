/**
 * React Query hooks for API data fetching
 */

import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from "@tanstack/react-query";
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
  getAvailability,
  setAvailability,
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
  // Escalations
  getEscalations,
  // CRM Activities & Tasks
  getLeadActivities,
  createLeadActivity,
  getLeadTasks,
  createLeadTask,
  updateLeadTask,
  deleteLeadTask,
  deleteLeadActivity,
  getLeadStats,
  apiKeys,
} from "@/services/api";
import type { LeadActivity, LeadTask } from "@/services/api";
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
    refetchInterval: 60000, // Refetch every 60 seconds (reduced from 5s)
    staleTime: 30000, // Data is fresh for 30 seconds
  });
}

/**
 * Hook to fetch conversations
 * Auto-refreshes every 5 seconds
 */
export function useConversations(creatorId: string = getCreatorId(), limit = 50) {
  return useQuery({
    queryKey: apiKeys.conversations(creatorId),
    queryFn: () => getConversations(creatorId, limit, 0),
    refetchInterval: 30000, // Refresh every 30s
    staleTime: 60000, // Data fresh for 60s (show cached immediately)
    gcTime: 5 * 60 * 1000, // Keep in cache 5 min
  });
}

/**
 * Hook to fetch conversations with infinite scroll support
 * Loads more conversations as user scrolls
 */
export function useInfiniteConversations(creatorId: string = getCreatorId(), pageSize = 50) {
  return useInfiniteQuery({
    queryKey: [...apiKeys.conversations(creatorId), "infinite"],
    queryFn: ({ pageParam = 0 }) => getConversations(creatorId, pageSize, pageParam),
    getNextPageParam: (lastPage) => {
      // Return next offset if there's more data
      if (lastPage.has_more) {
        return (lastPage.offset || 0) + (lastPage.limit || pageSize);
      }
      return undefined;
    },
    initialPageParam: 0,
    refetchInterval: 30000, // Refresh every 30s
    staleTime: 60000, // Data fresh for 60s
    gcTime: 5 * 60 * 1000, // Keep in cache 5 min
  });
}

/**
 * Hook to fetch a specific follower's conversation history
 * Auto-refreshes every 5 seconds when viewing a conversation
 * Also invalidates conversations list to keep sidebar in sync
 */
export function useFollowerDetail(followerId: string | null, creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();

  return useQuery({
    queryKey: apiKeys.follower(creatorId, followerId || ""),
    queryFn: async () => {
      const result = await getFollowerDetail(creatorId, followerId!);
      // Invalidate conversations to keep sidebar sorted by latest message
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      return result;
    },
    enabled: !!followerId, // Only fetch when we have a followerId
    refetchInterval: 15000, // Refresh every 15s
    staleTime: 30000, // Data fresh for 30s
    gcTime: 5 * 60 * 1000, // Keep in cache 5 min
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
    refetchInterval: 30000, // Refetch every 30s
    staleTime: 60000, // Data fresh for 60s
    gcTime: 5 * 60 * 1000, // Keep in cache 5 min
  });
}

/**
 * Hook to fetch metrics
 */
export function useMetrics(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.metrics(creatorId),
    queryFn: () => getMetrics(creatorId),
    refetchInterval: 60000, // Refetch every 60 seconds (reduced from 5s)
    staleTime: 30000, // Data is fresh for 30 seconds
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
 * Nuevo embudo: nuevo, interesado, caliente, cliente, fantasma
 */
export function useUpdateLeadStatus(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      followerId,
      status
    }: {
      followerId: string;
      status: string; // nuevo | interesado | caliente | cliente | fantasma (+ legacy)
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
// AVAILABILITY HOOKS
// =============================================================================

/**
 * Hook to fetch creator's availability schedule
 */
export function useAvailability(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: ["availability", creatorId] as const,
    queryFn: () => getAvailability(creatorId),
    staleTime: 60000,
  });
}

/**
 * Hook to update creator's availability schedule
 */
export function useSetAvailability(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (days: Array<{
      day_of_week: number;
      start_time: string;
      end_time: string;
      is_active: boolean;
    }>) => setAvailability(creatorId, days),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["availability", creatorId] });
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
 * Uses optimistic update for instant UI feedback
 */
export function useDeleteLead(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (leadId: string) => deleteLead(creatorId, leadId),
    // Optimistic update: remove from infinite conversations cache immediately
    onMutate: async (leadId: string) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: apiKeys.conversations(creatorId) });

      // Snapshot for rollback
      const previousData = queryClient.getQueryData([...apiKeys.conversations(creatorId), "infinite"]);

      // Optimistically remove from infinite query cache
      queryClient.setQueryData(
        [...apiKeys.conversations(creatorId), "infinite"],
        (old: { pages: Array<{ conversations: Array<{ id?: string; follower_id: string }> }> } | undefined) => {
          if (!old) return old;
          return {
            ...old,
            pages: old.pages.map(page => ({
              ...page,
              conversations: page.conversations.filter(c => c.id !== leadId && c.follower_id !== leadId),
            })),
          };
        }
      );

      return { previousData };
    },
    // Rollback on error
    onError: (_err, _leadId, context) => {
      if (context?.previousData) {
        queryClient.setQueryData([...apiKeys.conversations(creatorId), "infinite"], context.previousData);
      }
    },
    // Always refetch after to ensure consistency
    onSettled: () => {
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
      queryClient.setQueryData(apiKeys.conversations(creatorId), (old: ConversationsResponse | undefined) => {
        if (!old) return old;
        return {
          ...old,
          conversations: old.conversations.filter((c) => c.follower_id !== conversationId),
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
      queryClient.setQueryData(apiKeys.conversations(creatorId), (old: ConversationsResponse | undefined) => {
        if (!old) return old;
        return {
          ...old,
          conversations: old.conversations.filter((c) => c.follower_id !== conversationId),
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
export function useArchivedConversations(creatorId: string = getCreatorId(), options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: apiKeys.archivedConversations(creatorId),
    queryFn: () => getArchivedConversations(creatorId),
    select: (data) => data.conversations || [],
    refetchInterval: 30000,
    enabled: options?.enabled !== false, // Default true, can be disabled for sequential loading
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
 * Polling reduced to prevent request accumulation when endpoint is slow
 */
export function useCopilotPending(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.copilotPending(creatorId),
    queryFn: () => getCopilotPending(creatorId),
    refetchInterval: 15000, // Poll every 15s
    staleTime: 30000, // Data fresh for 30s (show cached on mount)
    gcTime: 5 * 60 * 1000, // Keep in cache 5 min
    refetchIntervalInBackground: false, // Don't poll if tab not visible
  });
}

/**
 * Hook to fetch copilot status
 * Polling is reduced to avoid race conditions with toggle mutations
 */
export function useCopilotStatus(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.copilotStatus(creatorId),
    queryFn: () => getCopilotStatus(creatorId),
    refetchInterval: 30000, // Poll every 30s
    staleTime: 60000, // Data fresh for 60s (show cached on mount)
    gcTime: 5 * 60 * 1000, // Keep in cache 5 min
    refetchOnWindowFocus: false, // Prevent refetch on window focus
  });
}

/**
 * Hook to approve a copilot response
 * Uses optimistic update for instant UI feedback
 */
export function useApproveCopilotResponse(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ messageId, editedText }: { messageId: string; editedText?: string }) =>
      approveCopilotResponse(creatorId, messageId, editedText),
    // Optimistic update: remove item immediately before server responds
    onMutate: async ({ messageId }) => {
      // Cancel outgoing refetches to prevent race conditions
      await queryClient.cancelQueries({ queryKey: apiKeys.copilotPending(creatorId) });

      // Snapshot previous value for rollback
      const previousData = queryClient.getQueryData(apiKeys.copilotPending(creatorId));

      // Optimistically remove the item from cache
      queryClient.setQueryData(
        apiKeys.copilotPending(creatorId),
        (old: { pending_responses: Array<{ id: string }>; pending_count: number } | undefined) => {
          if (!old) return old;
          return {
            ...old,
            pending_responses: old.pending_responses.filter((r) => r.id !== messageId),
            pending_count: Math.max(0, old.pending_count - 1),
          };
        }
      );

      return { previousData };
    },
    // Rollback on error
    onError: (_err, _variables, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(apiKeys.copilotPending(creatorId), context.previousData);
      }
    },
    // Always refetch after success or error to ensure consistency
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotPending(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotStatus(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
    },
  });
}

/**
 * Hook to discard a copilot response
 * Uses optimistic update for instant UI feedback
 */
export function useDiscardCopilotResponse(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) => discardCopilotResponse(creatorId, messageId),
    // Optimistic update: remove item immediately before server responds
    onMutate: async (messageId: string) => {
      // Cancel outgoing refetches to prevent race conditions
      await queryClient.cancelQueries({ queryKey: apiKeys.copilotPending(creatorId) });

      // Snapshot previous value for rollback
      const previousData = queryClient.getQueryData(apiKeys.copilotPending(creatorId));

      // Optimistically remove the item from cache
      queryClient.setQueryData(
        apiKeys.copilotPending(creatorId),
        (old: { pending_responses: Array<{ id: string }>; pending_count: number } | undefined) => {
          if (!old) return old;
          return {
            ...old,
            pending_responses: old.pending_responses.filter((r) => r.id !== messageId),
            pending_count: Math.max(0, old.pending_count - 1),
          };
        }
      );

      return { previousData };
    },
    // Rollback on error
    onError: (_err, _messageId, context) => {
      if (context?.previousData) {
        queryClient.setQueryData(apiKeys.copilotPending(creatorId), context.previousData);
      }
    },
    // Always refetch after success or error to ensure consistency
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotPending(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.copilotStatus(creatorId) });
    },
  });
}

/**
 * Hook to toggle copilot mode
 * Uses optimistic update to prevent race conditions with polling
 */
export function useToggleCopilotMode(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) => toggleCopilotMode(creatorId, enabled),
    // Optimistic update: change state immediately before server responds
    onMutate: async (enabled: boolean) => {
      // Cancel any outgoing refetches to prevent race conditions
      await queryClient.cancelQueries({ queryKey: apiKeys.copilotStatus(creatorId) });

      // Snapshot previous value for rollback
      const previousStatus = queryClient.getQueryData(apiKeys.copilotStatus(creatorId));

      // Optimistically update the cache
      queryClient.setQueryData(apiKeys.copilotStatus(creatorId), (old: { copilot_enabled?: boolean } | undefined) => ({
        ...old,
        copilot_enabled: enabled,
      }));

      return { previousStatus };
    },
    onError: (err, enabled, context) => {
      // Rollback to previous value on error
      if (context?.previousStatus) {
        queryClient.setQueryData(apiKeys.copilotStatus(creatorId), context.previousStatus);
      }
    },
    onSettled: () => {
      // Always refetch after mutation to ensure sync with server
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

// =============================================================================
// CRM HOOKS - Activities & Tasks
// =============================================================================

/**
 * Hook to fetch lead activities
 * Optimized with caching for fast modal tabs
 */
export function useLeadActivities(leadId: string | null, creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: ["leadActivities", creatorId, leadId],
    queryFn: () => getLeadActivities(creatorId, leadId!),
    enabled: !!leadId,
    staleTime: 60000, // Data fresh for 60s
    gcTime: 5 * 60 * 1000, // Keep in cache 5 min
  });
}

/**
 * Hook to create a lead activity
 */
export function useCreateLeadActivity(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: string; data: { activity_type: string; description: string } }) =>
      createLeadActivity(creatorId, leadId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["leadActivities", creatorId, variables.leadId] });
      queryClient.invalidateQueries({ queryKey: apiKeys.leads(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
    },
  });
}

/**
 * Hook to fetch lead tasks
 * Optimized with caching for fast modal tabs
 */
export function useLeadTasks(leadId: string | null, creatorId: string = getCreatorId(), includeCompleted: boolean = false) {
  return useQuery({
    queryKey: ["leadTasks", creatorId, leadId, includeCompleted],
    queryFn: () => getLeadTasks(creatorId, leadId!, includeCompleted),
    enabled: !!leadId,
    staleTime: 60000, // Data fresh for 60s
    gcTime: 5 * 60 * 1000, // Keep in cache 5 min
  });
}

/**
 * Hook to create a lead task
 */
export function useCreateLeadTask(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: string; data: { title: string; description?: string; task_type?: string; priority?: string; due_date?: string } }) =>
      createLeadTask(creatorId, leadId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["leadTasks", creatorId, variables.leadId] });
      queryClient.invalidateQueries({ queryKey: ["leadActivities", creatorId, variables.leadId] });
    },
  });
}

/**
 * Hook to update a lead task
 */
export function useUpdateLeadTask(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, taskId, data }: { leadId: string; taskId: string; data: Partial<LeadTask> }) =>
      updateLeadTask(creatorId, leadId, taskId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["leadTasks", creatorId, variables.leadId] });
      queryClient.invalidateQueries({ queryKey: ["leadActivities", creatorId, variables.leadId] });
    },
  });
}

/**
 * Hook to delete a lead task
 */
export function useDeleteLeadTask(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, taskId }: { leadId: string; taskId: string }) =>
      deleteLeadTask(creatorId, leadId, taskId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["leadTasks", creatorId, variables.leadId] });
    },
  });
}

/**
 * Hook to delete a lead activity from history
 */
export function useDeleteLeadActivity(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, activityId }: { leadId: string; activityId: string }) =>
      deleteLeadActivity(creatorId, leadId, activityId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["leadActivities", creatorId, variables.leadId] });
    },
  });
}

/**
 * Hook to fetch lead stats for monitoring
 * Optimized with caching for fast modal tabs
 */
export function useLeadStats(leadId: string | null, creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: ["leadStats", creatorId, leadId],
    queryFn: () => getLeadStats(creatorId, leadId!),
    enabled: !!leadId,
    staleTime: 60000, // Data fresh for 60s
    gcTime: 5 * 60 * 1000, // Keep in cache 5 min
  });
}

// =============================================================================
// ESCALATIONS HOOKS
// =============================================================================

/**
 * Hook to fetch escalation alerts
 * Returns leads that need human attention
 */
export function useEscalations(creatorId: string = getCreatorId(), limit: number = 50) {
  return useQuery({
    queryKey: apiKeys.escalations(creatorId),
    queryFn: () => getEscalations(creatorId, limit),
    refetchInterval: 60000, // Refetch every minute
    staleTime: 30000,
  });
}
