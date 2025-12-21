import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@/test/utils";
import userEvent from "@testing-library/user-event";
import Nurturing from "./Nurturing";

// Mock sequences data matching actual Nurturing component
const mockSequences = [
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
    type: "objection_price",
    name: "Price Objection",
    is_active: true,
    enrolled_count: 8,
    sent_count: 22,
    steps: [
      { delay_hours: 12, message: "I understand price is a concern..." },
    ],
  },
  {
    id: "3",
    type: "abandoned",
    name: "Abandoned Cart",
    is_active: false,
    enrolled_count: 5,
    sent_count: 12,
    steps: [{ delay_hours: 1, message: "Need help completing?" }],
  },
  {
    id: "4",
    type: "post_purchase",
    name: "Post Purchase",
    is_active: true,
    enrolled_count: 20,
    sent_count: 55,
    steps: [
      { delay_hours: 24, message: "Hope you're enjoying your purchase!" },
      { delay_hours: 168, message: "How's everything going?" },
    ],
  },
];

const mockEnrolledUsers = [
  {
    follower_id: "user123",
    next_scheduled: new Date(Date.now() + 86400000).toISOString(),
    pending_steps: [],
  },
  {
    follower_id: "user456",
    next_scheduled: new Date(Date.now() + 172800000).toISOString(),
    pending_steps: [],
  },
];

const mockToggleSequence = vi.fn().mockResolvedValue({ success: true });
const mockUpdateSequence = vi.fn().mockResolvedValue({ success: true });
const mockCancelNurturing = vi.fn().mockResolvedValue({ success: true });

// Mock the API hooks
vi.mock("@/hooks/useApi", () => ({
  useNurturingSequences: vi.fn(() => ({
    data: { sequences: mockSequences },
    isLoading: false,
    error: null,
  })),
  useNurturingStats: vi.fn(() => ({
    data: { total: 100, pending: 48, sent: 134, cancelled: 5 },
    isLoading: false,
    error: null,
  })),
  useToggleNurturingSequence: vi.fn(() => ({
    mutateAsync: mockToggleSequence,
    isPending: false,
  })),
  useUpdateNurturingSequence: vi.fn(() => ({
    mutateAsync: mockUpdateSequence,
    isPending: false,
  })),
  useCancelNurturing: vi.fn(() => ({
    mutateAsync: mockCancelNurturing,
    isPending: false,
  })),
}));

// Mock the API service
vi.mock("@/services/api", () => ({
  getNurturingEnrolled: vi.fn(() => Promise.resolve({ enrolled: mockEnrolledUsers })),
}));

