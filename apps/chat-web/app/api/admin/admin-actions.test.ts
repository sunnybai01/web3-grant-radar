import { NextRequest } from "next/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: { delete: vi.fn(), get: vi.fn(), post: vi.fn(), put: vi.fn() },
  };
});

import { POST as TAVILY_UNLOCK } from "./tavily-unlock/route";
import { POST as RESET_DEDUP } from "./reset-dedup/route";
import { api } from "@/lib/api";

const postMock = api.post as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  postMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

it("proxies the tavily unlock action", async () => {
  postMock.mockResolvedValue({
    data: { status: "ok", unlocked_count: 3, message: "Unlocked 3 tavily source(s).", error: "" },
    status: 200,
  });

  const response = await TAVILY_UNLOCK();

  expect(postMock).toHaveBeenCalledWith("/api/v1/admin/tavily-unlock");
  expect(response.status).toBe(200);
  await expect(response.json()).resolves.toEqual({
    status: "ok",
    unlocked_count: 3,
    message: "Unlocked 3 tavily source(s).",
    error: "",
  });
});

it("proxies a partial dedup reset by default", async () => {
  postMock.mockResolvedValue({
    data: { status: "ok", vectors_cleared: true, signals_cleared: 12, message: "", error: "" },
    status: 200,
  });

  await RESET_DEDUP(new NextRequest("http://localhost/api/admin/reset-dedup"));

  expect(postMock).toHaveBeenCalledWith("/api/v1/admin/reset-dedup", null, {
    params: { full: "false" },
  });
});

it("forwards an explicit full rescan request", async () => {
  postMock.mockResolvedValue({
    data: { status: "ok", vectors_cleared: true, signals_cleared: 0, message: "", error: "" },
    status: 200,
  });

  await RESET_DEDUP(
    new NextRequest("http://localhost/api/admin/reset-dedup?full=true")
  );

  expect(postMock).toHaveBeenCalledWith("/api/v1/admin/reset-dedup", null, {
    params: { full: "true" },
  });
});

it("maps an upstream failure onto a 502 response", async () => {
  postMock.mockRejectedValue(new Error("socket hang up"));

  const response = await TAVILY_UNLOCK();

  expect(response.status).toBe(502);
  await expect(response.json()).resolves.toEqual({
    error: "Upstream API unreachable",
  });
});
