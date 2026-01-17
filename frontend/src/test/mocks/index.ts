/**
 * Centralized mocks for Clonnect frontend tests.
 * Import these mocks to ensure consistent test behavior across the application.
 */
import { vi } from "vitest";

// =============================================================================
// TYPE DEFINITIONS
// =============================================================================

export interface MockQueryResult<T> {
  data: T | undefined;
  isLoading: boolean;
  error: Error | null;
  isSuccess: boolean;
  refetch: ReturnType<typeof vi.fn>;
}

export interface MockMutationResult {
  mutateAsync: ReturnType<typeof vi.fn>;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
}

// =============================================================================
// MOCK DATA
// =============================================================================

export const mockDashboardStats = {
  revenue: {
    total: 15000,
    trend: 12.5,
    last_30_days: 5000,
    growth_rate: 15,
  },
  followers: {
    total: 1250,
    new_today: 23,
    trend: 8.3,
  },
  conversations: {
    total: 450,
    pending: 12,
    resolved: 438,
  },
  conversion_rate: {
    rate: 4.5,
    trend: 0.8,
  },
};

export const mockConversation = {
  follower_id: "follower_123",
  name: "Test User",
  username: "testuser",
  platform: "instagram" as const,
  purchase_intent: 0.5,
  status: "active" as const,
  last_messages: [
    {
      id: "msg_1",
      content: "Hola, me interesa el curso",
      sender: "follower",
      timestamp: new Date().toISOString(),
    },
  ],
};

