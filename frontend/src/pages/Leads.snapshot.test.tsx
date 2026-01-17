import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@/test/utils";
import Leads from "./Leads";

// Mock data
const mockConversations = [
  { follower_id: "ig_hot1", name: "Hot Lead", username: "hotlead", platform: "instagram", purchase_intent: 0.75, is_lead: true, is_customer: false },
  { follower_id: "ig_active1", name: "Active Lead", username: "activelead", platform: "instagram", purchase_intent: 0.35, is_lead: true, is_customer: false },
  { follower_id: "tg_new1", name: "New Lead", username: "newlead", platform: "telegram", purchase_intent: 0.10, is_lead: false, is_customer: false },
  { follower_id: "ig_customer1", name: "Customer", username: "customer", platform: "instagram", purchase_intent: 0.90, is_lead: true, is_customer: true },
];

// Mock hooks
vi.mock("@/hooks/useApi", () => ({
  useConversations: vi.fn(() => ({ data: { conversations: mockConversations }, isLoading: false, error: null })),
  useUpdateLeadStatus: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useCreateManualLead: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useUpdateLead: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useDeleteLead: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useCreateLeadTask: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useUpdateLeadTask: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useDeleteLeadTask: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useDeleteLeadActivity: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useLeadActivities: vi.fn(() => ({ data: { activities: [] }, isLoading: false })),
  useLeadTasks: vi.fn(() => ({ data: { tasks: [] }, isLoading: false })),
  useLeadStats: vi.fn(() => ({ data: { total: 0 }, isLoading: false })),
}));

describe("Leads Snapshots", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders leads pipeline - snapshot", () => {
    const { container } = render(<Leads />);
    expect(container).toMatchSnapshot();
  });

  it("renders leads loading state - snapshot", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({ data: null, isLoading: true, error: null } as any);

    const { container } = render(<Leads />);
    expect(container).toMatchSnapshot();
  });

  it("renders leads empty state - snapshot", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({ data: { conversations: [] }, isLoading: false, error: null } as any);

    const { container } = render(<Leads />);
    expect(container).toMatchSnapshot();
  });

  it("renders leads error state - snapshot", async () => {
    const { useConversations } = await import("@/hooks/useApi");
    vi.mocked(useConversations).mockReturnValue({ data: null, isLoading: false, error: new Error("Error") } as any);

    const { container } = render(<Leads />);
    expect(container).toMatchSnapshot();
  });
});
