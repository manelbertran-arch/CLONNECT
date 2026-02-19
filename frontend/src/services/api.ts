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
// Falls back to same origin for production, local dev uses env variable
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

// P1 FIX: Dynamic creator ID from localStorage/auth
const DEFAULT_CREATOR_ID = import.meta.env.VITE_CREATOR_ID || "fitpack_global";  // From env or fallback
const CREATOR_ID_KEY = "clonnect_selected_creator";  // Must match AuthContext
const LEGACY_CREATOR_ID_KEY = "creator_id";  // Legacy key for backwards compatibility

export function getCreatorId(): string {
  // Priority order:
  // 1. New key (AuthContext)
  // 2. Legacy key (old code)
  // 3. Default fallback for demo
  const stored = localStorage.getItem(CREATOR_ID_KEY);
  if (stored) {
    return stored;
  }
  // Check legacy key
  const legacy = localStorage.getItem(LEGACY_CREATOR_ID_KEY);
  if (legacy) {
    // Migrate to new key
    localStorage.setItem(CREATOR_ID_KEY, legacy);
    return legacy;
  }
  return DEFAULT_CREATOR_ID;
}

// Helper to set creator ID on login
export function setCreatorId(creatorId: string): void {
  localStorage.setItem(CREATOR_ID_KEY, creatorId);
  // Also set legacy key for backwards compatibility
  localStorage.setItem(LEGACY_CREATOR_ID_KEY, creatorId);
}

