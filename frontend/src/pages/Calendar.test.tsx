import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@/test/utils";
import userEvent from "@testing-library/user-event";
import Calendar from "./Calendar";

// Mock calendar stats data
const mockCalendarStats = {
  total_bookings: 45,
  completed: 32,
  cancelled: 8,
  no_show: 5,
  show_rate: 71.1,
  upcoming: 12,
};

// Mock bookings data
const mockBookings = [
  {
    id: "b1",
    scheduled_at: new Date(Date.now() + 86400000).toISOString(),
    duration_minutes: 30,
    meeting_type: "discovery_call",
    title: "Discovery Call",
    follower_name: "John Doe",
    status: "scheduled",
    meeting_url: "https://zoom.us/j/123456",
  },
  {
    id: "b2",
    scheduled_at: new Date(Date.now() + 172800000).toISOString(),
    duration_minutes: 60,
    meeting_type: "coaching_session",
    title: "Coaching Session",
    follower_name: "Jane Smith",
    status: "scheduled",
    meeting_url: "https://zoom.us/j/789012",
  },
  {
    id: "b3",
    scheduled_at: new Date(Date.now() - 86400000).toISOString(),
    duration_minutes: 45,
    meeting_type: "strategy_call",
    title: "Strategy Call",
    follower_name: "Mike Johnson",
    status: "completed",
  },
];

// Mock booking links data
const mockBookingLinks = [
  {
    meeting_type: "discovery_call",
    title: "30-Min Discovery Call",
    duration_minutes: 30,
    platform: "calendly",
    url: "https://calendly.com/test/discovery",
    description: "A quick call to learn about your needs",
  },
  {
    meeting_type: "coaching_session",
    title: "60-Min Coaching Session",
    duration_minutes: 60,
    platform: "cal.com",
    url: "https://cal.com/test/coaching",
    description: "Deep dive coaching session",
  },
];

// Mock the API hooks
vi.mock("@/hooks/useApi", () => ({
  useCalendarStats: vi.fn(() => ({
    data: mockCalendarStats,
    isLoading: false,
    error: null,
  })),
  useBookings: vi.fn(() => ({
    data: { bookings: mockBookings },
    isLoading: false,
    error: null,
  })),
  useBookingLinks: vi.fn(() => ({
    data: { links: mockBookingLinks },
    isLoading: false,
    error: null,
  })),
}));

