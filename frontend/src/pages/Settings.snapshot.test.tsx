import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@/test/utils";
import Settings from "./Settings";

// Mock data
const mockConfigData = {
  config: {
    clone_name: "Test Bot",
    clone_tone: "friendly",
    clone_vocabulary: "- Tutea siempre\n- Usa emojis",
    clone_active: true,
  },
};

const mockProducts = [
  { id: "prod1", name: "Premium Course", price: 497, currency: "EUR", is_active: true },
];

const mockKnowledgeData = { faqs: [], about: {} };

// Mock hooks
vi.mock("@/hooks/useApi", () => ({
  useCreatorConfig: vi.fn(() => ({ data: mockConfigData, isLoading: false, error: null })),
  useProducts: vi.fn(() => ({ data: { products: mockProducts }, isLoading: false })),
  useUpdateConfig: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useAddProduct: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useUpdateProduct: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useDeleteProduct: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useAddContent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useKnowledge: vi.fn(() => ({ data: mockKnowledgeData, isLoading: false })),
  useAddFAQ: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useDeleteFAQ: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useUpdateFAQ: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useGenerateKnowledge: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useUpdateAbout: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useConnections: vi.fn(() => ({ data: {}, isLoading: false })),
  useUpdateConnection: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useDisconnectPlatform: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));

vi.mock("@/services/api", () => ({
  startOAuth: vi.fn().mockResolvedValue({ auth_url: "https://example.com/oauth" }),
  API_URL: "http://localhost:8000",
}));

describe("Settings Snapshots", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders settings page - snapshot", () => {
    const { container } = render(<Settings />);
    expect(container).toMatchSnapshot();
  });

  it("renders settings loading state - snapshot", async () => {
    const { useCreatorConfig } = await import("@/hooks/useApi");
    vi.mocked(useCreatorConfig).mockReturnValue({ data: null, isLoading: true, error: null } as any);

    const { container } = render(<Settings />);
    expect(container).toMatchSnapshot();
  });

  it("renders settings error state - snapshot", async () => {
    const { useCreatorConfig } = await import("@/hooks/useApi");
    vi.mocked(useCreatorConfig).mockReturnValue({ data: null, isLoading: false, error: new Error("Error") } as any);

    const { container } = render(<Settings />);
    expect(container).toMatchSnapshot();
  });
});