// Helper to clear creator ID on logout
export function clearCreatorId(): void {
  localStorage.removeItem(CREATOR_ID_KEY);
  localStorage.removeItem(LEGACY_CREATOR_ID_KEY);
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
 * Get all conversations for a creator with pagination support
 */
export async function getConversations(
  creatorId: string = CREATOR_ID,
  limit: number = 50,
  offset: number = 0
): Promise<ConversationsResponse> {
  return apiFetch<ConversationsResponse>(
    `/dm/conversations/${creatorId}?limit=${limit}&offset=${offset}`
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
 * Mark a conversation as read
 */
export async function markConversationRead(
  creatorId: string = CREATOR_ID,
  followerId: string
): Promise<{ status: string; message: string }> {
  return apiFetch(`/dm/conversations/${creatorId}/${followerId}/mark-read`, {
    method: "POST",
  });
}

/**
 * Update the lead status for a follower
 * Nuevo embudo: nuevo, interesado, caliente, cliente, fantasma
 */
export async function updateLeadStatus(
  creatorId: string = CREATOR_ID,
  followerId: string,
  status: string // nuevo | interesado | caliente | cliente | fantasma
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
// LEAD ACTIVITIES & TASKS (CRM)
// =============================================================================

export interface LeadActivity {
  id: string;
  activity_type: string;
  description: string;
  old_value?: string;
  new_value?: string;
  metadata?: Record<string, any>;
  created_by?: string;
  created_at: string;
}

export interface LeadTask {
  id: string;
  title: string;
  description?: string;
  task_type: string;
  priority: string;
  status: string;
  due_date?: string;
  completed_at?: string;
  assigned_to?: string;
  created_at: string;
}

/**
 * Get activities for a lead
 */
export async function getLeadActivities(
  creatorId: string = CREATOR_ID,
  leadId: string,
  limit: number = 50
): Promise<{ status: string; activities: LeadActivity[] }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/activities?limit=${limit}`);
}

/**
 * Create an activity for a lead (note, call, etc.)
 */
export async function createLeadActivity(
  creatorId: string = CREATOR_ID,
  leadId: string,
  data: { activity_type: string; description: string; metadata?: Record<string, any> }
): Promise<{ status: string; activity: LeadActivity }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/activities`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Get tasks for a lead
 */
export async function getLeadTasks(
  creatorId: string = CREATOR_ID,
  leadId: string,
  includeCompleted: boolean = false
): Promise<{ status: string; tasks: LeadTask[] }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/tasks?include_completed=${includeCompleted}`);
}

/**
 * Create a task for a lead
 */
export async function createLeadTask(
  creatorId: string = CREATOR_ID,
  leadId: string,
  data: { title: string; description?: string; task_type?: string; priority?: string; due_date?: string }
): Promise<{ status: string; task: LeadTask }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/tasks`, {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/**
 * Update a task
 */
export async function updateLeadTask(
  creatorId: string = CREATOR_ID,
  leadId: string,
  taskId: string,
  data: Partial<LeadTask>
): Promise<{ status: string; task: LeadTask }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/tasks/${taskId}`, {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

/**
 * Delete a task
 */
export async function deleteLeadTask(
  creatorId: string = CREATOR_ID,
  leadId: string,
  taskId: string
): Promise<{ status: string; message: string }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/tasks/${taskId}`, {
    method: "DELETE",
  });
}

/**
 * Delete a lead activity from history
 */
export async function deleteLeadActivity(
  creatorId: string = CREATOR_ID,
  leadId: string,
  activityId: string
): Promise<{ status: string; message: string }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/activities/${activityId}`, {
    method: "DELETE",
  });
}

/**
 * Detected signal from conversation analysis
 */
export interface DetectedSignal {
  signal: string;
  keyword_found?: string;
  weight: number;
  category: "compra" | "interes" | "objecion" | "comportamiento";
  emoji: string;
  description: string;
  detail?: string;
}

/**
 * Detected product from conversation
 */
export interface DetectedProduct {
  id: string;
  name: string;
  keyword_found: string;
  estimated_price: number;
  emoji: string;
}

/**
 * Next step suggestion
 */
export interface NextStep {
  accion: string;
  emoji: string;
  texto: string;
  prioridad: "urgente" | "alta" | "media" | "baja";
}

/**
 * Behavior metrics
 */
export interface BehaviorMetrics {
  tiempo_respuesta_promedio: string | null;
  tiempo_respuesta_segundos: number | null;
  longitud_mensaje_promedio: number;
  cantidad_preguntas: number;
  total_mensajes_lead: number;
  total_mensajes_bot: number;
  ratio_participacion: number;
}

/**
 * Lead stats for INTELLIGENT monitoring/analytics with prediction
 */
export interface LeadStats {
  // Core prediction
  probabilidad_venta: number;
  confianza_prediccion: "Alta" | "Media" | "Baja";
  producto_detectado: DetectedProduct | null;
  valor_estimado: number;

  // Signals
  senales_detectadas: DetectedSignal[];
  senales_por_categoria: {
    compra: DetectedSignal[];
    interes: DetectedSignal[];
    objecion: DetectedSignal[];
    comportamiento: DetectedSignal[];
  };
  total_senales: number;

  // Next step
  siguiente_paso: NextStep;

  // Engagement
  engagement: "Alto" | "Medio" | "Bajo";
  engagement_detalle: string;

  // Metrics
  metricas: BehaviorMetrics;
  mensajes_lead: number;
  mensajes_bot: number;

  // Timeline
  primer_contacto: string | null;
  ultimo_contacto: string | null;
  current_stage: string;
}

/**
 * Get lead stats for monitoring
 */
export async function getLeadStats(
  creatorId: string = CREATOR_ID,
  leadId: string
): Promise<{ status: string; stats: LeadStats }> {
  return apiFetch(`/dm/leads/${creatorId}/${leadId}/stats`);
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
// AVAILABILITY
// =============================================================================

export interface DayAvailability {
  day_of_week: number;  // 0=Monday, 6=Sunday
  day_name?: string;
  start_time: string;   // "09:00"
  end_time: string;     // "18:00"
  is_active: boolean;
}

export interface AvailabilityResponse {
  status: string;
  creator_id: string;
  availability: DayAvailability[];
}

/**
 * Get creator's weekly availability schedule
 */
export async function getAvailability(
  creatorId: string = CREATOR_ID
): Promise<AvailabilityResponse> {
  return apiFetch(`/booking/availability/${creatorId}`);
}

/**
 * Set creator's weekly availability schedule
 */
export async function setAvailability(
  creatorId: string = CREATOR_ID,
  days: DayAvailability[]
): Promise<{ status: string; message: string; days_set: number }> {
  return apiFetch(`/booking/availability/${creatorId}`, {
    method: "POST",
    body: JSON.stringify(days),
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
  limit: number = 500
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

export interface CopilotStats {
  creator_id: string;
  period_days: number;
  total_actions: number;
  approved: number;
  edited: number;
  discarded: number;
  manual_override: number;
  approval_rate: number;
  edit_rate: number;
  discard_rate: number;
  manual_rate: number;
  avg_response_time_ms: number | null;
  avg_confidence: number | null;
  edit_categories: Record<string, number>;
}

export interface CopilotComparison {
  message_id: string;
  bot_original: string;
  creator_final: string;
  action: string;
  edit_diff: { length_delta: number; categories: string[] } | null;
  confidence: number | null;
  response_time_ms: number | null;
  created_at: string;
  username: string;
  platform: string;
}

export async function getCopilotStats(
  creatorId: string = CREATOR_ID,
  days: number = 30
): Promise<CopilotStats> {
  return apiFetch(`/copilot/${creatorId}/stats?days=${days}`);
}

export async function getCopilotComparisons(
  creatorId: string = CREATOR_ID,
  limit: number = 500
): Promise<{ creator_id: string; comparisons: CopilotComparison[]; count: number; has_more: boolean }> {
  return apiFetch(`/copilot/${creatorId}/comparisons?limit=${limit}`);
}

// =============================================================================
// ESCALATIONS
// =============================================================================

export interface EscalationAlert {
  creator_id: string;
  follower_id: string;
  follower_username: string;
  follower_name: string;
  reason: string;
  last_message: string;
  conversation_summary: string;
  purchase_intent_score: number;
  total_messages: number;
  products_discussed: string[];
  timestamp: string;
  notification_type: string;
  read?: boolean;
}

export interface EscalationsResponse {
  status: string;
  creator_id: string;
  alerts: EscalationAlert[];
  total: number;
  unread: number;
}

/**
 * Get escalation alerts for a creator
 * Returns leads that need human attention (requested escalation, high intent, etc.)
 */
export async function getEscalations(
  creatorId: string = CREATOR_ID,
  limit: number = 50,
  unreadOnly: boolean = false
): Promise<EscalationsResponse> {
  const params = new URLSearchParams();
  params.append("limit", limit.toString());
  if (unreadOnly) params.append("unread_only", "true");
  return apiFetch(`/dm/leads/${creatorId}/escalations?${params.toString()}`);
}

// =============================================================================
// INTELLIGENCE - Business Analytics & Predictions
// =============================================================================

export interface IntelligenceDashboardResponse {
  status: string;
  creator_id: string;
  generated_at: string;
  analysis_period_days: number;
  patterns: {
    temporal: {
      best_hours: Array<{ hour: number; messages: number; users: number }>;
      best_days: Array<{ day: string; messages: number; users: number }>;
      peak_activity_hour: number;
      peak_activity_day: string;
    };
    conversation: {
      intent_distribution: Record<string, number>;
      avg_messages_per_user: number;
      max_messages_per_user: number;
    };
    conversion: {
      top_products_mentioned: Array<{ name: string; mentions: number }>;
    };
  };
  predictions: {
    hot_leads: LeadPrediction[];
    total_hot_leads: number;
    churn_risks: ChurnRisk[];
    total_at_risk: number;
    revenue_forecast: RevenueForecast;
  };
  recommendations: Recommendation[];
  kpis: {
    peak_activity_hour: number;
    peak_activity_day: string;
    avg_messages_per_user: number;
    intent_distribution: Record<string, number>;
  };
}

export interface LeadPrediction {
  lead_id: string;
  username: string;
  status: string;
  conversion_probability: number;
  confidence: number;
  factors: {
    engagement_level: number;
    current_score: number;
    days_since_last_activity: number;
  };
  recommended_action: string;
}

export interface ChurnRisk {
  lead_id: string;
  username: string;
  status: string;
  churn_risk: number;
  days_inactive: number;
  recovery_action: string;
}

export interface RevenueForecast {
  current_weekly_avg: number;
  growth_trend: number;
  forecasts: Array<{
    week: number;
    projected_revenue: number;
    confidence: number;
  }>;
}

export interface Recommendation {
  category: 'content' | 'action' | 'product' | 'pricing' | 'timing';
  priority: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  reasoning?: string;
  data_points?: Record<string, any>;
  expected_impact?: Record<string, string | number>;
  action_type?: string;
  action_data?: Record<string, any>;
}

export interface WeeklyReportResponse {
  status: string;
  creator_id: string;
  report: {
    period: { start: string; end: string };
    metrics_summary: {
      conversations: number;
      messages: number;
      new_leads: number;
      conversions: number;
      revenue: number;
      conversion_rate: number;
    };
    vs_previous_week: Record<string, number>;
    patterns: Record<string, any>;
    predictions: {
      hot_leads: LeadPrediction[];
      churn_risks: ChurnRisk[];
      revenue_forecast: RevenueForecast;
    };
    recommendations: {
      content: Recommendation[];
      actions: Recommendation[];
      products: Recommendation[];
    };
    executive_summary: string;
    key_wins: string[];
    areas_to_improve: string[];
    this_week_focus: string[];
  };
}

/**
 * Get Intelligence Dashboard with KPIs, predictions, and recommendations
 */
export async function getIntelligenceDashboard(
  creatorId: string = getCreatorId(),
  days: number = 30
): Promise<IntelligenceDashboardResponse> {
  return apiFetch(`/intelligence/${creatorId}/dashboard?days=${days}`);
}

/**
 * Get predictions (conversion, churn, revenue)
 */
export async function getIntelligencePredictions(
  creatorId: string = getCreatorId(),
  predictionType?: 'conversion' | 'churn' | 'revenue'
): Promise<any> {
  const params = predictionType ? `?prediction_type=${predictionType}` : '';
  return apiFetch(`/intelligence/${creatorId}/predictions${params}`);
}

/**
 * Get recommendations by category
 */
export async function getIntelligenceRecommendations(
  creatorId: string = getCreatorId(),
  category?: 'content' | 'action' | 'product' | 'timing'
): Promise<any> {
  const params = category ? `?category=${category}` : '';
  return apiFetch(`/intelligence/${creatorId}/recommendations${params}`);
}

/**
 * Get pattern analysis
 */
export async function getIntelligencePatterns(
  creatorId: string = getCreatorId(),
  days: number = 30
): Promise<any> {
  return apiFetch(`/intelligence/${creatorId}/patterns?days=${days}`);
}

/**
 * Get weekly report
 */
export async function getWeeklyReport(
  creatorId: string = getCreatorId()
): Promise<WeeklyReportResponse> {
  return apiFetch(`/intelligence/${creatorId}/report/weekly`);
}

/**
 * Generate new weekly report
 */
export async function generateWeeklyReport(
  creatorId: string = getCreatorId()
): Promise<WeeklyReportResponse> {
  return apiFetch(`/intelligence/${creatorId}/report/generate`, {
    method: 'POST'
  });
}

// =============================================================================
// AUDIENCE INTELLIGENCE - Unified follower profiles with context
// =============================================================================

export interface AudienceProfile {
  follower_id: string;
  username?: string;
  name?: string;
  platform?: string;
  profile_pic_url?: string;
  first_contact?: string;
  last_contact?: string;
  total_messages: number;
  interests: string[];
  products_discussed: string[];
  purchase_intent_score: number;
  is_lead: boolean;
  is_customer: boolean;
  funnel_phase?: string;
  funnel_context: Record<string, unknown>;
  // Intelligence layer
  narrative?: string;
  segments: string[];
  recommended_action?: string;
  action_priority?: 'low' | 'medium' | 'high' | 'urgent';
  objections: Array<{
    type: string;
    handled: boolean;
    suggestion: string;
  }>;
  days_inactive: number;
  last_message_role?: string;
  // CRM fields
  email?: string;
  phone?: string;
  notes?: string;
  deal_value?: number;
  tags: string[];
}

export interface SegmentCount {
  segment: string;
  count: number;
}

export interface AggregatedMetrics {
  total_followers: number;
  top_interests: Array<{ interest: string; count: number }>;
  top_objections: Array<{ objection: string; count: number }>;
  funnel_distribution: Record<string, number>;
}

/**
 * Get complete audience profile for a follower
 */
export async function getAudienceProfile(
  creatorId: string,
  followerId: string
): Promise<AudienceProfile> {
  return apiFetch(`/audience/${creatorId}/profile/${followerId}`);
}

/**
 * Get segment counts for a creator
 */
export async function getAudienceSegments(
  creatorId: string
): Promise<SegmentCount[]> {
  return apiFetch(`/audience/${creatorId}/segments`);
}

/**
 * Get profiles in a specific segment
 */
export async function getAudienceSegmentUsers(
  creatorId: string,
  segmentName: string,
  limit: number = 20
): Promise<AudienceProfile[]> {
  return apiFetch(`/audience/${creatorId}/segments/${segmentName}?limit=${limit}`);
}

/**
 * Get aggregated audience metrics
 */
export async function getAudienceAggregated(
  creatorId: string
): Promise<AggregatedMetrics> {
  return apiFetch(`/audience/${creatorId}/aggregated`);
}

// =============================================================================
// INSIGHTS API (SPRINT3-T3.2)
// =============================================================================

/**
 * Hot lead action for today's mission
 */
export interface HotLeadAction {
  follower_id: string;
  name: string;
  username: string;
  profile_pic_url?: string;
  last_message: string;
  hours_ago: number;
  product?: string;
  deal_value: number;
  context: string;
  action: string;
  purchase_intent_score: number;
}

/**
 * Booking info for today
 */
export interface BookingInfo {
  id: string;
  title: string;
  time: string;
  attendee_name: string;
  attendee_email?: string;
  platform: string;
}

/**
 * Today's mission with actionable priorities
 */
export interface TodayMission {
  potential_revenue: number;
  hot_leads: HotLeadAction[];
  pending_responses: number;
  today_bookings: BookingInfo[];
  ghost_reactivation_count: number;
}

/**
 * Content insight
 */
export interface ContentInsight {
  topic: string;
  count: number;
  percentage: number;
  quotes: string[];
  suggestion: string;
}

/**
 * Trend insight
 */
export interface TrendInsight {
  term: string;
  count: number;
  growth: string;
  suggestion: string;
}

/**
 * Product insight
 */
export interface ProductInsight {
  product_name: string;
  count: number;
  potential_revenue: number;
  suggestion: string;
}

/**
 * Competition insight
 */
export interface CompetitionInsight {
  competitor: string;
  count: number;
  sentiment: string;
  suggestion: string;
}

/**
 * Weekly insights with 4 cards
 */
export interface WeeklyInsights {
  content?: ContentInsight;
  trend?: TrendInsight;
  product?: ProductInsight;
  competition?: CompetitionInsight;
}

/**
 * Weekly metrics with deltas
 */
export interface WeeklyMetrics {
  revenue: number;
  revenue_delta: number;
  sales_count: number;
  sales_delta: number;
  response_rate: number;
  response_delta: number;
  hot_leads_count: number;
  conversations_count: number;
  new_leads_count: number;
}

/**
 * Get today's mission for a creator
 */
export async function getTodayMission(creatorId: string): Promise<TodayMission> {
  return apiFetch(`/insights/${creatorId}/today`);
}

/**
 * Get weekly insights for a creator
 */
export async function getWeeklyInsights(creatorId: string): Promise<WeeklyInsights> {
  return apiFetch(`/insights/${creatorId}/weekly`);
}

/**
 * Get weekly metrics for a creator
 */
export async function getWeeklyMetrics(creatorId: string): Promise<WeeklyMetrics> {
  return apiFetch(`/insights/${creatorId}/metrics`);
}

// =============================================================================
// AUDIENCIA API (SPRINT4-T4.2) - Tu Audiencia Page
// =============================================================================

/**
 * Topic aggregation from audience conversations
 */
export interface TopicAggregation {
  topic: string;
  count: number;
  percentage: number;
  quotes: string[];
  users: string[];
}

/**
 * Objection aggregation with suggestions
 */
export interface ObjectionAggregation {
  objection: string;
  count: number;
  percentage: number;
  quotes: string[];
  suggestion: string;
  resolved_count: number;
  pending_count: number;
}

/**
 * Competition mention with sentiment
 */
export interface CompetitionMention {
  competitor: string;
  count: number;
  sentiment: "positivo" | "neutral" | "negativo";
  context: string[];
  suggestion: string;
}

/**
 * Trend item with growth
 */
export interface TrendItem {
  term: string;
  count_this_week: number;
  count_last_week: number;
  growth_percentage: number;
  quotes: string[];
}

/**
 * Content request from audience
 */
export interface ContentRequest {
  topic: string;
  count: number;
  questions: string[];
  suggestion: string;
}

/**
 * Perception item with sentiment
 */
export interface PerceptionItem {
  aspect: string;
  positive_count: number;
  negative_count: number;
  quotes_positive: string[];
  quotes_negative: string[];
}

/**
 * Response types for audiencia endpoints
 */
export interface TopicsResponse {
  total_conversations: number;
  topics: TopicAggregation[];
}

export interface ObjectionsResponse {
  total_with_objections: number;
  objections: ObjectionAggregation[];
}

export interface CompetitionResponse {
  total_mentions: number;
  competitors: CompetitionMention[];
}

export interface TrendsResponse {
  period: string;
  trends: TrendItem[];
}

export interface ContentRequestsResponse {
  total_requests: number;
  requests: ContentRequest[];
}

export interface PerceptionResponse {
  total_analyzed: number;
  perceptions: PerceptionItem[];
}

/**
 * Get topics - what the audience talks about
 */
export async function getAudienciaTopics(
  creatorId: string,
  limit: number = 10
): Promise<TopicsResponse> {
  return apiFetch(`/audiencia/${creatorId}/topics?limit=${limit}`);
}

/**
 * Get passions - topics with high engagement
 */
export async function getAudienciaPassions(
  creatorId: string,
  limit: number = 10
): Promise<TopicsResponse> {
  return apiFetch(`/audiencia/${creatorId}/passions?limit=${limit}`);
}

/**
 * Get frustrations - what frustrates the audience
 */
export async function getAudienciaFrustrations(
  creatorId: string,
  limit: number = 10
): Promise<ObjectionsResponse> {
  return apiFetch(`/audiencia/${creatorId}/frustrations?limit=${limit}`);
}

/**
 * Get competition - competitor mentions
 */
export async function getAudienciaCompetition(
  creatorId: string,
  limit: number = 10
): Promise<CompetitionResponse> {
  return apiFetch(`/audiencia/${creatorId}/competition?limit=${limit}`);
}

/**
 * Get trends - emerging topics
 */
export async function getAudienciaTrends(
  creatorId: string,
  limit: number = 10
): Promise<TrendsResponse> {
  return apiFetch(`/audiencia/${creatorId}/trends?limit=${limit}`);
}

/**
 * Get content requests - what content they want
 */
export async function getAudienciaContentRequests(
  creatorId: string,
  limit: number = 10
): Promise<ContentRequestsResponse> {
  return apiFetch(`/audiencia/${creatorId}/content-requests?limit=${limit}`);
}

/**
 * Get purchase objections - why they don't buy
 */
export async function getAudienciaPurchaseObjections(
  creatorId: string,
  limit: number = 10
): Promise<ObjectionsResponse> {
  return apiFetch(`/audiencia/${creatorId}/purchase-objections?limit=${limit}`);
}

/**
 * Get perception - what they think about you
 */
export async function getAudienciaPerception(
  creatorId: string
): Promise<PerceptionResponse> {
  return apiFetch(`/audiencia/${creatorId}/perception`);
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
  copilotStats: (creatorId: string, days?: number) => ["copilotStats", creatorId, days] as const,
  copilotComparisons: (creatorId: string) => ["copilotComparisons", creatorId] as const,
  toneProfile: (creatorId: string) => ["toneProfile", creatorId] as const,
  contentStats: (creatorId: string) => ["contentStats", creatorId] as const,
  escalations: (creatorId: string) => ["escalations", creatorId] as const,
  // Intelligence
  intelligenceDashboard: (creatorId: string) => ["intelligence", "dashboard", creatorId] as const,
  intelligencePredictions: (creatorId: string) => ["intelligence", "predictions", creatorId] as const,
  intelligenceRecommendations: (creatorId: string, category?: string) => ["intelligence", "recommendations", creatorId, category] as const,
  intelligencePatterns: (creatorId: string) => ["intelligence", "patterns", creatorId] as const,
  intelligenceWeeklyReport: (creatorId: string) => ["intelligence", "weeklyReport", creatorId] as const,
  // Audience Intelligence
  audienceProfile: (creatorId: string, followerId: string) => ["audience", "profile", creatorId, followerId] as const,
  audienceSegments: (creatorId: string) => ["audience", "segments", creatorId] as const,
  audienceSegmentUsers: (creatorId: string, segmentName: string) => ["audience", "segmentUsers", creatorId, segmentName] as const,
  audienceAggregated: (creatorId: string) => ["audience", "aggregated", creatorId] as const,
  // Insights (Hoy page)
  insightsToday: (creatorId: string) => ["insights", "today", creatorId] as const,
  insightsWeekly: (creatorId: string) => ["insights", "weekly", creatorId] as const,
  insightsMetrics: (creatorId: string) => ["insights", "metrics", creatorId] as const,
  // Audiencia (Tu Audiencia page)
  audienciaTopics: (creatorId: string) => ["audiencia", "topics", creatorId] as const,
  audienciaPassions: (creatorId: string) => ["audiencia", "passions", creatorId] as const,
  audienciaFrustrations: (creatorId: string) => ["audiencia", "frustrations", creatorId] as const,
  audienciaCompetition: (creatorId: string) => ["audiencia", "competition", creatorId] as const,
  audienciaTrends: (creatorId: string) => ["audiencia", "trends", creatorId] as const,
  audienciaContentRequests: (creatorId: string) => ["audiencia", "content-requests", creatorId] as const,
  audienciaPurchaseObjections: (creatorId: string) => ["audiencia", "purchase-objections", creatorId] as const,
  audienciaPerception: (creatorId: string) => ["audiencia", "perception", creatorId] as const,
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

// WhatsApp Embedded Signup
export interface WhatsAppEmbeddedSignupResponse {
  success: boolean;
  phone_number_id: string;
  waba_id: string;
}

export async function exchangeWhatsAppEmbeddedSignup(
  code: string,
  wabaId: string,
  phoneNumberId: string,
  creatorId: string = CREATOR_ID
): Promise<WhatsAppEmbeddedSignupResponse> {
  return apiFetch(`/oauth/whatsapp/embedded-signup`, {
    method: "POST",
    body: JSON.stringify({
      code,
      waba_id: wabaId,
      phone_number_id: phoneNumberId,
      creator_id: creatorId,
    }),
  });
}

export interface WhatsAppConfigResponse {
  app_id: string;
  config_id: string;
}

export async function getWhatsAppConfig(): Promise<WhatsAppConfigResponse> {
  return apiFetch(`/oauth/whatsapp/config`);
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
  markConversationRead,
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
  getCopilotStats,
  getCopilotComparisons,
  // Escalations
  getEscalations,
  // Intelligence
  getIntelligenceDashboard,
  getIntelligencePredictions,
  getIntelligenceRecommendations,
  getIntelligencePatterns,
  getWeeklyReport,
  generateWeeklyReport,
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
// Build trigger: 1769547497
