import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@/test/utils";
import PersonalityTab from "./PersonalityTab";

vi.mock("@/services/api", () => ({
  API_URL: "http://localhost:8000",
}));

const mockConfig = {
  clone_name: "TestBot",
  clone_vocabulary: "- Tutea siempre al usuario\n- Usa emojis (1-2 por mensaje)\n- Sé cercano y conversacional\n- Responde como un amigo de confianza\n- Muestra empatía y comprensión",
};

const mockUpdateConfig = {
  mutateAsync: vi.fn().mockResolvedValue({}),
  isPending: false,
};

const mockToast = vi.fn();
const mockQueryClient = {
  invalidateQueries: vi.fn().mockResolvedValue(undefined),
};

describe("PersonalityTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders bot name input with config value", () => {
    render(
      <PersonalityTab
        config={mockConfig}
        updateConfig={mockUpdateConfig}
        toast={mockToast}
        queryClient={mockQueryClient}
      />
    );
    const input = screen.getByPlaceholderText("Tu nombre o marca");
    expect(input).toHaveValue("TestBot");
  });

  it("renders 4 personality presets", () => {
    render(
      <PersonalityTab
        config={mockConfig}
        updateConfig={mockUpdateConfig}
        toast={mockToast}
        queryClient={mockQueryClient}
      />
    );
    expect(screen.getByText("Amigo")).toBeInTheDocument();
    expect(screen.getByText("Mentor")).toBeInTheDocument();
    expect(screen.getByText("Vendedor")).toBeInTheDocument();
    expect(screen.getByText("Profesional")).toBeInTheDocument();
  });

  it("selects a preset and updates rules", () => {
    render(
      <PersonalityTab
        config={{ clone_name: "Bot", clone_vocabulary: "" }}
        updateConfig={mockUpdateConfig}
        toast={mockToast}
        queryClient={mockQueryClient}
      />
    );
    fireEvent.click(screen.getByText("Mentor"));
    const textarea = screen.getByPlaceholderText("Las instrucciones aparecerán aquí...");
    expect((textarea as HTMLTextAreaElement).value).toContain("Posiciónate como experto");
  });

  it("saves personality on button click", async () => {
    render(
      <PersonalityTab
        config={mockConfig}
        updateConfig={mockUpdateConfig}
        toast={mockToast}
        queryClient={mockQueryClient}
      />
    );
    fireEvent.click(screen.getByText("Guardar cambios"));
    await waitFor(() => {
      expect(mockUpdateConfig.mutateAsync).toHaveBeenCalledWith({
        clone_name: "TestBot",
        clone_vocabulary: mockConfig.clone_vocabulary,
      });
    });
  });

  it("shows error toast on save failure", async () => {
    const failingUpdate = {
      mutateAsync: vi.fn().mockRejectedValue(new Error("Network error")),
      isPending: false,
    };
    render(
      <PersonalityTab
        config={mockConfig}
        updateConfig={failingUpdate}
        toast={mockToast}
        queryClient={mockQueryClient}
      />
    );
    fireEvent.click(screen.getByText("Guardar cambios"));
    await waitFor(() => {
      expect(mockToast).toHaveBeenCalledWith(expect.objectContaining({
        title: "Error al guardar",
        variant: "destructive",
      }));
    });
  });

  it("renders AI generation section", () => {
    render(
      <PersonalityTab
        config={mockConfig}
        updateConfig={mockUpdateConfig}
        toast={mockToast}
        queryClient={mockQueryClient}
      />
    );
    expect(screen.getByText("Personalizar con IA")).toBeInTheDocument();
    expect(screen.getByText("Generar instrucciones")).toBeInTheDocument();
  });

  it("handles empty config gracefully", () => {
    render(
      <PersonalityTab
        config={undefined}
        updateConfig={mockUpdateConfig}
        toast={mockToast}
        queryClient={mockQueryClient}
      />
    );
    const input = screen.getByPlaceholderText("Tu nombre o marca");
    expect(input).toHaveValue("");
  });
});
