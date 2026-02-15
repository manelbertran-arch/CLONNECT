import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  addContent, getKnowledge, deleteKnowledge,
  addFAQ, deleteFAQ, updateFAQ,
  updateAbout, generateKnowledge,
  apiKeys, getCreatorId,
} from "@/services/api";

export function useAddContent(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ text, docType = "faq" }: { text: string; docType?: string }) => addContent(creatorId, text, docType),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) }); },
  });
}

export function useKnowledge(creatorId: string = getCreatorId()) {
  return useQuery({ queryKey: apiKeys.knowledge(creatorId), queryFn: () => getKnowledge(creatorId), staleTime: 60 * 1000 });
}

export function useDeleteKnowledge(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deleteKnowledge(creatorId, itemId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) }); },
  });
}

export function useAddFAQ(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ question, answer }: { question: string; answer: string }) => addFAQ(creatorId, question, answer),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) }); },
  });
}

export function useDeleteFAQ(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (itemId: string) => deleteFAQ(creatorId, itemId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) }); },
  });
}

export function useUpdateFAQ(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ itemId, question, answer }: { itemId: string; question: string; answer: string }) => updateFAQ(creatorId, itemId, { question, answer }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) }); },
  });
}

export function useGenerateKnowledge() {
  return useMutation({
    mutationFn: ({ prompt, type }: { prompt: string; type: "faqs" | "about" }) => generateKnowledge(prompt, type),
  });
}

export function useUpdateAbout(creatorId: string = getCreatorId()) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { bio: string; specialties: string; experience: string; audience: string }) => updateAbout(creatorId, data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: apiKeys.knowledge(creatorId) }); },
  });
}
