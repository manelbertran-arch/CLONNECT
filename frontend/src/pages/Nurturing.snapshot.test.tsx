import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@/test/utils";
import Nurturing from "./Nurturing";

// Mock data
const mockSequences = [
  { type: "abandoned", name: "Carrito Abandonado", is_active: true, enrolled_count: 5, sent_count: 12, steps: [] },
  { type: "interest_cold", name: "Interés Frío", is_active: true, enrolled_count: 8, sent_count: 23, steps: [] },
  { type: "re_engagement", name: "Reactivación", is_active: false, enrolled_count: 0, sent_count: 5, steps: [] },
  { type: "post_purchase", name: "Post Compra", is_active: true, enrolled_count: 2, sent_count: 8, steps: [] },
];

const mockStats = { total: 48, pending: 15, sent: 48, cancelled: 3 };

// Mock hooks
vi.mock("@/hooks/useApi", () => ({
  useNurturingSequences: vi.fn(() => ({ data: { sequences: mockSequences }, isLoading: false, error: null, refetch: vi.fn() })),
  useNurturingStats: vi.fn(() => ({ data: mockStats, isLoading: false, refetch: vi.fn() })),
  useToggleNurturingSequence: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useUpdateNurturingSequence: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useCancelNurturing: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useRunNurturing: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));

vi.mock("@/services/api", () => ({
  getNurturingEnrolled: vi.fn().mockResolvedValue({ enrolled: [] }),
}));

describe("Nurturing Snapshots", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nurturing page - snapshot", () => {
    const { container } = render(<Nurturing />);
    expect(container).toMatchSnapshot();
  });

  it("renders nurturing loading state - snapshot", async () => {
    const { useNurturingSequences } = await import("@/hooks/useApi");
    vi.mocked(useNurturingSequences).mockReturnValue({ data: null, isLoading: true, error: null, refetch: vi.fn() } as any);

    const { container } = render(<Nurturing />);
    expect(container).toMatchSnapshot();
  });

  it("renders nurturing error state - snapshot", async () => {
    const { useNurturingSequences } = await import("@/hooks/useApi");
    vi.mocked(useNurturingSequences).mockReturnValue({ data: null, isLoading: false, error: new Error("Error"), refetch: vi.fn() } as any);

    const { container } = render(<Nurturing />);
    expect(container).toMatchSnapshot();
  });
});
