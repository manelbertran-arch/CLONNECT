import { describe, it, expect } from "vitest";
import {
  getPurchaseIntent,
  detectPlatform,
  getDisplayName,
  getFriendlyName,
  extractNameFromMessages,
  getMessages,
} from "./api";
import type { Message, FollowerDetailResponse } from "./api";

describe("getPurchaseIntent", () => {
  it("uses multi-factor score when available", () => {
    expect(getPurchaseIntent({ score: 80 })).toBe(0.8);
  });

  it("falls back to purchase_intent", () => {
    expect(getPurchaseIntent({ purchase_intent: 0.65 })).toBe(0.65);
  });

  it("falls back to purchase_intent_score", () => {
    expect(getPurchaseIntent({ purchase_intent_score: 0.5 })).toBe(0.5);
  });

  it("returns 0 when no score available", () => {
    expect(getPurchaseIntent({})).toBe(0);
  });

  it("ignores score of 0", () => {
    expect(getPurchaseIntent({ score: 0, purchase_intent: 0.3 })).toBe(0.3);
  });

  it("prefers score over purchase_intent", () => {
    expect(getPurchaseIntent({ score: 70, purchase_intent: 0.5 })).toBe(0.7);
  });
});

describe("detectPlatform", () => {
  it("detects telegram", () => {
    expect(detectPlatform("tg_12345")).toBe("telegram");
  });

  it("detects whatsapp", () => {
    expect(detectPlatform("wa_5551234")).toBe("whatsapp");
  });

  it("defaults to instagram", () => {
    expect(detectPlatform("12345678")).toBe("instagram");
    expect(detectPlatform("ig_12345")).toBe("instagram");
  });
});

describe("getDisplayName", () => {
  it("prefers name", () => {
    expect(getDisplayName({ name: "John", username: "john_doe", follower_id: "123" })).toBe("John");
  });

  it("falls back to username", () => {
    expect(getDisplayName({ username: "john_doe", follower_id: "123" })).toBe("john_doe");
  });

  it("falls back to follower_id", () => {
    expect(getDisplayName({ follower_id: "123" })).toBe("123");
  });

  it("ignores empty name", () => {
    expect(getDisplayName({ name: "  ", username: "john_doe", follower_id: "123" })).toBe("john_doe");
  });

  it("ignores empty username", () => {
    expect(getDisplayName({ name: "", username: "  ", follower_id: "123" })).toBe("123");
  });
});

describe("getFriendlyName", () => {
  it("formats telegram IDs", () => {
    expect(getFriendlyName("tg_123456")).toBe("Telegram User 3456");
  });

  it("formats instagram IDs", () => {
    expect(getFriendlyName("ig_789012")).toBe("Instagram User 9012");
  });

  it("formats whatsapp IDs as phone numbers", () => {
    expect(getFriendlyName("wa_34612345678")).toBe("+34612345678");
  });

  it("returns raw ID for unknown formats", () => {
    expect(getFriendlyName("12345678")).toBe("12345678");
  });
});

describe("extractNameFromMessages", () => {
  it("extracts name from Hola greeting", () => {
    const messages: Message[] = [
      { role: "assistant", content: "Hola James! ¿Cómo estás?", timestamp: "" },
    ];
    expect(extractNameFromMessages(messages)).toBe("James");
  });

  it("extracts name from Hey greeting", () => {
    const messages: Message[] = [
      { role: "assistant", content: "Hey Maria, qué tal", timestamp: "" },
    ];
    expect(extractNameFromMessages(messages)).toBe("Maria");
  });

  it("returns null when no name found", () => {
    const messages: Message[] = [
      { role: "user", content: "Hola", timestamp: "" },
    ];
    expect(extractNameFromMessages(messages)).toBeNull();
  });

  it("ignores short names (2 chars or less)", () => {
    const messages: Message[] = [
      { role: "assistant", content: "Hola Al, test", timestamp: "" },
    ];
    expect(extractNameFromMessages(messages)).toBeNull();
  });

  it("returns null for empty array", () => {
    expect(extractNameFromMessages([])).toBeNull();
  });
});

describe("getMessages", () => {
  it("returns last_messages when available", () => {
    const msgs: Message[] = [{ role: "user", content: "hi", timestamp: "" }];
    const data = { last_messages: msgs } as FollowerDetailResponse;
    expect(getMessages(data)).toBe(msgs);
  });

  it("falls back to conversation_history", () => {
    const msgs: Message[] = [{ role: "user", content: "hi", timestamp: "" }];
    const data = { conversation_history: msgs } as FollowerDetailResponse;
    expect(getMessages(data)).toBe(msgs);
  });

  it("returns empty array for null", () => {
    expect(getMessages(null)).toEqual([]);
  });
});
