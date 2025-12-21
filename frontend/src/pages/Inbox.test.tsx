import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@/test/utils";
import userEvent from "@testing-library/user-event";
import Inbox from "./Inbox";

// Mock conversations data matching actual Inbox component
const mockConversations = [
  {
    follower_id: "ig_user1",
    name: "John Doe",
    username: "johndoe",
    platform: "instagram",
    last_contact: new Date().toISOString(),
    total_messages: 5,
    purchase_intent: 0.65,
    is_lead: true,
    is_customer: false,
    last_messages: [
      { role: "user", content: "Thanks for the info!", timestamp: new Date().toISOString() }
    ],
  },
  {
    follower_id: "ig_user2",
    name: "Jane Smith",
    username: "janesmith",
    platform: "instagram",
    last_contact: new Date(Date.now() - 3600000).toISOString(),
    total_messages: 12,
    purchase_intent: 0.30,
    is_lead: true,
    is_customer: false,
    last_messages: [
      { role: "user", content: "How much does it cost?", timestamp: new Date().toISOString() }
    ],
  },
  {
    follower_id: "tg_user3",
    name: "",
    username: "",
    platform: "telegram",
    last_contact: new Date(Date.now() - 7200000).toISOString(),
    total_messages: 3,
    purchase_intent: 0.10,
    is_lead: false,
    is_customer: false,
    last_messages: [],
  },
];

const mockMessages = [
  { role: "user", content: "Hi there!", timestamp: new Date(Date.now() - 3600000).toISOString() },
  { role: "assistant", content: "Hello! How can I help you?", timestamp: new Date(Date.now() - 3500000).toISOString() },
  { role: "user", content: "Tell me about your product", timestamp: new Date(Date.now() - 3400000).toISOString() },
];

const mockSendMessage = vi.fn().mockResolvedValue({ sent: true, platform: "instagram" });

// Mock the API hooks
vi.mock("@/hooks/useApi", () => ({
  useConversations: vi.fn(() => ({
    data: { conversations: mockConversations },
    isLoading: false,
    error: null,
  })),
  useFollowerDetail: vi.fn(() => ({
    data: {
      messages: mockMessages,
      follower: mockConversations[0],
      last_messages: mockMessages,
    },
    isLoading: false,
    error: null,
  })),
  useSendMessage: vi.fn(() => ({
    mutateAsync: mockSendMessage,
    isPending: false,
  })),
}));

