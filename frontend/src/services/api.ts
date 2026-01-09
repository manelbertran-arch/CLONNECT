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

// API Base URL - empty string means same origin (for Railway deployment)
// Falls back to Railway URL for local development
export const API_URL = import.meta.env.VITE_API_URL || "";

// Auth token storage key
const AUTH_TOKEN_KEY = "clonnect_auth_token";
const AUTH_USER_KEY = "clonnect_auth_user";

// Get auth token from localStorage
export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

// Set auth token in localStorage
export function setAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

// Clear auth token
export function clearAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
}

// Get stored user
export function getStoredUser(): AuthUser | null {
  const user = localStorage.getItem(AUTH_USER_KEY);
  return user ? JSON.parse(user) : null;
}

// Set stored user
export function setStoredUser(user: AuthUser): void {
  localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
}

// Auth types
export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
  creators: { id: string; name: string; clone_name: string; role: string }[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

// HARDCODED FOR DEMO - Forces stefano_auto (updated 2026-01-08)
export function getCreatorId(): string {
  // CRITICAL: Always return stefano_auto for demo
  return "stefano_auto";
}

// Legacy export for components that haven't been updated yet
export const CREATOR_ID = getCreatorId();

/**
 * Generic fetch wrapper with error handling
 */
async function apiFetch<T>(
  endpoint: string,
  options: RequestInit = {},
  skipAuth: boolean = false
): Promise<T> {
  const url = `${API_URL}${endpoint}`;

  const defaultHeaders: HeadersInit = {
    "Content-Type": "application/json",
  };

  // Add auth token if available and not skipping auth
  const token = getAuthToken();
  if (token && !skipAuth) {
    (defaultHeaders as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    // Handle validation errors (422) which have detail as array
    let errorMessage = `API Error: ${response.status}`;
    if (errorData.detail) {
      if (Array.isArray(errorData.detail)) {
        // Pydantic validation errors
        errorMessage = errorData.detail.map((e: any) => `${e.loc?.join('.')}: ${e.msg}`).join(', ');
      } else {
        errorMessage = String(errorData.detail);
      }
    }
    console.error(`API Error ${response.status}:`, errorData);
    throw new Error(errorMessage);
  }

  return response.json();
}

// =============================================================================
// AUTHENTICATION
// =============================================================================

/**
 * Login with email and password
 */
export async function login(email: string, password: string): Promise<LoginResponse> {
  const response = await apiFetch<LoginResponse>(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify({ email, password }),
    },
    true // Skip auth header for login
  );

  // Store token and user
  setAuthToken(response.access_token);
  setStoredUser(response.user);

  return response;
}

/**
 * Register a new user
 */
export async function register(
  email: string,
  password: string,
  name?: string
): Promise<LoginResponse> {
  const response = await apiFetch<LoginResponse>(
    "/auth/register",
    {
      method: "POST",
      body: JSON.stringify({ email, password, name }),
    },
    true // Skip auth header for register
  );

  // Store token and user
  setAuthToken(response.access_token);
  setStoredUser(response.user);

  return response;
}

/**
 * Get current user info
 */
export async function getCurrentUser(): Promise<AuthUser> {
  const response = await apiFetch<{
    id: string;
    email: string;
    name: string | null;
    is_active: boolean;
    creators: { id: string; name: string; clone_name: string; role: string }[];
  }>("/auth/me");

  const user: AuthUser = {
    id: response.id,
    email: response.email,
    name: response.name,
    creators: response.creators,
  };

  setStoredUser(user);
  return user;
}

/**
 * Logout - clear stored auth data
 */
export function logout(): void {
  clearAuthToken();
}

/**
 * Check if user is authenticated
 */
export function isAuthenticated(): boolean {
  return !!getAuthToken();
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
 * Get products for a creator (includes paused products)
 */
export async function getProducts(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; products: Product[]; count: number }> {
  return apiFetch(`/creator/${creatorId}/products?active_only=false`);
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
    body: JSON.stringify({}),  // Send empty body to avoid FastAPI parsing issues
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
 * Update an existing FAQ
 */
export async function updateFAQ(
  creatorId: string = CREATOR_ID,
  itemId: string,
  data: { question: string; answer: string }
): Promise<{ status: string; item: FAQItem }> {
  return apiFetch(`/creator/config/${creatorId}/knowledge/faqs/${itemId}`, {
    method: "PUT",
    body: JSON.stringify(data),
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

// =============================================================================
// COPILOT MODE
// =============================================================================

export interface PendingResponse {
  id: string;
  lead_id: string;
  follower_id: string;
  platform: string;
  username: string;
  full_name: string;
  user_message: string;
  suggested_response: string;
  intent: string;
  created_at: string;
  status: string;
}

export interface CopilotStatus {
  creator_id: string;
  copilot_enabled: boolean;
  pending_count: number;
  status: string;
}

export interface CopilotNotifications {
  creator_id: string;
  timestamp: string;
  new_messages_count: number;
  new_messages: any[];
  pending_count: number;
  pending_responses: PendingResponse[];
  hot_leads_count: number;
  hot_leads: any[];
}

/**
 * Get pending responses awaiting approval
 */
export async function getCopilotPending(
  creatorId: string = CREATOR_ID,
  limit: number = 50
): Promise<{ creator_id: string; pending_count: number; pending_responses: PendingResponse[] }> {
  return apiFetch(`/copilot/${creatorId}/pending?limit=${limit}`);
}

/**
 * Get copilot status
 */
export async function getCopilotStatus(
  creatorId: string = CREATOR_ID
): Promise<CopilotStatus> {
  return apiFetch(`/copilot/${creatorId}/status`);
}

/**
 * Approve a pending response
 */
export async function approveCopilotResponse(
  creatorId: string = CREATOR_ID,
  messageId: string,
  editedText?: string
): Promise<{ success: boolean; message_id: string; was_edited: boolean; final_text: string }> {
  return apiFetch(`/copilot/${creatorId}/approve/${messageId}`, {
    method: "POST",
    body: JSON.stringify({ edited_text: editedText }),
  });
}

/**
 * Discard a pending response
 */
export async function discardCopilotResponse(
  creatorId: string = CREATOR_ID,
  messageId: string
): Promise<{ success: boolean; message_id: string }> {
  return apiFetch(`/copilot/${creatorId}/discard/${messageId}`, {
    method: "POST",
  });
}

/**
 * Toggle copilot mode
 */
export async function toggleCopilotMode(
  creatorId: string = CREATOR_ID,
  enabled: boolean
): Promise<{ creator_id: string; copilot_enabled: boolean; message: string }> {
  return apiFetch(`/copilot/${creatorId}/toggle`, {
    method: "PUT",
    body: JSON.stringify({ enabled }),
  });
}

/**
 * Get real-time notifications (polling)
 */
export async function getCopilotNotifications(
  creatorId: string = CREATOR_ID,
  since?: string
): Promise<CopilotNotifications> {
  const params = since ? `?since=${encodeURIComponent(since)}` : "";
  return apiFetch(`/copilot/${creatorId}/notifications${params}`);
}

/**
 * Approve all pending responses
 */
export async function approveAllCopilot(
  creatorId: string = CREATOR_ID
): Promise<{ creator_id: string; results: { approved: number; failed: number; errors: any[] } }> {
  return apiFetch(`/copilot/${creatorId}/approve-all`, {
    method: "POST",
  });
}

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
  onboardingTour: (creatorId: string) => ["onboardingTour", creatorId] as const,
  setupProgress: (creatorId: string) => ["setupProgress", creatorId] as const,
  copilotPending: (creatorId: string) => ["copilotPending", creatorId] as const,
  copilotStatus: (creatorId: string) => ["copilotStatus", creatorId] as const,
  copilotNotifications: (creatorId: string) => ["copilotNotifications", creatorId] as const,
  toneProfile: (creatorId: string) => ["toneProfile", creatorId] as const,
  contentStats: (creatorId: string) => ["contentStats", creatorId] as const,
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

// =============================================================================
// VISUAL ONBOARDING
// =============================================================================

export interface VisualOnboardingStatus {
  status: string;
  onboarding_completed: boolean;
}

/**
 * Get visual onboarding status (if the intro tour has been completed)
 */
export async function getVisualOnboardingStatus(
  creatorId: string = CREATOR_ID
): Promise<VisualOnboardingStatus> {
  return apiFetch(`/onboarding/${creatorId}/visual-status`);
}

/**
 * Mark the visual onboarding tour as completed
 */
export async function completeVisualOnboarding(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; message: string }> {
  return apiFetch(`/onboarding/${creatorId}/complete`, {
    method: "POST",
  });
}

// =============================================================================
// FULL SETUP (ONBOARDING)
// =============================================================================

export interface SetupProgress {
  status: "not_started" | "in_progress" | "completed" | "error";
  progress: number;
  current_step?: string;
  steps: {
    instagram_connected: boolean;
    posts_imported: number;
    tone_profile_generated: boolean;
    tone_summary: string | null;
    content_indexed: number;
    dms_imported: number;
    leads_created: number;
    youtube_detected: boolean;
    youtube_videos_imported: number;
    website_detected: boolean;
    website_url: string | null;
  };
  errors: string[];
}

/**
 * Start full setup process (background task)
 */
export async function startFullSetup(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; message: string; creator_id: string }> {
  return apiFetch(`/onboarding/full-setup/${creatorId}`, {
    method: "POST",
  });
}

/**
 * Get full setup progress
 */
export async function getSetupProgress(
  creatorId: string = CREATOR_ID
): Promise<SetupProgress> {
  return apiFetch(`/onboarding/full-setup/${creatorId}/progress`);
}

// =============================================================================
// TONE PROFILE
// =============================================================================

export interface ToneProfile {
  formality: number;      // 0-100
  energy: number;         // 0-100
  warmth: number;         // 0-100
  emoji_usage: number;    // 0-100
  summary: string;
  generated_at?: string;
}

export interface ContentStats {
  posts_count: number;
  videos_count: number;
  pdfs_count: number;
  audios_count: number;
  total_indexed: number;
}

/**
 * Get tone profile for a creator
 */
export async function getToneProfile(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; tone_profile: ToneProfile | null }> {
  return apiFetch(`/creator/${creatorId}/tone-profile`);
}

/**
 * Regenerate tone profile from content
 */
export async function regenerateToneProfile(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; tone_profile: ToneProfile; message: string }> {
  return apiFetch(`/creator/${creatorId}/tone-profile/regenerate`, {
    method: "POST",
  });
}

/**
 * Get content statistics
 */
export async function getContentStats(
  creatorId: string = CREATOR_ID
): Promise<{ status: string; stats: ContentStats }> {
  return apiFetch(`/creator/${creatorId}/content-stats`);
}

// =============================================================================
// TEST CLONE
// =============================================================================

export interface TestCloneResponse {
  status: string;
  response: string;
  sources?: string[];
  tone_applied: boolean;
}

/**
 * Test the clone with a sample message
 */
export async function testClone(
  creatorId: string = CREATOR_ID,
  message: string
): Promise<TestCloneResponse> {
  return apiFetch(`/clone/${creatorId}/test`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
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
  updateFAQ,
  getAbout,
  updateAbout,
  generateKnowledge,
  deleteKnowledge,
  getVisualOnboardingStatus,
  completeVisualOnboarding,
  startFullSetup,
  getSetupProgress,
  getToneProfile,
  regenerateToneProfile,
  getContentStats,
  testClone,
  // Copilot
  getCopilotPending,
  getCopilotStatus,
  approveCopilotResponse,
  discardCopilotResponse,
  toggleCopilotMode,
  getCopilotNotifications,
  approveAllCopilot,
  apiKeys,
  CREATOR_ID,
  API_URL,
};
// =============================================================================
// AXIOS-LIKE API WRAPPER
// =============================================================================

/**
 * Simple axios-like API wrapper for cleaner syntax
 */
export const api = {
  async get<T = any>(endpoint: string): Promise<{ data: T }> {
    const data = await apiFetch<T>(endpoint);
    return { data };
  },

  async post<T = any>(endpoint: string, body?: any): Promise<{ data: T }> {
    const data = await apiFetch<T>(endpoint, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
    return { data };
  },

  async put<T = any>(endpoint: string, body?: any): Promise<{ data: T }> {
    const data = await apiFetch<T>(endpoint, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    });
    return { data };
  },

  async delete<T = any>(endpoint: string): Promise<{ data: T }> {
    const data = await apiFetch<T>(endpoint, {
      method: "DELETE",
    });
    return { data };
  },
};

// Force redeploy 1767880558
// Force deploy jueves,  8 de enero de 2026, 15:45:57 CET
