import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import PlatformLogo from "./PlatformLogo";

describe("PlatformLogo", () => {
  const platforms = ["instagram", "telegram", "whatsapp", "stripe", "paypal", "google"];

  platforms.forEach((platform) => {
    it(`renders ${platform} logo`, () => {
      const { container } = render(<PlatformLogo platform={platform} />);
      const svg = container.querySelector("svg");
      expect(svg).toBeTruthy();
    });
  });

  it("renders default logo for unknown platform", () => {
    const { container } = render(<PlatformLogo platform="unknown" />);
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
  });

  it("applies custom size", () => {
    const { container } = render(<PlatformLogo platform="instagram" size={32} />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("width")).toBe("32");
    expect(svg?.getAttribute("height")).toBe("32");
  });

  it("uses default size of 20", () => {
    const { container } = render(<PlatformLogo platform="instagram" />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("width")).toBe("20");
    expect(svg?.getAttribute("height")).toBe("20");
  });
});
