import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@/test/utils";
import userEvent from "@testing-library/user-event";
import Dashboard from "./Dashboard";

// Mock data matching actual Dashboard component expectations
const mockDashboardData = {
  metrics: {
    total_messages: 1250,
    total_followers: 450,
    leads: 35,
    customers: 12,
    high_intent_followers: 8,
    conversion_rate: 0.15,
    lead_rate: 0.08,
  },
  clone_active: true,
  config: {
    name: "TestCreator",
    clone_name: "AI Assistant",
  },
  recent_conversations: [
    { last_contact: new Date().toISOString(), total_messages: 5 },
    { last_contact: new Date().toISOString(), total_messages: 3 },
  ],
  leads: [
    { follower_id: "user1", name: "Hot Lead", purchase_intent: 0.75 },
    { follower_id: "user2", name: "Warm Lead", purchase_intent: 0.40 },
  ],
};

const mockToggleBot = vi.fn();

// Mock the API hooks
vi.mock("@/hooks/useApi", () => ({
  useDashboard: vi.fn(() => ({
    data: mockDashboardData,
    isLoading: false,
    error: null,
  })),
  useToggleBot: vi.fn(() => ({
    mutate: mockToggleBot,
    isPending: false,
  })),
}));

describe("Dashboard Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Basic Rendering Tests
  it("renders without crashing", () => {
    const { container } = render(<Dashboard />);
    expect(container).toBeInTheDocument();
  });

  it("displays greeting with creator name", () => {
    render(<Dashboard />);
    expect(screen.getByText(/TestCreator/)).toBeInTheDocument();
  });

  it("shows correct time-based greeting", () => {
    render(<Dashboard />);
    const greeting = screen.getByText(/Good (morning|afternoon|evening)/);
    expect(greeting).toBeInTheDocument();
  });

  // Bot Status Tests
  it("shows bot status badge as Online when active", () => {
    render(<Dashboard />);
    expect(screen.getByText(/Bot Online/i)).toBeInTheDocument();
  });

  it("bot toggle button is visible and clickable", async () => {
    render(<Dashboard />);
    const toggleButton = screen.getByRole("button", { name: /bot/i });
    expect(toggleButton).toBeInTheDocument();

    await userEvent.click(toggleButton);
    expect(mockToggleBot).toHaveBeenCalled();
  });

  // Metrics Cards Tests
  it("displays Total Messages card with correct value", () => {
    render(<Dashboard />);
    expect(screen.getByText("Total Messages")).toBeInTheDocument();
    expect(screen.getByText("1,250")).toBeInTheDocument();
  });

  it("displays Hot Leads card with count", () => {
    render(<Dashboard />);
    expect(screen.getByText("Hot Leads")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  it("displays Total Followers card", () => {
    render(<Dashboard />);
    expect(screen.getByText("Total Followers")).toBeInTheDocument();
    expect(screen.getByText("450")).toBeInTheDocument();
  });

  it("displays Conversion Rate card with percentage", () => {
    render(<Dashboard />);
    expect(screen.getByText("Conversion Rate")).toBeInTheDocument();
    expect(screen.getByText("15%")).toBeInTheDocument();
  });

  // Progress Bar Tests
  it("shows progress bar towards leads goal", () => {
    render(<Dashboard />);
    expect(screen.getByText(/Progress to 50 leads goal/)).toBeInTheDocument();
    expect(screen.getByText("70%")).toBeInTheDocument();
  });

  // Action Required Section Tests
  it("displays Action Required section", () => {
    render(<Dashboard />);
    expect(screen.getByText("Action Required")).toBeInTheDocument();
  });

  it("shows hot lead action items", () => {
    render(<Dashboard />);
    expect(screen.getByText(/Hot Lead is a hot lead/)).toBeInTheDocument();
  });

  // Message Activity Chart Tests
  it("displays Message Activity chart section", () => {
    render(<Dashboard />);
    expect(screen.getByText("Message Activity")).toBeInTheDocument();
  });

  // Loading State Tests
  it("shows loading spinner when data is loading", async () => {
    const { useDashboard } = await import("@/hooks/useApi");
    vi.mocked(useDashboard).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    } as any);

    render(<Dashboard />);
    const loader = document.querySelector(".animate-spin");
    expect(loader).toBeInTheDocument();
  });

  // Error State Tests
  it("shows error message when data fails to load", async () => {
    const { useDashboard } = await import("@/hooks/useApi");
    vi.mocked(useDashboard).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    } as any);

    render(<Dashboard />);
    expect(screen.getByText("Failed to load dashboard data")).toBeInTheDocument();
  });

  // Bot Paused State Tests
  it("shows Bot Paused when clone is inactive", async () => {
    const { useDashboard } = await import("@/hooks/useApi");
    vi.mocked(useDashboard).mockReturnValue({
      data: { ...mockDashboardData, clone_active: false },
      isLoading: false,
      error: null,
    } as any);

    render(<Dashboard />);
    expect(screen.getByText(/Bot Paused/i)).toBeInTheDocument();
  });

  // Empty State Tests
  it("shows no actions message when no hot leads", async () => {
    const { useDashboard } = await import("@/hooks/useApi");
    vi.mocked(useDashboard).mockReturnValue({
      data: {
        ...mockDashboardData,
        leads: [],
        metrics: { ...mockDashboardData.metrics, high_intent_followers: 0 }
      },
      isLoading: false,
      error: null,
    } as any);

    render(<Dashboard />);
    expect(screen.getByText("No actions required")).toBeInTheDocument();
  });
});
