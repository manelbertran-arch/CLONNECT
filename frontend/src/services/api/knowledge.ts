import { apiFetch, CREATOR_ID } from "./client";

export interface KnowledgeItem {
  id: string;
  content: string;
  doc_type: string;
  created_at?: string;
}

export interface FAQItem {
  id: string;
  question: string;
  answer: string;
  created_at?: string;
}

export interface AboutInfo {
  bio?: string;
  specialties?: string[];
  experience?: string;
  target_audience?: string;
  [key: string]: unknown;
}

export interface FullKnowledge {
  status: string;
  faqs: FAQItem[];
  about: AboutInfo;
  items: KnowledgeItem[];
  count: number;
}

export async function addContent(creatorId: string = CREATOR_ID, text: string, docType: string = "faq"): Promise<{ status: string; doc_id: string }> {
  return apiFetch(`/content/add`, { method: "POST", body: JSON.stringify({ creator_id: creatorId, text, doc_type: docType }) });
}

export async function getKnowledge(creatorId: string = CREATOR_ID): Promise<FullKnowledge> {
  return apiFetch(`/creator/config/${creatorId}/knowledge`);
}

export async function getFAQs(creatorId: string = CREATOR_ID): Promise<{ status: string; items: FAQItem[]; count: number }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/faqs`);
}

export async function addFAQ(creatorId: string = CREATOR_ID, question: string, answer: string): Promise<{ status: string; item: FAQItem }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/faqs`, { method: "POST", body: JSON.stringify({ question, answer }) });
}

export async function deleteFAQ(creatorId: string = CREATOR_ID, itemId: string): Promise<{ status: string }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/faqs/${itemId}`, { method: "DELETE" });
}

export async function updateFAQ(creatorId: string = CREATOR_ID, itemId: string, data: { question: string; answer: string }): Promise<{ status: string; item: FAQItem }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/faqs/${itemId}`, { method: "PUT", body: JSON.stringify(data) });
}

export async function getAbout(creatorId: string = CREATOR_ID): Promise<{ status: string; about: AboutInfo }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/about`);
}

export async function updateAbout(creatorId: string = CREATOR_ID, data: AboutInfo): Promise<{ status: string }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/about`, { method: "PUT", body: JSON.stringify(data) });
}

export async function generateKnowledge(prompt: string, type: "faqs" | "about" = "faqs"): Promise<{ faqs?: FAQItem[]; about?: AboutInfo; source: string }> {
  return apiFetch(`/api/ai/generate-knowledge`, { method: "POST", body: JSON.stringify({ prompt, type }) });
}

export async function deleteKnowledge(creatorId: string = CREATOR_ID, itemId: string): Promise<{ status: string }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/${itemId}`, { method: "DELETE" });
}
