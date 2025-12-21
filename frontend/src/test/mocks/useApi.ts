import { vi } from "vitest";

// Default mock data
export const mockDashboardData = {
  revenue: { total: 15000, trend: 12.5 },
  followers: { total: 1250, new_today: 23, trend: 8.3 },
  conversations: { total: 450, pending: 12, resolved: 438 },
  conversion_rate: { rate: 4.5, trend: 0.8 },
  bot_active: true,
};

export const mockConversationsData = [
  {
    id: "conv1",
    follower_id: "f1",
    follower_name: "John Doe",
    last_message: "Thanks for the info!",
    unread_count: 0,
    updated_at: new Date().toISOString(),
  },
  {
    id: "conv2",
    follower_id: "f2",
    follower_name: "Jane Smith",
    last_message: "How much does it cost?",
    unread_count: 2,
    updated_at: new Date().toISOString(),
  },
];

export const mockLeadsData = [
  {
    id: "1",
    name: "John Doe",
    instagram_id: "@johndoe",
    stage: "hot",
    score: 85,
    last_message: "I want to buy!",
    last_activity: new Date().toISOString(),
    created_at: new Date().toISOString(),
  },
  {
    id: "2",
    name: "Jane Smith",
    instagram_id: "@janesmith",
    stage: "warm",
    score: 65,
    last_message: "Tell me more",
    last_activity: new Date().toISOString(),
    created_at: new Date().toISOString(),
  },
];

export const mockNurturingSequences = [
  {
    id: "1",
    type: "interest_cold",
    name: "Cold Interest Follow-up",
    is_active: true,
    enrolled_count: 15,
    sent_count: 45,
    steps: [
      { delay_hours: 24, message: "Hey! Still interested?" },
      { delay_hours: 72, message: "Just checking in..." },
    ],
  },
  {
    id: "2",
    type: "abandoned",
    name: "Abandoned Cart",
    is_active: false,
    enrolled_count: 5,
    sent_count: 12,
    steps: [{ delay_hours: 1, message: "Need help completing?" }],
  },
];

export const mockRevenueData = {
  total_revenue: 15000,
  pending_revenue: 2500,
  monthly_growth: 12.5,
  total_customers: 150,
  transactions: [
    {
      id: "t1",
      amount: 99,
      status: "completed",
      customer_name: "John Doe",
      product_name: "Course A",
      created_at: new Date().toISOString(),
    },
  ],
};

export const mockPurchasesData = [
  {
    id: "p1",
    follower_id: "f1",
    follower_name: "John Doe",
    product_id: "prod1",
    product_name: "Course A",
    amount: 99,
    status: "completed",
    created_at: new Date().toISOString(),
  },
];

export const mockBookingsData = [
  {
    id: "b1",
    follower_id: "f1",
    follower_name: "John Doe",
    date: new Date().toISOString(),
    time: "10:00",
    status: "confirmed",
    link_id: "link1",
  },
];

export const mockCalendarStats = {
  total_bookings: 25,
  upcoming: 10,
  completed: 12,
  cancelled: 3,
  this_week: 5,
};

export const mockBookingLinks = [
  {
    id: "link1",
    name: "30 Min Call",
    duration: 30,
    url: "https://calendly.com/test/30min",
    active: true,
  },
];

export const mockConfigData = {
  creator_id: "test-creator",
  clone_name: "Test Bot",
  clone_tone: "friendly",
  clone_vocabulary: ["hi", "hello"],
  auto_reply_enabled: true,
  working_hours: { start: "09:00", end: "18:00" },
  webhook_url: "https://example.com/webhook",
};

export const mockProductsData = [
  {
    id: "prod1",
    name: "Course A",
    price: 99,
    description: "A great course",
    active: true,
  },
];

// Create mock hooks
export const createMockHooks = () => ({
  // Dashboard
  useDashboard: vi.fn(() => ({
    data: mockDashboardData,
    isLoading: false,
    error: null,
  })),

  // Conversations
  useConversations: vi.fn(() => ({
    data: { conversations: mockConversationsData },
    isLoading: false,
    error: null,
  })),

  useFollowerDetail: vi.fn(() => ({
    data: { messages: [], follower: {} },
    isLoading: false,
    error: null,
  })),

  // Leads
  useLeads: vi.fn(() => ({
    data: { leads: mockLeadsData },
    isLoading: false,
    error: null,
  })),

  // Metrics
  useMetrics: vi.fn(() => ({
    data: {
      total: 50,
      hot: 10,
      warm: 25,
      cold: 15,
    },
    isLoading: false,
    error: null,
  })),

  // Config
  useCreatorConfig: vi.fn(() => ({
    data: mockConfigData,
    isLoading: false,
    error: null,
  })),

  // Products
  useProducts: vi.fn(() => ({
    data: { products: mockProductsData },
    isLoading: false,
    error: null,
  })),

  // Revenue
  useRevenue: vi.fn(() => ({
    data: mockRevenueData,
    isLoading: false,
    error: null,
  })),

  usePurchases: vi.fn(() => ({
    data: { purchases: mockPurchasesData },
    isLoading: false,
    error: null,
  })),

  // Calendar
  useBookings: vi.fn(() => ({
    data: { bookings: mockBookingsData },
    isLoading: false,
    error: null,
  })),

  useCalendarStats: vi.fn(() => ({
    data: mockCalendarStats,
    isLoading: false,
    error: null,
  })),

  useBookingLinks: vi.fn(() => ({
    data: { links: mockBookingLinks },
    isLoading: false,
    error: null,
  })),

  // Nurturing
  useNurturingSequences: vi.fn(() => ({
    data: { sequences: mockNurturingSequences },
    isLoading: false,
    error: null,
  })),

  useNurturingStats: vi.fn(() => ({
    data: { total: 100, pending: 20, sent: 75, cancelled: 5 },
    isLoading: false,
    error: null,
  })),

  useNurturingFollowups: vi.fn(() => ({
    data: { followups: [] },
    isLoading: false,
    error: null,
  })),

  useNurturingEnrolled: vi.fn(() => ({
    data: { enrolled: [] },
    isLoading: false,
    error: null,
  })),

  // Mutations
  useToggleBot: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),

  useUpdateConfig: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),

  useSendMessage: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),

  useUpdateLeadStatus: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),

  useToggleNurturingSequence: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),

  useUpdateNurturingSequence: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),

  useCancelNurturing: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),

  useAddProduct: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),

  useUpdateProduct: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),

  useDeleteProduct: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),

  useAddContent: vi.fn(() => ({
    mutateAsync: vi.fn(),
    isPending: false,
  })),
});

export const mockHooks = createMockHooks();
