/**
 * Clonnect API Service
 * Connects the frontend with the FastAPI backend
 */

import type {
  DashboardOverview,
  ConversationsResponse,
  LeadsResponse,
  MetricsResponse,
  CreatorConfig,
  ToggleResponse,
  Product,
  FollowerDetailResponse,
  RevenueStatsResponse,
  PurchasesResponse,
  BookingsResponse,
  CalendarStatsResponse,
  BookingLinksResponse,
} from "@/types/api";

// API Base URL from environment
const API_URL = import.meta.env.VITE_API_URL || "https://web-production-9f69.up.railway.app";
const CREATOR_ID = import.meta.env.VITE_CREATOR_ID || "manel";

/**
 * Generic fetch wrapper with error handling
 */
async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_URL}${endpoint}`;

  const defaultHeaders: HeadersInit = {
    "Content-Type": "application/json",
  };

  const response = await fetch(url, {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API Error: ${response.status}`);
  }

  return response.json();
}

// =============================================================================
// DASHBOARD
// =============================================================================

/**
 * Get dashboard overview data
 */
export async function getDashboardOverview(
  creatorId: string = CREATOR_ID
): Promise<DashboardOverview> {
  return apiFetch<DashboardOverview>(`/dashboard/${creatorId}/overview`);
}

/**
 * Toggle bot active status
 */
export async function toggleBot(
  creatorId: string = CREATOR_ID,
  active: boolean,
  reason: string = ""
): Promise<ToggleResponse> {
  return apiFetch<ToggleResponse>(
    `/dashboard/${creatorId}/toggle?active=${active}&reason=${encodeURIComponent(reason)}`,
    { method: "PUT" }
  );
}

// =============================================================================
// CONVERSATIONS / DM
// =============================================================================

/**
 * Get all conversations for a creator
 */
export async function getConversations(
  creatorId: string = CREATOR_ID,
  limit: number = 50
): Promise<ConversationsResponse> {
  return apiFetch<ConversationsResponse>(
    `/dm/conversations/${creatorId}?limit=${limit}`
  );
}

/**
 * Get leads for a creator
 */
export async function getLeads(
  creatorId: string = CREATOR_ID
): Promise<LeadsResponse> {
  return apiFetch<LeadsResponse>(`/dm/leads/${creatorId}`);
}

/**
 * Get metrics for a creator
 */
export async function getMetrics(
  creatorId: string = CREATOR_ID
): Promise<MetricsResponse> {
  return apiFetch<MetricsResponse>(`/dm/metrics/${creatorId}`);
}

/**
 * Get follower detail with conversation history
 */
export async function getFollowerDetail(
  creatorId: string = CREATOR_ID,
  followerId: string
): Promise<FollowerDetailResponse> {
  return apiFetch<FollowerDetailResponse>(`/dm/follower/${creatorId}/${followerId}`);
}

/**
 * Send a manual message to a follower
 */
export async function sendMessage(
  creatorId: string = CREATOR_ID,
  followerId: string,
  message: string
): Promise<{ status: string; sent: boolean; platform: string; follower_id: string }> {
  return apiFetch(`/dm/send/${creatorId}`, {
    method: "POST",
    body: JSON.stringify({ follower_id: followerId, message }),
  });
}

/**
 * Update the lead status for a follower
 */
export async function updateLeadStatus(
  creatorId: string = CREATOR_ID,
  followerId: string,
  status: "cold" | "warm" | "hot" | "customer"
): Promise<{ status: string; follower_id: string; new_status: string; purchase_intent: number }> {
  return apiFetch(`/dm/follower/${creatorId}/${followerId}/status`, {
    method: "PUT",
    body: JSON.stringify({ status }),
  });
}

/**
 * Create a manual lead
 */
export interface CreateLeadData {
  name: string;
  platform?: string;
  email?: string;
  phone?: string;
  notes?: string;
}

