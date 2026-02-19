import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@/test/utils";
import userEvent from "@testing-library/user-event";
import Settings from "./Settings";

// Mock config data
const mockConfigData = {
  config: {
    clone_name: "Test Bot",
    clone_tone: "friendly",
    clone_vocabulary: "- Tutea siempre al usuario\n- Usa emojis",
    clone_active: true,
  },
};

const mockProducts = [
  {
    id: "prod1",
    name: "Premium Course",
    description: "Our flagship program",
    price: 497,
    currency: "EUR",
    payment_link: "https://stripe.com/pay/premium",
    is_active: true,
  },
];

const mockUpdateConfig = vi.fn().mockResolvedValue({ success: true });
const mockAddProduct = vi.fn().mockResolvedValue({ success: true });
const mockUpdateProduct = vi.fn().mockResolvedValue({ success: true });
const mockDeleteProduct = vi.fn().mockResolvedValue({ success: true });
const mockAddFAQ = vi.fn().mockResolvedValue({ success: true });
const mockDeleteFAQ = vi.fn().mockResolvedValue({ success: true });
const mockUpdateFAQ = vi.fn().mockResolvedValue({ success: true });
const mockUpdateAbout = vi.fn().mockResolvedValue({ success: true });
const mockUpdateConnection = vi.fn().mockResolvedValue({ success: true });
const mockDisconnectPlatform = vi.fn().mockResolvedValue({ success: true });

const mockKnowledgeData = { faqs: [], about: {} };
const mockConnectionsData = {};

// Mock the API hooks
vi.mock("@/hooks/useApi", () => ({
  useCreatorConfig: vi.fn(() => ({
    data: mockConfigData,
    isLoading: false,
    error: null,
  })),
  useProducts: vi.fn(() => ({
    data: { products: mockProducts },
    isLoading: false,
    error: null,
  })),
  useUpdateConfig: vi.fn(() => ({
    mutateAsync: mockUpdateConfig,
    isPending: false,
  })),
  useAddProduct: vi.fn(() => ({
    mutateAsync: mockAddProduct,
    isPending: false,
  })),
  useUpdateProduct: vi.fn(() => ({
    mutateAsync: mockUpdateProduct,
    isPending: false,
  })),
  useDeleteProduct: vi.fn(() => ({
    mutateAsync: mockDeleteProduct,
    isPending: false,
  })),
  useKnowledge: vi.fn(() => ({
    data: mockKnowledgeData,
    isLoading: false,
    error: null,
  })),
  useAddFAQ: vi.fn(() => ({
    mutateAsync: mockAddFAQ,
    isPending: false,
  })),
  useDeleteFAQ: vi.fn(() => ({
    mutateAsync: mockDeleteFAQ,
    isPending: false,
  })),
  useUpdateFAQ: vi.fn(() => ({
    mutateAsync: mockUpdateFAQ,
    isPending: false,
  })),
  useUpdateAbout: vi.fn(() => ({
    mutateAsync: mockUpdateAbout,
    isPending: false,
  })),
  useConnections: vi.fn(() => ({
    data: mockConnectionsData,
    isLoading: false,
    error: null,
  })),
  useUpdateConnection: vi.fn(() => ({
    mutateAsync: mockUpdateConnection,
    isPending: false,
  })),
  useDisconnectPlatform: vi.fn(() => ({
    mutateAsync: mockDisconnectPlatform,
    isPending: false,
  })),
}));

vi.mock("@/services/api", () => ({
  startOAuth: vi.fn().mockResolvedValue({ auth_url: "https://example.com/oauth" }),
  exchangeWhatsAppEmbeddedSignup: vi.fn().mockResolvedValue({}),
  getWhatsAppConfig: vi.fn().mockResolvedValue({}),
  API_URL: "http://localhost:8000",
}));

describe("Settings Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders page without crashing", () => {
    const { container } = render(<Settings />);
    expect(container).toBeInTheDocument();
  });

  it("displays Ajustes title", () => {
    render(<Settings />);
    expect(screen.getByText("Ajustes")).toBeInTheDocument();
  });

  it("displays subtitle", () => {
    render(<Settings />);
    expect(screen.getByText("Configuración del bot")).toBeInTheDocument();
  });

  it("displays all 3 tabs", () => {
    render(<Settings />);
    expect(screen.getByText("Personalidad")).toBeInTheDocument();
    expect(screen.getByText("Conexiones")).toBeInTheDocument();
    expect(screen.getByText("Conocimiento")).toBeInTheDocument();
  });

  it("Personalidad tab is active by default", () => {
    render(<Settings />);
    expect(screen.getByText("Nombre del bot")).toBeInTheDocument();
  });

  it("shows 4 personality presets", () => {
    render(<Settings />);
    expect(screen.getByText("Amigo")).toBeInTheDocument();
    expect(screen.getByText("Mentor")).toBeInTheDocument();
    expect(screen.getByText("Vendedor")).toBeInTheDocument();
    expect(screen.getByText("Profesional")).toBeInTheDocument();
  });

  it("displays bot name from config", () => {
    render(<Settings />);
    const input = screen.getByPlaceholderText("Tu nombre o marca") as HTMLInputElement;
    expect(input.value).toBe("Test Bot");
  });

  it("has Guardar cambios button", () => {
    render(<Settings />);
    expect(screen.getByText("Guardar cambios")).toBeInTheDocument();
  });

  it("can switch to Conexiones tab", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Conexiones"));
    expect(screen.getByText("Instagram")).toBeInTheDocument();
    expect(screen.getByText("Telegram")).toBeInTheDocument();
  });

  it("can switch to Conocimiento tab", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Conocimiento"));
    expect(screen.getByText("Preguntas Frecuentes")).toBeInTheDocument();
    expect(screen.getByText("Sobre ti")).toBeInTheDocument();
  });

  it("Guardar cambios calls updateConfig", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Guardar cambios"));
    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalled();
    });
  });

  it("shows loading skeleton when config is loading", async () => {
    const { useCreatorConfig } = await import("@/hooks/useApi");
    vi.mocked(useCreatorConfig).mockReturnValueOnce({
      data: null,
      isLoading: true,
      error: null,
    } as any);

    const { container } = render(<Settings />);
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("shows error state with message", async () => {
    const { useCreatorConfig } = await import("@/hooks/useApi");
    vi.mocked(useCreatorConfig).mockReturnValueOnce({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    } as any);

    render(<Settings />);
    expect(screen.getByText("Error al cargar ajustes")).toBeInTheDocument();
  });
});