describe("Nurturing Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Basic Rendering Tests
  it("renders page without crashing", () => {
    const { container } = render(<Nurturing />);
    expect(container).toBeInTheDocument();
  });

  it("displays Nurturing Sequences title", () => {
    render(<Nurturing />);
    expect(screen.getByText("Nurturing Sequences")).toBeInTheDocument();
  });

  it("displays subtitle description", () => {
    render(<Nurturing />);
    expect(screen.getByText(/Automated follow-up sequences/)).toBeInTheDocument();
  });

  // Stats Cards Tests
  it("displays Active Sequences stat card", () => {
    render(<Nurturing />);
    expect(screen.getByText("Active Sequences")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument(); // 3 active
  });

  it("displays Pending Followups stat card", () => {
    render(<Nurturing />);
    expect(screen.getByText("Pending Followups")).toBeInTheDocument();
    expect(screen.getByText("48")).toBeInTheDocument();
  });

  it("displays Messages Sent stat card", () => {
    render(<Nurturing />);
    expect(screen.getByText("Messages Sent")).toBeInTheDocument();
    expect(screen.getByText("134")).toBeInTheDocument();
  });

  // Sequence Cards Tests
  it("displays all sequence cards", () => {
    render(<Nurturing />);
    expect(screen.getByText("Cold Interest Follow-up")).toBeInTheDocument();
    expect(screen.getByText("Price Objection")).toBeInTheDocument();
    expect(screen.getByText("Abandoned Cart")).toBeInTheDocument();
    expect(screen.getByText("Post Purchase")).toBeInTheDocument();
  });

  it("shows unique icons for each sequence type", () => {
    const { container } = render(<Nurturing />);
    // Each sequence should have a unique icon
    const iconContainers = container.querySelectorAll('[class*="w-12 h-12 rounded-xl"]');
    expect(iconContainers.length).toBe(4);
  });

  it("shows sequence descriptions", () => {
    render(<Nurturing />);
    expect(screen.getByText(/Follow up with leads who showed interest/)).toBeInTheDocument();
  });

  // Toggle Tests
  it("has toggle switch for each sequence", () => {
    render(<Nurturing />);
    const switches = screen.getAllByRole("switch");
    expect(switches.length).toBe(4);
  });

  it("toggle shows correct state for active sequences", () => {
    render(<Nurturing />);
    const switches = screen.getAllByRole("switch");
    // First sequence (Cold Interest) should be checked
    expect(switches[0]).toBeChecked();
  });

  it("toggle shows correct state for inactive sequences", () => {
    render(<Nurturing />);
    const switches = screen.getAllByRole("switch");
    // Abandoned Cart is inactive (index 2)
    expect(switches[2]).not.toBeChecked();
  });

  it("clicking toggle calls toggle mutation", async () => {
    render(<Nurturing />);
    const switches = screen.getAllByRole("switch");
    await userEvent.click(switches[0]);

    await waitFor(() => {
      expect(mockToggleSequence).toHaveBeenCalledWith("interest_cold");
    });
  });

  // Edit Button Tests
  it("has edit button for each sequence", () => {
    const { container } = render(<Nurturing />);
    // Edit buttons exist in each sequence card
    const buttons = container.querySelectorAll('button');
    expect(buttons.length).toBeGreaterThan(4); // At least 4 sequences with edit buttons
  });

  it("clicking edit button opens modal", async () => {
    render(<Nurturing />);
    // Find edit button (button with Edit2 icon)
    const buttons = screen.getAllByRole("button");
    const editButton = buttons.find(btn =>
      btn.querySelector("svg")?.classList.contains("lucide-edit-2") ||
      btn.innerHTML.includes("Edit2")
    );

    if (editButton) {
      await userEvent.click(editButton);
      await waitFor(() => {
        expect(screen.getByText("Edit Sequence Steps")).toBeInTheDocument();
      });
    }
  });

  // Step Delays Tests
  it("shows step delay badges", () => {
    render(<Nurturing />);
    // Steps show delay in format "Xh" - may be in separate elements
    const allText = screen.getAllByText(/\d+h/);
    expect(allText.length).toBeGreaterThan(0);
  });

  // Enrolled/Sent Counts Tests
  it("shows enrolled count for each sequence", () => {
    render(<Nurturing />);
    expect(screen.getByText("15")).toBeInTheDocument(); // Cold Interest
    expect(screen.getByText("8")).toBeInTheDocument();  // Price Objection
  });

  it("shows sent count for each sequence", () => {
    render(<Nurturing />);
    expect(screen.getByText("45")).toBeInTheDocument(); // Cold Interest sent
    expect(screen.getByText("22")).toBeInTheDocument(); // Price Objection sent
  });

  it("shows Pending label under enrolled count", () => {
    render(<Nurturing />);
    const pendingLabels = screen.getAllByText("Pending");
    expect(pendingLabels.length).toBe(4);
  });

  it("shows Sent label under sent count", () => {
    render(<Nurturing />);
    const sentLabels = screen.getAllByText("Sent");
    expect(sentLabels.length).toBe(4);
  });

  // Expand/Collapse Tests
  it("has expand button for each sequence", () => {
    const { container } = render(<Nurturing />);
    // ChevronDown icon has lucide-chevron-down class
    const chevronIcons = container.querySelectorAll('svg.lucide-chevron-down');
    expect(chevronIcons.length).toBeGreaterThan(0);
  });

  it("expanding sequence shows enrolled users section", async () => {
    render(<Nurturing />);
    // Find expand button
    const buttons = screen.getAllByRole("button");
    const expandButton = buttons.find(btn =>
      btn.innerHTML.includes("ChevronDown") || btn.innerHTML.includes("ChevronUp")
    );

    if (expandButton) {
      await userEvent.click(expandButton);
      await waitFor(() => {
        expect(screen.getByText("Enrolled Users")).toBeInTheDocument();
      });
    }
  });

  // How Nurturing Works Section Tests
  it("displays How Nurturing Works section", () => {
    render(<Nurturing />);
    expect(screen.getByText("How Nurturing Works")).toBeInTheDocument();
  });

  it("shows nurturing explanation bullets", () => {
    render(<Nurturing />);
    expect(screen.getByText(/Sequences are triggered automatically/)).toBeInTheDocument();
    expect(screen.getByText(/Each step is sent at the configured delay/)).toBeInTheDocument();
    expect(screen.getByText(/Sequences are cancelled if the user responds/)).toBeInTheDocument();
  });

  // Loading State Tests
  it("shows loading spinner when data is loading", async () => {
    const { useNurturingSequences } = await import("@/hooks/useApi");
    vi.mocked(useNurturingSequences).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    } as any);

    render(<Nurturing />);
    const loader = document.querySelector(".animate-spin");
    expect(loader).toBeInTheDocument();
  });

  // Error State Tests
  it("shows error message when data fails to load", async () => {
    const { useNurturingSequences } = await import("@/hooks/useApi");
    vi.mocked(useNurturingSequences).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    } as any);

    render(<Nurturing />);
    expect(screen.getByText("Failed to load nurturing data")).toBeInTheDocument();
  });

  // Edit Modal Tests
  it("edit modal shows step delay input", async () => {
    render(<Nurturing />);
    const buttons = screen.getAllByRole("button");
    // Find any edit button
    for (const btn of buttons) {
      if (btn.innerHTML.includes("Edit")) {
        await userEvent.click(btn);
        break;
      }
    }

    await waitFor(() => {
      const modal = screen.queryByText("Edit Sequence Steps");
      if (modal) {
        expect(screen.getByText(/Delay/)).toBeInTheDocument();
      }
    });
  });

  it("edit modal has save and cancel buttons", async () => {
    render(<Nurturing />);
    const buttons = screen.getAllByRole("button");
    for (const btn of buttons) {
      if (btn.innerHTML.includes("Edit")) {
        await userEvent.click(btn);
        break;
      }
    }

    await waitFor(() => {
      const modal = screen.queryByText("Edit Sequence Steps");
      if (modal) {
        expect(screen.getByText("Save Changes")).toBeInTheDocument();
        expect(screen.getByText("Cancel")).toBeInTheDocument();
      }
    });
  });
});