export async function createManualLead(
  creatorId: string = CREATOR_ID,
  data: CreateLeadData
): Promise<{ status: string; lead: any }> {
  return apiFetch(`/dm/leads/${creatorId}/manual`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Update a lead
 */
export interface UpdateLeadData {
  name?: string;
  email?: string;
  phone?: string;
  notes?: string;
  status?: string;
}

export async function updateLead(
  creatorId: string = CREATOR_ID,
  leadId: string,
  data: UpdateLeadData
): Promise<{ status: string; lead: any }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/**
 * Delete a lead
 */
export async function deleteLead(
  creatorId: string = CREATOR_ID,
  leadId: string
): Promise<{ status: string; deleted: boolean; lead_id: string }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}`, {
    method: "DELETE",
  });
}

// =============================================================================
// CREATOR CONFIG
// =============================================================================

/**
 * Get creator configuration
 */
export async function getCreatorConfig(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; config: CreatorConfig }> {
  return apiFetch(`/creator/config/${creatorId}`);
}

/**
 * Update creator configuration
 */
export async function updateCreatorConfig(
  creatorId: string = CREATOR_ID,
  config: Partial<CreatorConfig>
): Promise<{ status: string; config: CreatorConfig }> {
  return apiFetch(`/creator/config/${creatorId}`, {
    method: "PUT",
    body: JSON.stringify(config),
  });
}

// =============================================================================
// PRODUCTS
// =============================================================================

/**
 * Get products for a creator
 */
export async function getProducts(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; products: Product[]; count: number }> {
  return apiFetch(`/creator/${creatorId}/products`);
}

/**
 * Add a product
 */
export async function addProduct(
  creatorId: string = CREATOR_ID,
  product: Omit<Product, "id">
): Promise<{ status: string; product: Product }> {
  return apiFetch(`/creator/${creatorId}/products`, {
    method: "POST",
    body: JSON.stringify(product),
  });
}

/**
 * Update a product
 */
export async function updateProduct(
  creatorId: string = CREATOR_ID,
  productId: string,
  product: Partial<Product>
): Promise<{ status: string; product: Product }> {
  return apiFetch(`/creator/${creatorId}/products/${productId}`, {
    method: "PUT",
    body: JSON.stringify(product),
  });
}

/**
 * Delete a product
 */
export async function deleteProduct(
  creatorId: string = CREATOR_ID,
  productId: string
): Promise<{ status: string }> {
  return apiFetch(`/creator/${creatorId}/products/${productId}`, {
    method: "DELETE",
  });
}

// =============================================================================
// REVENUE / PAYMENTS
// =============================================================================

/**
 * Get revenue statistics
 */
export async function getRevenueStats(
  creatorId: string = CREATOR_ID,
  days: number = 30
): Promise<RevenueStatsResponse> {
  return apiFetch(`/payments/${creatorId}/revenue?days=${days}`);
}

/**
 * Get list of purchases
 */
export async function getPurchases(
  creatorId: string = CREATOR_ID,
  limit: number = 100,
  status?: string
): Promise<PurchasesResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.append("status", status);
  return apiFetch(`/payments/${creatorId}/purchases?${params}`);
}

/**
 * Record a new purchase
 */
export interface RecordPurchaseData {
  product_name: string;
  amount: number;
  currency: string;
  platform: string;
  status?: string;
  bot_attributed?: boolean;
  follower_id?: string;
}

export async function recordPurchase(
  creatorId: string = CREATOR_ID,
  data: RecordPurchaseData
): Promise<{ status: string; message: string }> {
  return apiFetch(`/payments/${creatorId}/purchases`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// =============================================================================
// CALENDAR / BOOKINGS
// =============================================================================

/**
 * Get bookings for a creator
 */
export async function getBookings(
  creatorId: string = CREATOR_ID,
  upcoming: boolean = false
): Promise<BookingsResponse> {
  return apiFetch(`/calendar/${creatorId}/bookings?upcoming=${upcoming}`);
}

/**
 * Get calendar statistics
 */
export async function getCalendarStats(
  creatorId: string = CREATOR_ID,
  days: number = 30
): Promise<CalendarStatsResponse> {
  return apiFetch(`/calendar/${creatorId}/stats?days=${days}`);
}

/**
 * Get booking links
 */
export async function getBookingLinks(
  creatorId: string = CREATOR_ID
): Promise<BookingLinksResponse> {
  return apiFetch(`/calendar/${creatorId}/links`);
}

/**
 * Get Calendly sync status
 */
export interface CalendlySyncStatus {
  status: string;
  calendly_connected: boolean;
  has_refresh_token: boolean;
  token_expires_at: string | null;
  bookings_synced: number;
  auto_refresh_enabled: boolean;
}

export async function getCalendlySyncStatus(
  creatorId: string = CREATOR_ID
): Promise<CalendlySyncStatus> {
  return apiFetch(`/calendar/${creatorId}/sync/status`);
}

/**
 * Create a booking link
 */
export interface CreateBookingLinkData {
  meeting_type: string;
  title: string;
  url?: string;  // Optional - auto-generated for Calendly
  platform: string;
  duration_minutes: number;
  description?: string;
}

export async function createBookingLink(
  creatorId: string = CREATOR_ID,
  data: CreateBookingLinkData
): Promise<{ status: string; link: any }> {
  return apiFetch(`/calendar/${creatorId}/links`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteBookingLink(
  creatorId: string = CREATOR_ID,
  linkId: string
): Promise<{ status: string }> {
  return apiFetch(`/calendar/${creatorId}/links/${linkId}`, {
    method: "DELETE",
  });
}

export async function cancelBooking(
  creatorId: string = CREATOR_ID,
  bookingId: string
): Promise<{ status: string; message: string }> {
  return apiFetch(`/calendar/${creatorId}/bookings/${bookingId}`, {
    method: "DELETE",
  });
}

export async function clearBookingHistory(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; message: string; deleted_count: number }> {
  return apiFetch(`/calendar/${creatorId}/history`, {
    method: "DELETE",
  });
}

export async function deleteHistoryItem(
  creatorId: string = CREATOR_ID,
  bookingId: string
): Promise<{ status: string; message: string }> {
  return apiFetch(`/calendar/${creatorId}/history/${bookingId}`, {
    method: "DELETE",
  });
}

// =============================================================================
// NURTURING
// =============================================================================

/**
 * Get nurturing sequences with stats
 */
export async function getNurturingSequences(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; sequences: any[]; stats: any }> {
  return apiFetch(`/nurturing/${creatorId}/sequences`);
}

/**
 * Get nurturing followups
 */
export async function getNurturingFollowups(
  creatorId: string = CREATOR_ID,
  status?: string
): Promise<{ status: string; followups: any[]; count: number }> {
  const params = new URLSearchParams();
  if (status) params.append("status", status);
  return apiFetch(`/nurturing/${creatorId}/followups?${params}`);
}

/**
 * Get nurturing stats
 */
export async function getNurturingStats(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; total: number; pending: number; sent: number; cancelled: number }> {
  return apiFetch(`/nurturing/${creatorId}/stats`);
}

/**
 * Toggle nurturing sequence on/off
 */
export async function toggleNurturingSequence(
  creatorId: string = CREATOR_ID,
  sequenceType: string
): Promise<{ status: string; sequence_type: string; is_active: boolean }> {
  return apiFetch(`/nurturing/${creatorId}/sequences/${sequenceType}/toggle`, {
    method: "POST",
  });
}

/**
 * Update nurturing sequence steps
 */
export async function updateNurturingSequence(
  creatorId: string = CREATOR_ID,
  sequenceType: string,
  steps: Array<{ delay_hours: number; message: string }>
): Promise<{ status: string; sequence_type: string; steps: any[] }> {
  return apiFetch(`/nurturing/${creatorId}/sequences/${sequenceType}`, {
    method: "PUT",
    body: JSON.stringify({ steps }),
  });
}

/**
 * Get enrolled followers for a sequence
 */
export async function getNurturingEnrolled(
  creatorId: string = CREATOR_ID,
  sequenceType: string
): Promise<{ status: string; enrolled: any[]; count: number }> {
  return apiFetch(`/nurturing/${creatorId}/sequences/${sequenceType}/enrolled`);
}

/**
 * Cancel nurturing for a follower
 */
export async function cancelNurturing(
  creatorId: string = CREATOR_ID,
  followerId: string,
  sequenceType?: string
): Promise<{ status: string; cancelled: number }> {
  const params = sequenceType ? `?sequence_type=${sequenceType}` : "";
  return apiFetch(`/nurturing/${creatorId}/cancel/${followerId}${params}`, {
    method: "DELETE",
  });
}

/**
 * Run nurturing followups (execute pending messages)
 */
export interface RunNurturingParams {
  dueOnly?: boolean;
  dryRun?: boolean;
  limit?: number;
  forceDue?: boolean;
}

export interface RunNurturingResponse {
  status: string;
  creator_id: string;
  dry_run: boolean;
  // dry_run=true response
  would_process?: number;
  items?: Array<{
    followup_id: string;
    follower_id: string;
    sequence_type: string;
    step: number;
    scheduled_at: string;
    message_preview: string;
    channel_guess: string;
  }>;
  // dry_run=false response
  processed?: number;
  sent?: number;
  simulated?: number;
  errors?: string[];
  by_sequence?: Record<string, { processed: number; sent: number; simulated: number; errors: number }>;
  stats_after?: { pending: number; sent: number; cancelled: number };
}

export async function runNurturing(
  creatorId: string = CREATOR_ID,
  params: RunNurturingParams = {}
): Promise<RunNurturingResponse> {
  const queryParams = new URLSearchParams();
  if (params.dueOnly !== undefined) queryParams.append("due_only", String(params.dueOnly));
  if (params.dryRun !== undefined) queryParams.append("dry_run", String(params.dryRun));
  if (params.limit !== undefined) queryParams.append("limit", String(params.limit));
  if (params.forceDue !== undefined) queryParams.append("force_due", String(params.forceDue));

  return apiFetch(`/nurturing/${creatorId}/run?${queryParams}`, {
    method: "POST",
  });
}

// =============================================================================
// CONTENT / RAG
// =============================================================================

/**
 * Add content to knowledge base
 */
export async function addContent(
  creatorId: string = CREATOR_ID,
  text: string,
  docType: string = "faq"
): Promise<{ status: string; doc_id: string }> {
  return apiFetch(`/content/add`, {
    method: "POST",
    body: JSON.stringify({
      creator_id: creatorId,
      text,
      doc_type: docType,
    }),
  });
}

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
  items: KnowledgeItem[];  // Legacy compatibility
  count: number;
}

/**
 * Get full knowledge base (FAQs + About)
 */
export async function getKnowledge(
  creatorId: string = CREATOR_ID
): Promise<FullKnowledge> {
  return apiFetch(`/creator/config/${creatorId}/knowledge`);
}

/**
 * Get FAQs only
 */
export async function getFAQs(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; items: FAQItem[]; count: number }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/faqs`);
}

