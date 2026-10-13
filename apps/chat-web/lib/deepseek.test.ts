import { describe, expect, it, vi } from "vitest";

import { DEFAULT_DEEPSEEK_MODEL, isThinkingEnabled, withThinking } from "./deepseek";

const ENDPOINT = "https://api.deepseek.com/v1/chat/completions";

function recordingFetch() {
  return vi.fn(async (..._args: unknown[]) => new Response("{}"));
}

function sentBody(fetchImpl: ReturnType<typeof recordingFetch>) {
  const [, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
  return JSON.parse(init.body as string);
}

describe("deepseek helpers", () => {
  it("defaults to DeepSeek-V4.1-Flash", () => {
    expect(DEFAULT_DEEPSEEK_MODEL).toBe("deepseek-flash");
  });

  it("reads DEEPSEEK_THINKING like the Python settings, on by default", () => {
    expect(isThinkingEnabled(undefined)).toBe(true);
    expect(isThinkingEnabled("")).toBe(true);
    expect(isThinkingEnabled(" TRUE ")).toBe(true);
    expect(isThinkingEnabled("1")).toBe(true);
    expect(isThinkingEnabled("false")).toBe(false);
    expect(isThinkingEnabled("0")).toBe(false);
  });

  it("adds the thinking field to JSON request bodies and keeps the rest", async () => {
    const fetchImpl = recordingFetch();

    await withThinking(true, fetchImpl as unknown as typeof fetch)(ENDPOINT, {
      method: "POST",
      body: JSON.stringify({ model: "deepseek-flash", stream: true, messages: [] }),
    });

    const [url, init] = fetchImpl.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(ENDPOINT);
    expect(init.method).toBe("POST");
    expect(sentBody(fetchImpl)).toEqual({
      model: "deepseek-flash",
      stream: true,
      messages: [],
      thinking: { type: "enabled" },
    });
  });

  it("sends thinking disabled when switched off", async () => {
    const fetchImpl = recordingFetch();

    await withThinking(false, fetchImpl as unknown as typeof fetch)(ENDPOINT, {
      method: "POST",
      body: JSON.stringify({ model: "deepseek-flash" }),
    });

    expect(sentBody(fetchImpl).thinking).toEqual({ type: "disabled" });
  });

  it("passes requests without a string body through unchanged", async () => {
    const fetchImpl = recordingFetch();
    const init = { method: "GET" };

    await withThinking(true, fetchImpl as unknown as typeof fetch)(
      "https://api.deepseek.com/v1/models",
      init,
    );

    expect(fetchImpl).toHaveBeenCalledWith("https://api.deepseek.com/v1/models", init);
  });
});
