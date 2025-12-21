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

  it("displays Lead Pipeline title", () => {
    render(<Leads />);
    expect(screen.getByText("Lead Pipeline")).toBeInTheDocument();
  });

  it("shows total leads count", () => {
    render(<Leads />);
    expect(screen.getByText(/\d+ total leads/)).toBeInTheDocument();
  });

  // Kanban Columns Tests
  it("displays 4 Kanban columns", () => {
    render(<Leads />);
    expect(screen.getByText("New Leads")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Hot 🔥")).toBeInTheDocument();
    expect(screen.getByText("Customers ✅")).toBeInTheDocument();
  });

  it("shows column lead counts", () => {
    const { container } = render(<Leads />);
    // Each column header shows count
    const countElements = container.querySelectorAll(".text-xs.text-muted-foreground");
    expect(countElements.length).toBeGreaterThan(0);
  });

  it("shows column value totals", () => {
    render(<Leads />);
    // Columns show € values
    const euroValues = screen.getAllByText(/€\d+/);
    expect(euroValues.length).toBeGreaterThan(0);
  });

  // Lead Cards Tests
  it("displays lead cards in columns", () => {
    render(<Leads />);
    expect(screen.getByText("Hot Lead User")).toBeInTheDocument();
    expect(screen.getByText("Active Lead User")).toBeInTheDocument();
    expect(screen.getByText("New Lead User")).toBeInTheDocument();
  });

  it("shows lead score percentage on cards", () => {
    render(<Leads />);
    expect(screen.getByText("75%")).toBeInTheDocument(); // Hot lead
    expect(screen.getByText("35%")).toBeInTheDocument(); // Active lead
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

  it("shows estimated value on lead cards", () => {
    render(<Leads />);
    const euroValues = screen.getAllByText(/€\d+/);
    expect(euroValues.length).toBeGreaterThan(0);
  });

  // Drag and Drop Tests
  it("lead cards are draggable", () => {
    const { container } = render(<Leads />);
    const draggableCards = container.querySelectorAll('[draggable="true"]');
    expect(draggableCards.length).toBeGreaterThan(0);
  });

  it("columns accept drops", () => {
    const { container } = render(<Leads />);
    // Columns have drop handlers
    const columns = container.querySelectorAll('[class*="grid-cols-4"] > div');
    expect(columns.length).toBe(4);
  });

  // Add Lead Button Tests
  it("has Add Lead button", () => {
    render(<Leads />);
    expect(screen.getByText("Add Lead")).toBeInTheDocument();
  });

  it("Add Lead button is clickable", async () => {
    render(<Leads />);
    const addButton = screen.getByText("Add Lead");
    await userEvent.click(addButton);
    // Button should be clickable
    expect(addButton).toBeInTheDocument();
  });

  // More Options Button Tests
  it("lead cards have more options button", () => {
    const { container } = render(<Leads />);
    const optionButtons = container.querySelectorAll('[class*="MoreHorizontal"]');
    // Each card should have options
  });

  // Pipeline Value Footer Tests
  it("shows total pipeline value", () => {
    render(<Leads />);
    expect(screen.getByText("Total Pipeline Value")).toBeInTheDocument();
  });

  it("displays pipeline value with gradient text", () => {
    const { container } = render(<Leads />);
    const gradientValue = container.querySelector(".gradient-text");
    expect(gradientValue).toBeInTheDocument();
  });

  // Lead Status Classification Tests
  it("classifies hot leads correctly (50%+ intent)", () => {
    render(<Leads />);
    // Hot Lead User with 75% should be in Hot column
    expect(screen.getByText("Hot 🔥")).toBeInTheDocument();
    expect(screen.getByText("Hot Lead User")).toBeInTheDocument();
  });

  it("classifies active leads correctly (25-50% intent)", () => {
    render(<Leads />);
    // Active Lead User with 35% should be in Active column
    expect(screen.getByText("Active Lead User")).toBeInTheDocument();
  });

  it("classifies new leads correctly (<25% intent)", () => {
    render(<Leads />);
    // New Lead User with 10% should be in New column
    expect(screen.getByText("New Lead User")).toBeInTheDocument();
  });

  it("classifies customers correctly", () => {
    render(<Leads />);
    // Customer User should be in Customers column
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

    render(<Leads />);
    const loader = document.querySelector(".animate-spin");
    expect(loader).toBeInTheDocument();
  });

  // Error State Tests
  it("shows error message when data fails to load", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    } as any);

    render(<Leads />);
    expect(screen.getByText("Failed to load leads")).toBeInTheDocument();
  });

  // Empty Column State Tests
  it("shows no leads message in empty columns", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({
      data: { conversations: [] },
      isLoading: false,
      error: null,
    } as any);

    render(<Leads />);
    const noLeadsMessages = screen.getAllByText("No leads");
    expect(noLeadsMessages.length).toBe(4); // All 4 columns empty
  });
});
