import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getLeads, createManualLead, updateLead, deleteLead,
  getLeadActivities, createLeadActivity, deleteLeadActivity,
  getLeadTasks, createLeadTask, updateLeadTask, deleteLeadTask,
  getLeadStats, getEscalations,
  apiKeys, getCreatorId,
} from "@/services/api";
import type { CreateLeadData, UpdateLeadData, LeadTask } from "@/services/api";

export function useLeads(creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: apiKeys.leads(creatorId),
    queryFn: () => getLeads(creatorId),
    refetchInterval: 30000,
    staleTime: 60000,
    gcTime: 5 * 60 * 1000,
  });
}

export function useCreateManualLead(creatorId: string = getCreatorId()) {
  return useMutation({ mutationFn: (data: CreateLeadData) => createManualLead(creatorId, data) });
}

export function useUpdateLead(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: string; data: UpdateLeadData }) => updateLead(creatorId, leadId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: apiKeys.leads(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.follower(creatorId, variables.leadId) });
    },
  });
}

export function useDeleteLead(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (leadId: string) => deleteLead(creatorId, leadId),
    onMutate: async (leadId: string) => {
      await queryClient.cancelQueries({ queryKey: apiKeys.conversations(creatorId) });
      const previousData = queryClient.getQueryData([...apiKeys.conversations(creatorId), "infinite"]);
      queryClient.setQueryData(
        [...apiKeys.conversations(creatorId), "infinite"],
        (old: { pages: Array<{ conversations: Array<{ id?: string; follower_id: string }> }> } | undefined) => {
          if (!old) return old;
          return { ...old, pages: old.pages.map(page => ({ ...page, conversations: page.conversations.filter(c => c.id !== leadId && c.follower_id !== leadId) })) };
        }
      );
      return { previousData };
    },
    onError: (_err, _leadId, context) => {
      if (context?.previousData) queryClient.setQueryData([...apiKeys.conversations(creatorId), "infinite"], context.previousData);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.dashboard(creatorId) });
    },
  });
}

export function useLeadActivities(leadId: string | null, creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: ["leadActivities", creatorId, leadId],
    queryFn: () => getLeadActivities(creatorId, leadId!),
    enabled: !!leadId,
    staleTime: 60000,
    gcTime: 5 * 60 * 1000,
  });
}

export function useCreateLeadActivity(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: string; data: { activity_type: string; description: string } }) => createLeadActivity(creatorId, leadId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["leadActivities", creatorId, variables.leadId] });
      queryClient.invalidateQueries({ queryKey: apiKeys.leads(creatorId) });
      queryClient.invalidateQueries({ queryKey: apiKeys.conversations(creatorId) });
    },
  });
}

export function useDeleteLeadActivity(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, activityId }: { leadId: string; activityId: string }) => deleteLeadActivity(creatorId, leadId, activityId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["leadActivities", creatorId, variables.leadId] });
    },
  });
}

export function useLeadTasks(leadId: string | null, creatorId: string = getCreatorId(), includeCompleted: boolean = false) {
  return useQuery({
    queryKey: ["leadTasks", creatorId, leadId, includeCompleted],
    queryFn: () => getLeadTasks(creatorId, leadId!, includeCompleted),
    enabled: !!leadId,
    staleTime: 60000,
    gcTime: 5 * 60 * 1000,
  });
}

export function useCreateLeadTask(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, data }: { leadId: string; data: { title: string; description?: string; task_type?: string; priority?: string; due_date?: string } }) => createLeadTask(creatorId, leadId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["leadTasks", creatorId, variables.leadId] });
      queryClient.invalidateQueries({ queryKey: ["leadActivities", creatorId, variables.leadId] });
    },
  });
}

export function useUpdateLeadTask(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, taskId, data }: { leadId: string; taskId: string; data: Partial<LeadTask> }) => updateLeadTask(creatorId, leadId, taskId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["leadTasks", creatorId, variables.leadId] });
      queryClient.invalidateQueries({ queryKey: ["leadActivities", creatorId, variables.leadId] });
    },
  });
}

export function useDeleteLeadTask(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, taskId }: { leadId: string; taskId: string }) => deleteLeadTask(creatorId, leadId, taskId),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ["leadTasks", creatorId, variables.leadId] });
    },
  });
}

export function useLeadStats(leadId: string | null, creatorId: string = getCreatorId()) {
  return useQuery({
    queryKey: ["leadStats", creatorId, leadId],
    queryFn: () => getLeadStats(creatorId, leadId!),
    enabled: !!leadId,
    staleTime: 60000,
    gcTime: 5 * 60 * 1000,
  });
}

export function useEscalations(creatorId: string = getCreatorId(), limit: number = 50) {
  return useQuery({
    queryKey: apiKeys.escalations(creatorId),
    queryFn: () => getEscalations(creatorId, limit),
    refetchInterval: 60000,
    staleTime: 30000,
  });
}