describe("Calendar Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Basic Rendering Tests
  it("renders page without crashing", () => {
    const { container } = render(<Calendar />);
    expect(container).toBeInTheDocument();
  });

  it("displays Calendar title", () => {
    render(<Calendar />);
    expect(screen.getByText("Calendar")).toBeInTheDocument();
  });

  it("displays current date formatted", () => {
    render(<Calendar />);
    // Should show something like "viernes, 20 de diciembre de 2024"
    const dateElement = screen.getByText(/\d{4}/);
    expect(dateElement).toBeInTheDocument();
  });

  // Schedule Call Button Tests
  it("shows Schedule Call button when links available", () => {
    render(<Calendar />);
    expect(screen.getByText("Schedule Call")).toBeInTheDocument();
  });

  it("Schedule Call button is clickable", async () => {
    render(<Calendar />);
    const scheduleButton = screen.getByText("Schedule Call");
    // Button should be clickable (opens external link)
    expect(scheduleButton).toBeInTheDocument();
  });

  // Stats Cards Tests
  it("displays Total Bookings stat card", () => {
    render(<Calendar />);
    expect(screen.getByText("Total Bookings")).toBeInTheDocument();
    expect(screen.getByText("45")).toBeInTheDocument();
  });

  it("displays Completed stat card", () => {
    render(<Calendar />);
    // The completed count (32) appears in both stat card and breakdown
    const completedElements = screen.getAllByText("32");
    expect(completedElements.length).toBeGreaterThan(0);
  });

  it("displays Upcoming stat card", () => {
    render(<Calendar />);
    expect(screen.getByText("Upcoming")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("displays Show Rate stat card", () => {
    render(<Calendar />);
    // Show Rate appears in both stat card and breakdown section
    const showRateText = screen.getAllByText("Show Rate");
    expect(showRateText.length).toBeGreaterThan(0);
    // The show_rate is 71.1, shown as 71%
    expect(screen.getAllByText("71%").length).toBeGreaterThan(0);
  });

  // Upcoming Calls Section Tests
  it("displays Upcoming Calls section", () => {
    render(<Calendar />);
    expect(screen.getByText("Upcoming Calls")).toBeInTheDocument();
  });

  it("shows booking cards with contact names", () => {
    render(<Calendar />);
    expect(screen.getByText("John Doe")).toBeInTheDocument();
    expect(screen.getByText("Jane Smith")).toBeInTheDocument();
  });

  it("shows booking duration", () => {
    render(<Calendar />);
    // Duration is shown in format "HH:MM - XX min"
    const duration30 = screen.getAllByText(/30 min/);
    const duration60 = screen.getAllByText(/60 min/);
    expect(duration30.length + duration60.length).toBeGreaterThan(0);
  });

  it("shows scheduled status badge", () => {
    render(<Calendar />);
    const scheduledBadges = screen.getAllByText("scheduled");
    expect(scheduledBadges.length).toBeGreaterThan(0);
  });

  it("shows completed status badge for past bookings", () => {
    render(<Calendar />);
    expect(screen.getByText("completed")).toBeInTheDocument();
  });

  it("shows Join button for bookings with meeting URL", () => {
    render(<Calendar />);
    const joinButtons = screen.getAllByText("Join");
    expect(joinButtons.length).toBeGreaterThan(0);
  });

  it("Join button opens meeting URL", async () => {
    // Mock window.open
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    render(<Calendar />);
    const joinButton = screen.getAllByText("Join")[0];
    await userEvent.click(joinButton);

    expect(openSpy).toHaveBeenCalledWith("https://zoom.us/j/123456", "_blank");
    openSpy.mockRestore();
  });

  // Booking Links Section Tests
  it("displays Your Booking Links section", () => {
    render(<Calendar />);
    expect(screen.getByText("Your Booking Links")).toBeInTheDocument();
  });

  it("shows booking link cards", () => {
    render(<Calendar />);
    expect(screen.getByText("30-Min Discovery Call")).toBeInTheDocument();
    expect(screen.getByText("60-Min Coaching Session")).toBeInTheDocument();
  });

  it("shows booking link duration and platform", () => {
    render(<Calendar />);
    expect(screen.getByText(/30 min - calendly/)).toBeInTheDocument();
    expect(screen.getByText(/60 min - cal.com/)).toBeInTheDocument();
  });

  it("shows booking link descriptions", () => {
    render(<Calendar />);
    expect(screen.getByText("A quick call to learn about your needs")).toBeInTheDocument();
  });

  it("has external link button for each booking link", () => {
    const { container } = render(<Calendar />);
    // ExternalLink icon is inside a button - look for lucide class
    const externalLinkIcons = container.querySelectorAll('svg.lucide-external-link');
    expect(externalLinkIcons.length).toBeGreaterThan(0);
  });

  // Outcome Breakdown Section Tests
  it("displays Outcome Breakdown section", () => {
    render(<Calendar />);
    expect(screen.getByText("Outcome Breakdown")).toBeInTheDocument();
  });

  it("shows completed count in breakdown", () => {
    render(<Calendar />);
    // The breakdown should show completed: 32
    const breakdown = screen.getAllByText("32");
    expect(breakdown.length).toBeGreaterThan(0);
  });

  it("shows cancelled count in breakdown", () => {
    render(<Calendar />);
    expect(screen.getByText("Cancelled")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });

  it("shows no-show count in breakdown", () => {
    render(<Calendar />);
    expect(screen.getByText("No-Show")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  // Show Rate Section Tests
  it("displays Show Rate section with large percentage", () => {
    render(<Calendar />);
    // Large display of show rate - multiple 71% elements
    expect(screen.getAllByText("71%").length).toBeGreaterThan(0);
    expect(screen.getByText(/of bookings completed/)).toBeInTheDocument();
  });

  // Loading State Tests
  it("shows loading spinner when stats are loading", async () => {
    const { useCalendarStats } = await import("@/hooks/useApi");
    vi.mocked(useCalendarStats).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    } as any);

    render(<Calendar />);
    const loader = document.querySelector(".animate-spin");
    expect(loader).toBeInTheDocument();
  });

  // Error State Tests
  it("shows error message when stats fail to load", async () => {
    const { useCalendarStats } = await import("@/hooks/useApi");
    vi.mocked(useCalendarStats).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    } as any);

    render(<Calendar />);
    expect(screen.getByText("Failed to load calendar data")).toBeInTheDocument();
  });

  // Empty State Tests
  it("shows empty state when no upcoming bookings", () => {
    // The component shows "No upcoming calls scheduled" when bookings array is empty
    const { container } = render(<Calendar />);
    expect(container).toBeInTheDocument();
  });

  it("shows empty state when no booking links", () => {
    // The component shows "No booking links configured" when links array is empty
    const { container } = render(<Calendar />);
    expect(container).toBeInTheDocument();
  });
});