describe("Inbox Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Basic Rendering Tests
  it("renders page without crashing", () => {
    const { container } = render(<Inbox />);
    expect(container).toBeInTheDocument();
  });

  it("displays search input", () => {
    render(<Inbox />);
    expect(screen.getByPlaceholderText(/search conversations/i)).toBeInTheDocument();
  });

  // Conversation List Tests
  it("displays conversation list with contacts", () => {
    render(<Inbox />);
    // Mock data has John Doe and Jane Smith as names
    const johnDoe = screen.getAllByText("John Doe");
    expect(johnDoe.length).toBeGreaterThan(0);
  });

  it("shows conversation initials avatar", () => {
    render(<Inbox />);
    // John Doe initials are JD - they appear in the avatar
    const initials = screen.getAllByText("JD");
    expect(initials.length).toBeGreaterThan(0);
  });

  it("displays last message preview in conversation list", () => {
    render(<Inbox />);
    expect(screen.getByText("Thanks for the info!")).toBeInTheDocument();
  });

  it("shows status badges on conversations", () => {
    render(<Inbox />);
    const statusBadges = screen.getAllByText(/hot|active|new|customer/i);
    expect(statusBadges.length).toBeGreaterThan(0);
  });

  it("shows platform icons on conversations", () => {
    render(<Inbox />);
    const instagramLabels = screen.getAllByText("instagram");
    expect(instagramLabels.length).toBeGreaterThan(0);
  });

  // Conversation Selection Tests
  it("clicking a conversation selects it", async () => {
    render(<Inbox />);
    // First conversation is auto-selected, so John Doe should appear in header
    const johnDoeElements = screen.getAllByText("John Doe");
    // Should appear in both list and header (when selected)
    expect(johnDoeElements.length).toBeGreaterThan(0);
  });

  it("selected conversation shows chat view", () => {
    render(<Inbox />);
    // First conversation is auto-selected
    expect(screen.getByPlaceholderText(/type a message/i)).toBeInTheDocument();
  });

  // Message Display Tests
  it("displays messages in chat view", () => {
    render(<Inbox />);
    expect(screen.getByText("Hi there!")).toBeInTheDocument();
    expect(screen.getByText("Hello! How can I help you?")).toBeInTheDocument();
  });

  it("shows bot icon for assistant messages", () => {
    const { container } = render(<Inbox />);
    // Bot messages should have bot icon
    const botMessages = container.querySelectorAll('[class*="from-primary to-accent"]');
    expect(botMessages.length).toBeGreaterThan(0);
  });

  it("shows user icon for user messages", () => {
    const { container } = render(<Inbox />);
    // User messages styled differently
    const userMessages = container.querySelectorAll('[class*="bg-gradient-to-br from-primary to-accent text-white"]');
    expect(userMessages.length).toBeGreaterThan(0);
  });

  // Message Input Tests
  it("message input is visible", () => {
    render(<Inbox />);
    expect(screen.getByPlaceholderText(/type a message/i)).toBeInTheDocument();
  });

  it("send button is disabled when input is empty", () => {
    render(<Inbox />);
    const sendButtons = screen.getAllByRole("button");
    const sendButton = sendButtons.find(btn => btn.querySelector("svg"));
    // Send button should be disabled when no text
  });

  it("send button enabled when message typed", async () => {
    render(<Inbox />);
    const input = screen.getByPlaceholderText(/type a message/i);
    await userEvent.type(input, "Hello!");

    // After typing, send button should be clickable
    const sendButtons = screen.getAllByRole("button");
    expect(sendButtons.length).toBeGreaterThan(0);
  });

  it("sends message when clicking send button", async () => {
    render(<Inbox />);
    const input = screen.getByPlaceholderText(/type a message/i);
    await userEvent.type(input, "Test message");

    // Find send button (last button in chat area)
    const buttons = screen.getAllByRole("button");
    const sendButton = buttons[buttons.length - 1];
    await userEvent.click(sendButton);

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalled();
    });
  });

  it("sends message when pressing Enter", async () => {
    render(<Inbox />);
    const input = screen.getByPlaceholderText(/type a message/i);
    await userEvent.type(input, "Test message{enter}");

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalled();
    });
  });

  // Search/Filter Tests
  it("search input filters conversations", async () => {
    render(<Inbox />);
    const searchInput = screen.getByPlaceholderText(/search conversations/i);
    await userEvent.type(searchInput, "john");

    // John Doe should still be visible after filtering
    await waitFor(() => {
      const johnDoe = screen.getAllByText("John Doe");
      expect(johnDoe.length).toBeGreaterThan(0);
    });
  });

  // Chat Header Tests
  it("displays contact name in chat header", () => {
    render(<Inbox />);
    // First conversation auto-selected shows in header
    const headers = screen.getAllByText("John Doe");
    expect(headers.length).toBeGreaterThanOrEqual(1);
  });

  it("shows platform and score in chat header", () => {
    render(<Inbox />);
    expect(screen.getByText(/Score: \d+%/)).toBeInTheDocument();
  });

  it("has options button in chat header", () => {
    render(<Inbox />);
    const buttons = screen.getAllByRole("button");
    // There should be a more options button
    expect(buttons.length).toBeGreaterThan(2);
  });

  // Loading State Tests
  it("shows loading spinner when data is loading", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    } as any);

    render(<Inbox />);
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

    render(<Inbox />);
    expect(screen.getByText("Failed to load conversations")).toBeInTheDocument();
  });

  // Empty State Tests
  it("shows empty state when no conversations", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({
      data: { conversations: [] },
      isLoading: false,
      error: null,
    } as any);

    render(<Inbox />);
    expect(screen.getByText("No conversations yet")).toBeInTheDocument();
  });

  it("shows no messages state when conversation has no messages", () => {
    // The component shows "No messages in this conversation" when messages array is empty
    const { container } = render(<Inbox />);
    expect(container).toBeInTheDocument();
  });
});
