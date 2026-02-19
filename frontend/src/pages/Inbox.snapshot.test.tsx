import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@/test/utils";
import Inbox from "./Inbox";

// Mock data
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
    last_messages: [{ role: "user", content: "Thanks!", timestamp: new Date().toISOString() }],
  },
  {
    follower_id: "ig_user2",
    name: "Jane Smith",
    username: "janesmith",
    platform: "instagram",
    last_contact: new Date().toISOString(),
    total_messages: 12,
    purchase_intent: 0.30,
    is_lead: true,
    last_messages: [{ role: "user", content: "How much?", timestamp: new Date().toISOString() }],
  },
];

const mockMessages = [
  { role: "user", content: "Hi there!", timestamp: new Date().toISOString() },
  { role: "assistant", content: "Hello! How can I help?", timestamp: new Date().toISOString() },
];

// Mock hooks
vi.mock("@/hooks/useApi", () => ({
  useConversations: vi.fn(() => ({
    data: { conversations: mockConversations },
    isLoading: false,
    error: null,
    isSuccess: true,
  })),
  useFollowerDetail: vi.fn(() => ({
    data: { messages: mockMessages, follower: mockConversations[0], last_messages: mockMessages },
    isLoading: false,
    error: null,
  })),
  useSendMessage: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useArchiveConversation: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useMarkConversationSpam: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useDeleteConversation: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useRestoreConversation: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useArchivedConversations: vi.fn(() => ({ data: { conversations: [] }, isLoading: false })),
  useEventStream: vi.fn(() => ({ data: null, isLoading: false })),
  useTrackManualCopilot: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  usePendingForLead: vi.fn(() => ({ data: null, isLoading: false })),
  useApproveCopilotResponse: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useDiscardCopilotResponse: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));

describe("Inbox Snapshots", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders inbox with conversations - snapshot", () => {
    const { container } = render(<Inbox />);
    expect(container).toMatchSnapshot();
  });

  it("renders inbox loading state - snapshot", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    } as any);

    const { container } = render(<Inbox />);
    expect(container).toMatchSnapshot();
  });

  it("renders inbox empty state - snapshot", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({
      data: { conversations: [] },
      isLoading: false,
      error: null,
    } as any);

    const { container } = render(<Inbox />);
    expect(container).toMatchSnapshot();
  });

  it("renders inbox error state - snapshot", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    } as any);

    const { container } = render(<Inbox />);
    expect(container).toMatchSnapshot();
  });
});