export const mockLead = {
  follower_id: "lead_123",
  name: "John Doe",
  username: "johndoe",
  platform: "instagram" as const,
  purchase_intent: 0.75,
  status: "hot" as const,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

export const mockNurturingSequence = {
  id: "seq_1",
  type: "interest_cold",
  name: "Cold Interest Follow-up",
  is_active: true,
  enrolled_count: 15,
  sent_count: 45,
  steps: [
    { delay_hours: 24, message: "Hey! Still interested?" },
    { delay_hours: 72, message: "Just checking in..." },
  ],
};

export const mockProduct = {
  id: "prod_1",
  name: "Marketing Course",
  price: 99,
  currency: "EUR",
  description: "Complete marketing course",
  is_active: true,
};

export const mockCreatorConfig = {
  clone_name: "Test Clone",
  clone_tone: "friendly",
  clone_active: true,
  auto_reply: true,
  working_hours: { start: "09:00", end: "18:00" },
};

// =============================================================================
// MOCK FACTORY FUNCTIONS
// =============================================================================

/**
 * Create a mock query result with customizable data and state
 */
export function createMockQuery<T>(
  data: T,
  options: Partial<MockQueryResult<T>> = {}
): MockQueryResult<T> {
  return {
    data,
    isLoading: false,
    error: null,
    isSuccess: true,
    refetch: vi.fn().mockResolvedValue({ data }),
    ...options,
  };
}

/**
 * Create a mock mutation result
 */
export function createMockMutation(
  options: Partial<MockMutationResult> = {}
): MockMutationResult {
  return {
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
    isError: false,
    error: null,
    ...options,
  };
}

/**
 * Create loading state for a query
 */
export function createLoadingQuery<T>(): MockQueryResult<T> {
  return {
    data: undefined,
    isLoading: true,
    error: null,
    isSuccess: false,
    refetch: vi.fn(),
  };
}

/**
 * Create error state for a query
 */
export function createErrorQuery<T>(
  errorMessage: string = "Test error"
): MockQueryResult<T> {
  return {
    data: undefined,
    isLoading: false,
    error: new Error(errorMessage),
    isSuccess: false,
    refetch: vi.fn(),
  };
}

// =============================================================================
// API HOOK MOCKS
// =============================================================================

/**
 * Default mock implementations for useApi hooks
 */
export const mockUseApiDefaults = {
  // Dashboard
  useDashboardStats: () =>
    createMockQuery({ stats: mockDashboardStats }),

  // Conversations
  useConversations: () =>
    createMockQuery({
      conversations: [mockConversation],
    }),

  useFollowerDetail: () =>
    createMockQuery({
      follower: mockConversation,
      messages: mockConversation.last_messages,
      last_messages: mockConversation.last_messages,
    }),

  useSendMessage: () => createMockMutation(),
  useArchiveConversation: () => createMockMutation(),
  useMarkConversationSpam: () => createMockMutation(),
  useDeleteConversation: () => createMockMutation(),
  useRestoreConversation: () => createMockMutation(),
  useArchivedConversations: () =>
    createMockQuery({ conversations: [] }),

  // Leads
  useUpdateLeadStatus: () => createMockMutation(),
  useCreateManualLead: () => createMockMutation(),
  useUpdateLead: () => createMockMutation(),
  useDeleteLead: () => createMockMutation(),
  useCreateLeadTask: () => createMockMutation(),
  useUpdateLeadTask: () => createMockMutation(),
  useDeleteLeadTask: () => createMockMutation(),
  useDeleteLeadActivity: () => createMockMutation(),
  useLeadActivities: () => createMockQuery({ activities: [] }),
  useLeadTasks: () => createMockQuery({ tasks: [] }),
  useLeadStats: () => createMockQuery({ total: 0 }),

  // Nurturing
  useNurturingSequences: () =>
    createMockQuery({
      sequences: [mockNurturingSequence],
    }),
  useNurturingStats: () =>
    createMockQuery({ total: 0, pending: 0, sent: 0 }),
  useToggleNurturingSequence: () => createMockMutation(),
  useUpdateNurturingSequence: () => createMockMutation(),
  useCancelNurturing: () => createMockMutation(),
  useRunNurturing: () => createMockMutation(),

  // Settings
  useCreatorConfig: () =>
    createMockQuery({ config: mockCreatorConfig }),
  useProducts: () =>
    createMockQuery({ products: [mockProduct] }),
  useUpdateConfig: () => createMockMutation(),
  useAddProduct: () => createMockMutation(),
  useUpdateProduct: () => createMockMutation(),
  useDeleteProduct: () => createMockMutation(),
  useAddContent: () => createMockMutation(),
  useKnowledge: () =>
    createMockQuery({ faqs: [], about: {} }),
  useAddFAQ: () => createMockMutation(),
  useDeleteFAQ: () => createMockMutation(),
  useUpdateFAQ: () => createMockMutation(),
  useGenerateKnowledge: () => createMockMutation(),
  useUpdateAbout: () => createMockMutation(),
  useConnections: () => createMockQuery({}),
  useUpdateConnection: () => createMockMutation(),
  useDisconnectPlatform: () => createMockMutation(),
};

/**
 * Create a complete useApi mock with all hooks
 */
export function createUseApiMock(
  overrides: Partial<typeof mockUseApiDefaults> = {}
) {
  return {
    ...mockUseApiDefaults,
    ...overrides,
  };
}

// =============================================================================
// SERVICE MOCKS
// =============================================================================

export const mockApiService = {
  getNurturingEnrolled: vi.fn().mockResolvedValue({ enrolled: [] }),
  startOAuth: vi.fn().mockResolvedValue({}),
  API_URL: "http://localhost:8000",
};

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

/**
 * Setup all standard mocks for a test file
 */
export function setupStandardMocks() {
  vi.mock("@/hooks/useApi", () => createUseApiMock());
  vi.mock("@/services/api", () => mockApiService);
}

/**
 * Create multiple mock conversations
 */
export function createMockConversations(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    ...mockConversation,
    follower_id: `follower_${i}`,
    name: `User ${i}`,
    username: `user${i}`,
  }));
}

/**
 * Create multiple mock leads
 */
export function createMockLeads(count: number) {
  const statuses = ["new", "warm", "hot", "customer"] as const;
  return Array.from({ length: count }, (_, i) => ({
    ...mockLead,
    follower_id: `lead_${i}`,
    name: `Lead ${i}`,
    username: `lead${i}`,
    status: statuses[i % statuses.length],
    purchase_intent: Math.random(),
  }));
}

/**
 * Create mock messages for a conversation
 */
export function createMockMessages(count: number, conversationId: string) {
  return Array.from({ length: count }, (_, i) => ({
    id: `msg_${conversationId}_${i}`,
    content: `Message ${i}`,
    sender: i % 2 === 0 ? "follower" : "creator",
    timestamp: new Date(Date.now() - i * 60000).toISOString(),
  }));
}

// =============================================================================
// VITEST MOCK HELPERS
// =============================================================================

/**
 * Reset all mocks between tests
 */
export function resetAllMocks() {
  vi.clearAllMocks();
}

/**
 * Restore all mocks after tests
 */
export function restoreAllMocks() {
  vi.restoreAllMocks();
}
