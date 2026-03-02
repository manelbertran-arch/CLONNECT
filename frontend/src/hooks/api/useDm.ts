import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from "@tanstack/react-query";
import {
  getConversations, getFollowerDetail, sendMessage, updateLeadStatus,
  archiveConversation, markConversationSpam, deleteConversation,
  getArchivedConversations, restoreConversation,
  apiKeys, getCreatorId,
} from "@/services/api";
import type { ConversationsResponse } from "@/services/api";

export function useConversations(creatorId: string = getCreatorId(), limit = 50) {
  return useQuery({
    queryKey: apiKeys.conversations(creatorId),
    queryFn: () => getConversations(creatorId, limit, 0),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    staleTime: 3000,
    gcTime: 10 * 60 * 1000,
  });
}

export function useInfiniteConversations(creatorId: string = getCreatorId(), pageSize = 50) {
  return useInfiniteQuery({
    queryKey: [...apiKeys.conversations(creatorId), "infinite"],
    queryFn: ({ pageParam = 0 }) => getConversations(creatorId, pageSize, pageParam),
    getNextPageParam: (lastPage) => {
      if (lastPage.has_more) {
        return (lastPage.offset || 0) + (lastPage.limit || pageSize);
      }
      return undefined;
    },
    initialPageParam: 0,
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    staleTime: 3000,
    gcTime: 10 * 60 * 1000,
  });
}

export function useFollowerDetail(followerId: string | null, creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.follower(creatorId, followerId || ""),
    queryFn: () => getFollowerDetail(creatorId, followerId!),
    enabled: !!followerId,
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    staleTime: 3000,
    gcTime: 10 * 60 * 1000,
  });
}

export function useSendMessage(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ followerId, message }: { followerId: string; message: string }) => sendMessage(creatorId, followerId, message),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: apiKeys.follower(creatorId, variables.followerId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
    },
  });
}

export function useUpdateLeadStatus(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ followerId, status }: { followerId: string; status: string }) => updateLeadStatus(creatorId, followerId, status),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: apiKeys.leads(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.follower(creatorId, variables.followerId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

export function useArchiveConversation(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => archiveConversation(creatorId, conversationId),
    onMutate: async (conversationId: string) => {
      await queryClient.cancelQueries({ queryKey: apiKeys.conversations(creatorId) });
      const previousData = queryClient.getQueryData(apiKeys.conversations(creatorId));
      queryClient.setQueryData(apiKeys.conversations(creatorId), (old: ConversationsResponse | undefined) => {
        if (!old) return old;
        return { ...old, conversations: old.conversations.filter((c) => c.follower_id !== conversationId), count: old.count - 1 };
      });
      return { previousData };
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) queryClient.setQueryData(apiKeys.conversations(creatorId), context.previousData);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

export function useMarkConversationSpam(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => markConversationSpam(creatorId, conversationId),
    onMutate: async (conversationId: string) => {
      await queryClient.cancelQueries({ queryKey: apiKeys.conversations(creatorId) });
      const previousData = queryClient.getQueryData(apiKeys.conversations(creatorId));
      queryClient.setQueryData(apiKeys.conversations(creatorId), (old: ConversationsResponse | undefined) => {
        if (!old) return old;
        return { ...old, conversations: old.conversations.filter((c) => c.follower_id !== conversationId), count: old.count - 1 };
      });
      return { previousData };
    },
    onError: (_err, _vars, context) => {
      if (context?.previousData) queryClient.setQueryData(apiKeys.conversations(creatorId), context.previousData);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

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

export function useArchivedConversations(creatorId: string = getCreatorId(), options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: apiKeys.archivedConversations(creatorId),
    queryFn: () => getArchivedConversations(creatorId),
    select: (data) => data.conversations || [],
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
    enabled: options?.enabled !== false,
  });
}

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
