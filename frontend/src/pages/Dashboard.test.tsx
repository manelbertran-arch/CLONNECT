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

const mockRevenueData = {
  total_revenue: 15000,
  bot_attributed_revenue: 2500,
};

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
  useRevenue: vi.fn(() => ({
    data: mockRevenueData,
    isLoading: false,
    error: null,
  })),
  useEscalations: vi.fn(() => ({
    data: { escalations: [], count: 0 },
    isLoading: false,
    error: null,
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

  it("shows correct time-based greeting in Spanish", () => {
    render(<Dashboard />);
    // Spanish greetings based on time of day
    const greeting = screen.getByText(/Buenos días|Buenas tardes|Buenas noches/);
    expect(greeting).toBeInTheDocument();
  });

  // Bot Status Tests - Spanish
  it("shows bot status as Activo or Pausado", () => {
    render(<Dashboard />);
    // UI shows "Activo" or "Pausado" in button
    expect(screen.getByText(/Activo|Pausado/)).toBeInTheDocument();
  });

  it("bot toggle button is visible and clickable", async () => {
    render(<Dashboard />);
    // Button contains the status text
    const toggleButton = screen.getByText(/Activo|Pausado/);
    expect(toggleButton).toBeInTheDocument();

    await userEvent.click(toggleButton);
    expect(mockToggleBot).toHaveBeenCalled();
  });

  // Metrics Cards Tests - Spanish labels
  it("displays Mensajes card with correct value", () => {
    render(<Dashboard />);
    expect(screen.getByText("Mensajes")).toBeInTheDocument();
    // Number might be formatted with locale, check for the value itself
    expect(screen.getByText(/1[,.]?250/)).toBeInTheDocument();
  });

  it("displays Contactos card with count", () => {
    render(<Dashboard />);
    expect(screen.getByText("Contactos")).toBeInTheDocument();
    expect(screen.getByText("450")).toBeInTheDocument();
  });

  it("displays Leads card", () => {
    render(<Dashboard />);
    expect(screen.getByText("Leads")).toBeInTheDocument();
  });

  it("displays Clientes card", () => {
    render(<Dashboard />);
    expect(screen.getByText("Clientes")).toBeInTheDocument();
  });

  it("displays Conversión percentage", () => {
    render(<Dashboard />);
    expect(screen.getByText("Conversión")).toBeInTheDocument();
    expect(screen.getByText("15%")).toBeInTheDocument();
  });

  // Revenue Section
  it("displays Ingresos 30d section", () => {
    render(<Dashboard />);
    expect(screen.getByText(/Ingresos 30d/)).toBeInTheDocument();
  });

  // Activity Chart Tests - Spanish
  it("displays Actividad semanal chart section", () => {
    render(<Dashboard />);
    expect(screen.getByText("Actividad semanal")).toBeInTheDocument();
  });

  // Hot Leads Section - Spanish
  it("displays Leads calientes section", () => {
    render(<Dashboard />);
    expect(screen.getByText("Leads calientes")).toBeInTheDocument();
  });

  it("shows hot lead names", () => {
    render(<Dashboard />);
    expect(screen.getByText("Hot Lead")).toBeInTheDocument();
  });

  // Loading State Tests
  it("shows loading spinner when data is loading", async () => {
    const { useDashboard } = await import("@/hooks/useApi");
    vi.mocked(useDashboard).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    } as any);

    const { container } = render(<Dashboard />);
    const loader = container.querySelector(".animate-pulse") || container.querySelector(".animate-spin");
    expect(loader).toBeInTheDocument();
  });

  // Error State Tests - Spanish
  it("shows error message when data fails to load", async () => {
    const { useDashboard } = await import("@/hooks/useApi");
    vi.mocked(useDashboard).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    } as any);

    render(<Dashboard />);
    expect(screen.getByText("Error al cargar datos")).toBeInTheDocument();
  });

  // Bot Paused State Tests - Spanish
  it("shows Pausado when clone is inactive", async () => {
    const { useDashboard } = await import("@/hooks/useApi");
    vi.mocked(useDashboard).mockReturnValue({
      data: { ...mockDashboardData, clone_active: false },
      isLoading: false,
      error: null,
    } as any);

    render(<Dashboard />);
    expect(screen.getByText(/Pausado/)).toBeInTheDocument();
  });

  // Empty State Tests - Spanish
  it("shows no hot leads message when empty", async () => {
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
    expect(screen.getByText("Sin leads calientes")).toBeInTheDocument();
  });
});
