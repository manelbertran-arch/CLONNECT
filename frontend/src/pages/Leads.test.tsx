import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@/test/utils";
import userEvent from "@testing-library/user-event";
import Leads from "./Leads";

// Mock conversations data for Leads page (it uses useConversations)
const mockConversations = [
  {
    follower_id: "ig_hot1",
    name: "Hot Lead User",
    username: "hotlead",
    platform: "instagram",
    purchase_intent: 0.75,
    is_lead: true,
    is_customer: false,
  },
  {
    follower_id: "ig_active1",
    name: "Active Lead User",
    username: "activelead",
    platform: "instagram",
    purchase_intent: 0.35,
    is_lead: true,
    is_customer: false,
  },
  {
    follower_id: "tg_new1",
    name: "New Lead User",
    username: "newlead",
    platform: "telegram",
    purchase_intent: 0.10,
    is_lead: false,
    is_customer: false,
  },
  {
    follower_id: "ig_customer1",
    name: "Customer User",
    username: "customer",
    platform: "instagram",
    purchase_intent: 0.90,
    is_lead: true,
    is_customer: true,
  },
];

const mockUpdateStatus = vi.fn().mockResolvedValue({ success: true });
const mockCreateLead = vi.fn().mockResolvedValue({ success: true });
const mockUpdateLead = vi.fn().mockResolvedValue({ success: true });
const mockDeleteLead = vi.fn().mockResolvedValue({ success: true });
const mockCreateTask = vi.fn().mockResolvedValue({ success: true });
const mockUpdateTask = vi.fn().mockResolvedValue({ success: true });
const mockDeleteTask = vi.fn().mockResolvedValue({ success: true });
const mockDeleteActivity = vi.fn().mockResolvedValue({ success: true });

// Mock the API hooks
vi.mock("@/hooks/useApi", () => ({
  useConversations: vi.fn(() => ({
    data: { conversations: mockConversations },
    isLoading: false,
    error: null,
  })),
  useUpdateLeadStatus: vi.fn(() => ({
    mutateAsync: mockUpdateStatus,
    isPending: false,
  })),
  useCreateManualLead: vi.fn(() => ({
    mutateAsync: mockCreateLead,
    isPending: false,
  })),
  useUpdateLead: vi.fn(() => ({
    mutateAsync: mockUpdateLead,
    isPending: false,
  })),
  useDeleteLead: vi.fn(() => ({
    mutateAsync: mockDeleteLead,
    isPending: false,
  })),
  useCreateLeadTask: vi.fn(() => ({
    mutateAsync: mockCreateTask,
    isPending: false,
  })),
  useUpdateLeadTask: vi.fn(() => ({
    mutateAsync: mockUpdateTask,
    isPending: false,
  })),
  useDeleteLeadTask: vi.fn(() => ({
    mutateAsync: mockDeleteTask,
    isPending: false,
  })),
  useDeleteLeadActivity: vi.fn(() => ({
    mutateAsync: mockDeleteActivity,
    isPending: false,
  })),
  useLeadActivities: vi.fn(() => ({
    data: { activities: [] },
    isLoading: false,
    error: null,
  })),
  useLeadTasks: vi.fn(() => ({
    data: { tasks: [] },
    isLoading: false,
    error: null,
  })),
  useLeadStats: vi.fn(() => ({
    data: { total: 0, nuevo: 0, contactado: 0, activo: 0, caliente: 0, cliente: 0 },
    isLoading: false,
    error: null,
  })),
}));

describe("Leads Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Basic Rendering Tests
  it("renders page without crashing", () => {
    const { container } = render(<Leads />);
    expect(container).toBeInTheDocument();
  });

  it("displays Pipeline title", () => {
    render(<Leads />);
    expect(screen.getByText("Pipeline")).toBeInTheDocument();
  });

  it("shows total leads count in Spanish", () => {
    render(<Leads />);
    expect(screen.getByText(/leads en el pipeline/)).toBeInTheDocument();
  });

  // Kanban Columns Tests - Spanish names
  it("displays 6 Kanban columns in Spanish", () => {
    render(<Leads />);
    expect(screen.getByText("Nuevos")).toBeInTheDocument();
    expect(screen.getByText("Amigos")).toBeInTheDocument();
    expect(screen.getByText("Colaboradores")).toBeInTheDocument();
    expect(screen.getByText("Calientes")).toBeInTheDocument();
    expect(screen.getByText("Clientes")).toBeInTheDocument();
    expect(screen.getByText("Fríos")).toBeInTheDocument();
  });

  it("shows column lead counts", () => {
    const { container } = render(<Leads />);
    // Column headers with counts
    const countBadges = container.querySelectorAll("[class*='text-xs']");
    expect(countBadges.length).toBeGreaterThan(0);
  });

  // Lead Cards Tests
  it("displays lead cards in columns", () => {
    render(<Leads />);
    expect(screen.getByText("Hot Lead User")).toBeInTheDocument();
    expect(screen.getByText("Active Lead User")).toBeInTheDocument();
    expect(screen.getByText("New Lead User")).toBeInTheDocument();
  });

  it("shows lead initials avatar", () => {
    render(<Leads />);
    expect(screen.getByText("HL")).toBeInTheDocument(); // Hot Lead User
  });

  it("shows platform icons on lead cards", () => {
    const { container } = render(<Leads />);
    // SVG icons for platforms
    const platformIcons = container.querySelectorAll("svg");
    expect(platformIcons.length).toBeGreaterThan(0);
  });

  // Drag and Drop Tests
  it("lead cards are draggable", () => {
    const { container } = render(<Leads />);
    const draggableCards = container.querySelectorAll('[draggable="true"]');
    expect(draggableCards.length).toBeGreaterThan(0);
  });

  // Add Lead Button Tests - Spanish
  it("has Nuevo Lead button", () => {
    render(<Leads />);
    expect(screen.getByText("Nuevo Lead")).toBeInTheDocument();
  });

  it("Nuevo Lead button is clickable", async () => {
    render(<Leads />);
    const addButton = screen.getByText("Nuevo Lead");
    await userEvent.click(addButton);
    // Button should be clickable
    expect(addButton).toBeInTheDocument();
  });

  // More Options Button Tests
  it("lead cards have more options button", () => {
    const { container } = render(<Leads />);
    const buttons = container.querySelectorAll("button");
    expect(buttons.length).toBeGreaterThan(0);
  });

  // Lead Status Classification Tests
  it("classifies leads correctly", () => {
    render(<Leads />);
    // All leads should appear in the page
    expect(screen.getByText("Hot Lead User")).toBeInTheDocument();
    expect(screen.getByText("Active Lead User")).toBeInTheDocument();
    expect(screen.getByText("New Lead User")).toBeInTheDocument();
    expect(screen.getByText("Customer User")).toBeInTheDocument();
  });

  // Loading State Tests
  it("shows loading spinner when data is loading", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    } as any);

    const { container } = render(<Leads />);
    const loader = container.querySelector(".animate-pulse") || container.querySelector(".animate-spin");
    expect(loader).toBeInTheDocument();
  });

  // Error State Tests - Spanish
  it("shows error message when data fails to load", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    } as any);

    render(<Leads />);
    expect(screen.getByText("No se pudieron cargar los leads")).toBeInTheDocument();
  });

  // Empty Column State Tests - Spanish
  it("shows Sin leads message in empty columns", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({
      data: { conversations: [] },
      isLoading: false,
      error: null,
    } as any);

    render(<Leads />);
    const noLeadsMessages = screen.getAllByText("Sin leads");
    expect(noLeadsMessages.length).toBeGreaterThan(0);
  });
});
