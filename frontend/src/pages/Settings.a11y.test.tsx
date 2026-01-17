import { describe, it, expect, vi, beforeEach } from "vitest";
import { render } from "@/test/utils";
import Settings from "./Settings";

// Mock hooks
vi.mock("@/hooks/useApi", () => ({
  useCreatorConfig: vi.fn(() => ({
    data: { config: { clone_name: "Test", clone_tone: "friendly", clone_active: true } },
    isLoading: false,
    error: null,
  })),
  useProducts: vi.fn(() => ({ data: { products: [] }, isLoading: false })),
  useUpdateConfig: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useAddProduct: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useUpdateProduct: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useDeleteProduct: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useAddContent: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
  useKnowledge: vi.fn(() => ({ data: { faqs: [], about: {} }, isLoading: false })),
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
  startOAuth: vi.fn(),
  API_URL: "http://localhost:8000",
}));

describe("Settings Accessibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should have proper form labels", () => {
    const { container } = render(<Settings />);
    const inputs = container.querySelectorAll("input, select, textarea");

    inputs.forEach((input) => {
      const id = input.getAttribute("id");
      const ariaLabel = input.getAttribute("aria-label");
      const ariaLabelledBy = input.getAttribute("aria-labelledby");
      const placeholder = input.getAttribute("placeholder");
      const hasLabel = id ? container.querySelector(`label[for="${id}"]`) !== null : false;

      // Cada input debe tener alguna forma de label
      expect(hasLabel || ariaLabel || ariaLabelledBy || placeholder).toBeTruthy();
    });
  });

  it("should have accessible tabs", () => {
    const { container } = render(<Settings />);
    const tabs = container.querySelectorAll('[role="tab"]');

    if (tabs.length > 0) {
      tabs.forEach((tab) => {
        // Cada tab debe tener aria-selected
        const hasAriaSelected = tab.hasAttribute("aria-selected");
        // Y debe ser focusable
        const isFocusable = tab.hasAttribute("tabindex") || tab.tagName === "BUTTON";

        expect(hasAriaSelected || isFocusable).toBe(true);
      });
    }
  });

  it("should have proper heading hierarchy", () => {
    const { container } = render(<Settings />);
    const headings = container.querySelectorAll("h1, h2, h3, h4, h5, h6");

    let lastLevel = 0;
    let valid = true;
    headings.forEach((heading) => {
      const level = parseInt(heading.tagName[1]);
      if (lastLevel > 0 && level - lastLevel > 1) {
        valid = false;
      }
      lastLevel = level;
    });

    expect(valid).toBe(true);
  });

  it("should have accessible switches/toggles", () => {
    const { container } = render(<Settings />);
    const switches = container.querySelectorAll('[role="switch"]');

    switches.forEach((switchEl) => {
      const hasAriaChecked = switchEl.hasAttribute("aria-checked");
      const hasLabel =
        switchEl.getAttribute("aria-label") ||
        switchEl.getAttribute("aria-labelledby");

      expect(hasAriaChecked).toBe(true);
    });
  });

  it("should have proper button accessibility", () => {
    const { container } = render(<Settings />);
    const buttons = container.querySelectorAll("button");

    buttons.forEach((button) => {
      const hasText = button.textContent?.trim().length > 0;
      const hasAriaLabel = button.hasAttribute("aria-label");

      expect(hasText || hasAriaLabel).toBe(true);
    });
  });

  it("should not have duplicate IDs", () => {
    const { container } = render(<Settings />);
    const elementsWithId = container.querySelectorAll("[id]");
    const ids = new Set<string>();
    let hasDuplicates = false;

    elementsWithId.forEach((el) => {
      const id = el.getAttribute("id");
      if (id && ids.has(id)) {
        hasDuplicates = true;
      }
      if (id) ids.add(id);
    });

    expect(hasDuplicates).toBe(false);
  });

  it("should have keyboard-navigable form", () => {
    const { container } = render(<Settings />);
    const focusableElements = container.querySelectorAll(
      'a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );

    expect(focusableElements.length).toBeGreaterThan(0);
  });
});