/**
 * Add a FAQ
 */
export async function addFAQ(
  creatorId: string = CREATOR_ID,
  question: string,
  answer: string
): Promise<{ status: string; item: FAQItem }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/faqs`, {
    method: "POST",
    body: JSON.stringify({ question, answer }),
  });
}

/**
 * Delete a FAQ
 */
export async function deleteFAQ(
  creatorId: string = CREATOR_ID,
  itemId: string
): Promise<{ status: string }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/faqs/${itemId}`, {
    method: "DELETE",
  });
}

/**
 * Get About Me/Business info
 */
export async function getAbout(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; about: AboutInfo }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/about`);
}

/**
 * Update About Me/Business info
 */
export async function updateAbout(
  creatorId: string = CREATOR_ID,
  data: AboutInfo
): Promise<{ status: string }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/about`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/**
 * Generate knowledge using AI
 */
export async function generateKnowledge(
  prompt: string,
  type: "faqs" | "about" = "faqs"
): Promise<{ faqs?: FAQItem[]; about?: AboutInfo; source: string }> {
  return apiFetch(`/api/ai/generate-knowledge`, {
    method: "POST",
    body: JSON.stringify({ prompt, type }),
  });
}

/**
 * Delete a knowledge base item (legacy)
 */
export async function deleteKnowledge(
  creatorId: string = CREATOR_ID,
  itemId: string
): Promise<{ status: string }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/${itemId}`, {
    method: "DELETE",
  });
}

// =============================================================================
// CONVERSATION ACTIONS
// =============================================================================

/**
 * Archive a conversation
 */
export async function archiveConversation(
  creatorId: string = CREATOR_ID,
  conversationId: string
): Promise<{ status: string }> {
  return apiFetch(`/dm/conversations/${creatorId}/${conversationId}/archive`, {
    method: "POST",
  });
}

/**
 * Mark a conversation as spam
 */
export async function markConversationSpam(
  creatorId: string = CREATOR_ID,
  conversationId: string
): Promise<{ status: string }> {
  return apiFetch(`/dm/conversations/${creatorId}/${conversationId}/spam`, {
    method: "POST",
  });
}

/**
 * Delete a conversation
 */
export async function deleteConversation(
  creatorId: string = CREATOR_ID,
  conversationId: string
): Promise<{ status: string }> {
  return apiFetch(`/dm/conversations/${creatorId}/${conversationId}`, {
    method: "DELETE",
  });
}

/**
 * Get archived/spam conversations
 */
export async function getArchivedConversations(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; conversations: Conversation[] }> {
  return apiFetch(`/dm/conversations/${creatorId}/archived`);
}

/**
 * Restore an archived/spam conversation
 */
export async function restoreConversation(
  creatorId: string = CREATOR_ID,
  conversationId: string
): Promise<{ status: string; restored?: boolean }> {
  return apiFetch(`/dm/conversations/${creatorId}/${conversationId}/restore`, {
    method: "POST",
  });
}

// =============================================================================
// HOOKS (React Query)
// =============================================================================

export const apiKeys = {
  dashboard: (creatorId: string) => ["dashboard", creatorId] as const,
  conversations: (creatorId: string) => ["conversations", creatorId] as const,
  archivedConversations: (creatorId: string) => ["archivedConversations", creatorId] as const,
  follower: (creatorId: string, followerId: string) => ["follower", creatorId, followerId] as const,
  leads: (creatorId: string) => ["leads", creatorId] as const,
  metrics: (creatorId: string) => ["metrics", creatorId] as const,
  config: (creatorId: string) => ["config", creatorId] as const,
  products: (creatorId: string) => ["products", creatorId] as const,
  revenue: (creatorId: string, days: number) => ["revenue", creatorId, days] as const,
  purchases: (creatorId: string) => ["purchases", creatorId] as const,
  bookings: (creatorId: string, upcoming: boolean) => ["bookings", creatorId, upcoming] as const,
  calendarStats: (creatorId: string) => ["calendarStats", creatorId] as const,
  bookingLinks: (creatorId: string) => ["bookingLinks", creatorId] as const,
  nurturingSequences: (creatorId: string) => ["nurturingSequences", creatorId] as const,
  nurturingStats: (creatorId: string) => ["nurturingStats", creatorId] as const,
  nurturingFollowups: (creatorId: string) => ["nurturingFollowups", creatorId] as const,
  knowledge: (creatorId: string) => ["knowledge", creatorId] as const,
  connections: (creatorId: string) => ["connections", creatorId] as const,
};

// =============================================================================
// CONNECTIONS
// =============================================================================

export interface ConnectionStatus {
  connected: boolean;
  username?: string;
  masked_token?: string;
}

export interface AllConnections {
  instagram: ConnectionStatus;
  telegram: ConnectionStatus;
  whatsapp: ConnectionStatus;
  stripe: ConnectionStatus;
  paypal: ConnectionStatus;
  hotmart: ConnectionStatus;
  calendly: ConnectionStatus;
}

export interface UpdateConnectionData {
  token?: string;
  page_id?: string;
  phone_id?: string;
}

export async function getConnections(
  creatorId: string = CREATOR_ID
): Promise<AllConnections> {
  return apiFetch(`/connections/${creatorId}`);
}

export async function updateConnection(
  creatorId: string = CREATOR_ID,
  platform: string,
  data: UpdateConnectionData
): Promise<{ status: string; platform: string }> {
  return apiFetch(`/connections/${creatorId}/${platform}`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function disconnectPlatform(
  creatorId: string = CREATOR_ID,
  platform: string
): Promise<{ status: string; platform: string }> {
  return apiFetch(`/connections/${creatorId}/${platform}`, {
    method: "DELETE",
  });
}

// =============================================================================
// OAUTH
// =============================================================================

export interface OAuthStartResponse {
  auth_url: string;
  state: string;
}

export async function startOAuth(
  platform: string,
  creatorId: string = CREATOR_ID
): Promise<OAuthStartResponse> {
  return apiFetch(`/oauth/${platform}/start?creator_id=${creatorId}`);
}

// Default export for convenience
export default {
  getDashboardOverview,
  toggleBot,
  getConversations,
  getLeads,
  getMetrics,
  getFollowerDetail,
  sendMessage,
  updateLeadStatus,
  getCreatorConfig,
  updateCreatorConfig,
  getProducts,
  addProduct,
  updateProduct,
  deleteProduct,
  getRevenueStats,
  getPurchases,
  getBookings,
  getCalendarStats,
  getBookingLinks,
  getCalendlySyncStatus,
  createBookingLink,
  deleteBookingLink,
  getNurturingSequences,
  getNurturingFollowups,
  getNurturingStats,
  toggleNurturingSequence,
  updateNurturingSequence,
  getNurturingEnrolled,
  cancelNurturing,
  runNurturing,
  addContent,
  getKnowledge,
  getFAQs,
  addFAQ,
  deleteFAQ,
  getAbout,
  updateAbout,
  generateKnowledge,
  deleteKnowledge,
  apiKeys,
  CREATOR_ID,
  API_URL,
};
