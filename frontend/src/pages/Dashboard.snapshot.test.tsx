import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@/test/utils";
import Dashboard from "./Dashboard";

// Mock data
const mockDashboardData = {
  metrics: {
    total_messages: 1250,
    total_followers: 450,
    leads: 35,
    customers: 12,
    high_intent_followers: 8,
    conversion_rate: 0.15,
  },
  clone_active: true,
  config: { name: "TestCreator", clone_name: "AI Assistant" },
  recent_conversations: [],
  leads: [
    { follower_id: "u1", name: "Hot Lead", purchase_intent: 0.75 },
    { follower_id: "u2", name: "Warm Lead", purchase_intent: 0.40 },
  ],
};

const mockRevenueData = { total_revenue: 15000, bot_attributed_revenue: 2500 };

// Mock hooks
vi.mock("@/hooks/useApi", () => ({
  useDashboard: vi.fn(() => ({
    data: mockDashboardData,
    isLoading: false,
    error: null,
  })),
  useToggleBot: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRevenue: vi.fn(() => ({ data: mockRevenueData, isLoading: false })),
}));

describe("Dashboard Snapshots", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders dashboard with stats - snapshot", () => {
    const { container } = render(<Dashboard />);
    expect(container).toMatchSnapshot();
  });

  it("renders dashboard loading state - snapshot", async () => {
    const { useDashboard } = await import("@/hooks/useApi");
    vi.mocked(useDashboard).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    } as any);

    const { container } = render(<Dashboard />);
    expect(container).toMatchSnapshot();
  });

  it("renders dashboard empty state - snapshot", async () => {
    const { useDashboard } = await import("@/hooks/useApi");
    vi.mocked(useDashboard).mockReturnValue({
      data: {
        ...mockDashboardData,
        metrics: { ...mockDashboardData.metrics, total_messages: 0, total_followers: 0, leads: 0 },
        leads: [],
      },
      isLoading: false,
      error: null,
    } as any);

    const { container } = render(<Dashboard />);
    expect(container).toMatchSnapshot();
  });

  it("renders dashboard error state - snapshot", async () => {
    const { useDashboard } = await import("@/hooks/useApi");
    vi.mocked(useDashboard).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    } as any);

    const { container } = render(<Dashboard />);
    expect(container).toMatchSnapshot();
  });
});
