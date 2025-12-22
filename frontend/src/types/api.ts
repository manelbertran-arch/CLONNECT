// API Response Types

export interface ApiResponse<T = unknown> {
  status: "ok" | "error";
  error?: string;
  data?: T;
}

// Dashboard Metrics - matches actual backend response
export interface DashboardMetrics {
  total_messages: number;
  total_followers: number;
  leads: number;
  customers: number;
  high_intent_followers: number;
  conversion_rate: number;
  lead_rate: number;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface Conversation {
  follower_id: string;
  id?: string; // UUID primary key from Lead.id - use this for updates
  username?: string;
  name?: string;
  platform?: string;
  last_contact?: string;
  total_messages: number;
  // Backend uses purchase_intent (0.0 to 1.0)
  purchase_intent?: number;
  purchase_intent_score?: number; // Alias for compatibility
  is_lead?: boolean;
  is_customer?: boolean;
  tags?: string[];
  last_messages?: Message[];
  products_discussed?: string[];
  // Contact info stored in Lead.context JSON
  email?: string;
  phone?: string;
  notes?: string;
}

export interface Lead {
  follower_id: string;
  username?: string;
  name?: string;
  platform?: string;
  // Backend uses purchase_intent (0.0 to 1.0)
  purchase_intent?: number;
  purchase_intent_score?: number; // Alias for compatibility
  first_contact?: string;
  last_contact?: string;
  total_messages: number;
  is_lead?: boolean;
  is_customer?: boolean;
  interests?: string[];
  products_discussed?: string[];
  tags?: string[];
}

export interface CreatorConfig {
  creator_id: string;
  name?: string;
  clone_name?: string;
  clone_tone?: string;
  clone_vocabulary?: string;
  clone_active?: boolean;
  is_active?: boolean;
  personality?: {
    tone?: string;
    formality?: string;
    energy?: string;
    use_humor?: boolean;
    use_emojis?: boolean;
    show_empathy?: boolean;
    favorite_words?: string[];
  };
  instagram_page_id?: string;
  instagram_user_id?: string;
  telegram_bot_token?: string;
}

export interface Product {
  id: string;
  name: string;
  description?: string;
  price: number;
  currency?: string;
  payment_link?: string;  // Backend field name
  url?: string;           // Frontend alias (deprecated)
  is_active?: boolean;    // Backend field name
  active?: boolean;       // Frontend alias (deprecated)
}

export interface DashboardOverview {
  status: string;
  metrics: DashboardMetrics;
  recent_conversations: Conversation[];
  leads: Lead[];
  config: CreatorConfig | null;
  products_count: number;
  clone_active: boolean;
}

export interface ConversationsResponse {
  status: string;
  conversations: Conversation[];
  count: number;
}

export interface LeadsResponse {
  status: string;
  leads: Lead[];
  count: number;
}

export interface MetricsResponse {
  status: string;
  metrics: DashboardMetrics;
}

export interface ToggleResponse {
  status: string;
  active: boolean;
  reason?: string;
}

export interface ProductsResponse {
  status: string;
  products: Product[];
}

// Follower detail response (includes messages)
export interface FollowerDetailResponse {
  status: string;
  follower_id: string;
  username?: string;
  name?: string;
  platform?: string;
  total_messages: number;
  purchase_intent?: number;
  is_lead?: boolean;
  is_customer?: boolean;
  products_discussed?: string[];
  // Backend returns messages in last_messages field
  last_messages?: Message[];
  conversation_history?: Message[]; // Alias for compatibility
  first_contact?: string;
  last_contact?: string;
}

// Escalation type
export interface Escalation {
  id: string;
  follower_id: string;
  reason: string;
  timestamp: string;
  status: "pending" | "resolved";
  priority: "high" | "medium" | "low";
}

// Helper to get purchase intent from either field
export function getPurchaseIntent(item: { purchase_intent?: number; purchase_intent_score?: number }): number {
  return item.purchase_intent ?? item.purchase_intent_score ?? 0;
}

// Helper to detect platform from follower_id
export function detectPlatform(followerId: string): "telegram" | "instagram" | "whatsapp" {
  if (followerId.startsWith("tg_")) return "telegram";
  if (followerId.startsWith("wa_")) return "whatsapp";
  return "instagram";
}

// Helper to get display name
export function getDisplayName(item: { name?: string; username?: string; follower_id: string }): string {
  if (item.name && item.name.trim()) return item.name;
  if (item.username && item.username.trim()) return item.username;
  return item.follower_id;
}

// Helper to get a friendly display name from follower_id
export function getFriendlyName(followerId: string): string {
  if (followerId.startsWith("tg_")) {
    const id = followerId.replace("tg_", "");
    return `Telegram User ${id.slice(-4)}`;
  }
  if (followerId.startsWith("ig_")) {
    const id = followerId.replace("ig_", "");
    return `Instagram User ${id.slice(-4)}`;
  }
  if (followerId.startsWith("wa_")) {
    const id = followerId.replace("wa_", "");
    return `WhatsApp User ${id.slice(-4)}`;
  }
  return followerId;
}

// Helper to extract name from bot responses (looks for greeting patterns)
export function extractNameFromMessages(messages: Message[]): string | null {
  for (const msg of messages) {
    if (msg.role === "assistant") {
      // Look for patterns like "Hola James!" or "Hey James," or "James!"
      const patterns = [
        /(?:hola|hey|hi|hello|buenas|ey)\s+([A-Z][a-z]+)[\s,!]/i,
        /([A-Z][a-z]+)[\s,!].*(?:genial|encantado|gusto)/i,
        /¡([A-Z][a-z]+)!/,
      ];
      for (const pattern of patterns) {
        const match = msg.content.match(pattern);
        if (match && match[1] && match[1].length > 2) {
          return match[1];
        }
      }
    }
  }
  return null;
}

// Helper to get messages from either field
export function getMessages(data: FollowerDetailResponse | null): Message[] {
  if (!data) return [];
  return data.last_messages || data.conversation_history || [];
}

// =============================================================================
// REVENUE / PAYMENTS TYPES
// =============================================================================

export interface Purchase {
  id: string;
  follower_id: string;
  product_id: string;
  product_name: string;
  amount: number;
  currency: string;
  platform: "stripe" | "hotmart";
  status: "completed" | "refunded" | "cancelled" | "pending" | "failed";
  bot_attributed: boolean;
  created_at: string;
  email?: string;
}

export interface RevenueStats {
  total_revenue: number;
  total_purchases: number;
  avg_order_value: number;
  bot_attributed_revenue: number;
  bot_attributed_purchases: number;
  revenue_by_platform: { stripe: number; hotmart: number };
  revenue_by_product: Record<string, number>;
  daily_revenue: Array<{ date: string; revenue: number; purchases: number }>;
}

export interface RevenueStatsResponse {
  status: string;
  creator_id: string;
  total_revenue: number;
  total_purchases: number;
  avg_order_value: number;
  bot_attributed_revenue: number;
  bot_attributed_purchases: number;
  revenue_by_platform: { stripe: number; hotmart: number };
  revenue_by_product: Record<string, number>;
  daily_revenue: Array<{ date: string; revenue: number; purchases: number }>;
}

export interface PurchasesResponse {
  status: string;
  creator_id: string;
  purchases: Purchase[];
  count: number;
}

// =============================================================================
// CALENDAR / BOOKINGS TYPES
// =============================================================================

export interface Booking {
  id: string;
  follower_id: string;
  follower_name?: string;
  follower_email?: string;
  meeting_type: string;
  title?: string;
  scheduled_at: string;
  duration_minutes: number;
  status: "scheduled" | "completed" | "cancelled" | "no_show";
  platform: "calendly" | "calcom" | "manual";
  meeting_url?: string;
  notes?: string;
}

export interface BookingsResponse {
  status: string;
  creator_id: string;
  bookings: Booking[];
  count: number;
}

export interface CalendarStats {
  total_bookings: number;
  completed: number;
  cancelled: number;
  no_show: number;
  show_rate: number;
  upcoming: number;
  by_type: Record<string, number>;
  by_platform: Record<string, number>;
}

export interface CalendarStatsResponse {
  status: string;
  creator_id: string;
  total_bookings: number;
  completed: number;
  cancelled: number;
  no_show: number;
  show_rate: number;
  upcoming: number;
  by_type: Record<string, number>;
  by_platform: Record<string, number>;
}

export interface BookingLink {
  id?: string;
  meeting_type: string;
  title: string;
  description?: string;
  duration_minutes: number;
  url: string;
  platform: "calendly" | "calcom" | "manual";
  active?: boolean;
}

export interface BookingLinksResponse {
  status: string;
  creator_id: string;
  links: BookingLink[];
  count: number;
}
