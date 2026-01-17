import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@/test/utils";
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

// Mock products data
const mockProducts = [
  {
    id: "prod1",
    name: "Premium Course",
    description: "Our flagship coaching program",
    price: 497,
    currency: "EUR",
    payment_link: "https://stripe.com/pay/premium",
    is_active: true,
  },
  {
    id: "prod2",
    name: "Ebook Bundle",
    description: "Collection of digital guides",
    price: 47,
    currency: "EUR",
    payment_link: "https://stripe.com/pay/ebook",
    is_active: false,
  },
];

const mockUpdateConfig = vi.fn().mockResolvedValue({ success: true });
const mockAddProduct = vi.fn().mockResolvedValue({ success: true });
const mockUpdateProduct = vi.fn().mockResolvedValue({ success: true });
const mockDeleteProduct = vi.fn().mockResolvedValue({ success: true });
const mockAddContent = vi.fn().mockResolvedValue({ success: true });
const mockAddFAQ = vi.fn().mockResolvedValue({ success: true });
const mockDeleteFAQ = vi.fn().mockResolvedValue({ success: true });
const mockUpdateFAQ = vi.fn().mockResolvedValue({ success: true });
const mockGenerateKnowledge = vi.fn().mockResolvedValue({ success: true });
const mockUpdateAbout = vi.fn().mockResolvedValue({ success: true });
const mockUpdateConnection = vi.fn().mockResolvedValue({ success: true });
const mockDisconnectPlatform = vi.fn().mockResolvedValue({ success: true });

const mockKnowledgeData = {
  faqs: [],
  about: {},
};

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
  useAddContent: vi.fn(() => ({
    mutateAsync: mockAddContent,
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
  useGenerateKnowledge: vi.fn(() => ({
    mutateAsync: mockGenerateKnowledge,
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

// Mock startOAuth
vi.mock("@/services/api", () => ({
  startOAuth: vi.fn().mockResolvedValue({ auth_url: "https://example.com/oauth" }),
  API_URL: "http://localhost:8000",
}));

describe("Settings Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Basic Rendering Tests
  it("renders page without crashing", () => {
    const { container } = render(<Settings />);
    expect(container).toBeInTheDocument();
  });

  it("displays Ajustes title", () => {
    render(<Settings />);
    expect(screen.getByText("Ajustes")).toBeInTheDocument();
  });

  it("displays subtitle in Spanish", () => {
    render(<Settings />);
    expect(screen.getByText("Configuración del bot")).toBeInTheDocument();
  });

  // Tabs Tests - 3 tabs (Personalidad, Conexiones, Conocimiento)
  it("displays all tabs", () => {
    render(<Settings />);
    expect(screen.getByText("Personalidad")).toBeInTheDocument();
    expect(screen.getByText("Conexiones")).toBeInTheDocument();
    expect(screen.getByText("Conocimiento")).toBeInTheDocument();
  });

  it("Personalidad tab is default active", () => {
    render(<Settings />);
    // Bot Name input should be visible by default (label is "Nombre del bot")
    expect(screen.getByText("Nombre del bot")).toBeInTheDocument();
  });

  it("can switch to Conexiones tab", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Conexiones"));
    expect(screen.getByText("Instagram")).toBeInTheDocument();
  });

  it("can switch to Conocimiento tab", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Conocimiento"));
    expect(screen.getByText("Preguntas Frecuentes")).toBeInTheDocument();
  });

  // Personality Tab Tests - Spanish
  it("displays Bot Name input with value", () => {
    render(<Settings />);
    const input = screen.getByPlaceholderText("Tu nombre o marca") as HTMLInputElement;
    expect(input.value).toBe("Test Bot");
  });

  it("can update Bot Name", async () => {
    render(<Settings />);
    const input = screen.getByPlaceholderText("Tu nombre o marca");
    await userEvent.clear(input);
    await userEvent.type(input, "New Bot Name");
    expect(input).toHaveValue("New Bot Name");
  });

  it("displays communication style selector", () => {
    render(<Settings />);
    expect(screen.getByText("Estilo de comunicación")).toBeInTheDocument();
  });

  it("has 4 personality presets", () => {
    render(<Settings />);
    expect(screen.getByText("Amigo")).toBeInTheDocument();
    expect(screen.getByText("Mentor")).toBeInTheDocument();
    expect(screen.getByText("Vendedor")).toBeInTheDocument();
    expect(screen.getByText("Profesional")).toBeInTheDocument();
  });

  it("displays Instrucciones del bot section", () => {
    render(<Settings />);
    expect(screen.getByText("Instrucciones del bot")).toBeInTheDocument();
  });

  it("has Guardar cambios button", () => {
    render(<Settings />);
    expect(screen.getByText("Guardar cambios")).toBeInTheDocument();
  });

  it("clicking Guardar cambios calls update mutation", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Guardar cambios"));

    await waitFor(() => {
      expect(mockUpdateConfig).toHaveBeenCalled();
    });
  });

  // Connections Tab Tests
  it("shows connection status for each platform", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Conexiones"));

    expect(screen.getByText("Instagram")).toBeInTheDocument();
    expect(screen.getByText("Telegram")).toBeInTheDocument();
    expect(screen.getByText("WhatsApp")).toBeInTheDocument();
    expect(screen.getByText("Stripe")).toBeInTheDocument();
  });

  it("shows Connect button for disconnected platforms", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Conexiones"));

    const connectButtons = screen.getAllByText("Connect");
    expect(connectButtons.length).toBeGreaterThan(0);
  });

  // Knowledge Tab Tests - Spanish
  it("shows Sobre ti section", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Conocimiento"));

    expect(screen.getByText("Sobre ti")).toBeInTheDocument();
  });

  it("shows Preguntas Frecuentes section", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Conocimiento"));

    expect(screen.getByText("Preguntas Frecuentes")).toBeInTheDocument();
  });

  it("has AI generator textarea", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Conocimiento"));

    const textarea = screen.getByPlaceholderText(/Soy Manel/);
    expect(textarea).toBeInTheDocument();
  });

  it("has Generar FAQs + Perfil button", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Conocimiento"));

    expect(screen.getByText("Generar FAQs + Perfil")).toBeInTheDocument();
  });

  it("shows FAQ templates", async () => {
    render(<Settings />);
    await userEvent.click(screen.getByText("Conocimiento"));

    expect(screen.getByText("¿Cuánto cuesta?")).toBeInTheDocument();
    expect(screen.getByText("¿Qué incluye?")).toBeInTheDocument();
  });

  // Loading State Tests
  it("shows loading spinner when config is loading", async () => {
    const { useCreatorConfig } = await import("@/hooks/useApi");
    vi.mocked(useCreatorConfig).mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    } as any);

    render(<Settings />);
    const loader = document.querySelector(".animate-spin");
    expect(loader).toBeInTheDocument();
  });

  // Error State Tests - Spanish
  it("shows error message when config fails to load", async () => {
    const { useCreatorConfig } = await import("@/hooks/useApi");
    vi.mocked(useCreatorConfig).mockReturnValue({
      data: null,
      isLoading: false,
      error: new Error("Network error"),
    } as any);

    render(<Settings />);
    expect(screen.getByText("Error al cargar ajustes")).toBeInTheDocument();
  });
});
