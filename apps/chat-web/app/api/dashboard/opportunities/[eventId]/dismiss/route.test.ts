import { NextRequest } from "next/server";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

// The route talks to the shared axios client; observe that rather than fetch.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: { delete: vi.fn(), get: vi.fn(), post: vi.fn(), put: vi.fn() },
  };
});

import { PUT } from "./route";
import { api } from "@/lib/api";

const putMock = api.put as unknown as ReturnType<typeof vi.fn>;

const ctx = (eventId: string) => ({ params: Promise.resolve({ eventId }) });

beforeEach(() => {
  putMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

it("forwards the dismiss toggle with the resolved event id", async () => {
  putMock.mockResolvedValue({
    data: { status: "success", event_id: 42, is_dismissed: true },
    status: 200,
  });

  const response = await PUT(
    new NextRequest("http://localhost/api/dashboard/opportunities/42/dismiss?dismissed=true"),
    ctx("42")
  );

  expect(putMock).toHaveBeenCalledWith(
    "/api/v1/dashboard/opportunities/42/dismiss",
    null,
    { params: { dismissed: "true" } }
  );
  expect(response.status).toBe(200);
  await expect(response.json()).resolves.toEqual({
    status: "success",
    event_id: 42,
    is_dismissed: true,
  });
});

it("forwards a restore request", async () => {
  putMock.mockResolvedValue({
    data: { status: "success", event_id: 42, is_dismissed: false },
    status: 200,
  });

  await PUT(
    new NextRequest("http://localhost/api/dashboard/opportunities/42/dismiss?dismissed=false"),
    ctx("42")
  );

  expect(putMock).toHaveBeenCalledWith(
    "/api/v1/dashboard/opportunities/42/dismiss",
    null,
    { params: { dismissed: "false" } }
  );
});

it("defaults to dismissing when the query flag is absent", async () => {
  putMock.mockResolvedValue({
    data: { status: "success", event_id: 42, is_dismissed: true },
    status: 200,
  });

  await PUT(
    new NextRequest("http://localhost/api/dashboard/opportunities/42/dismiss"),
    ctx("42")
  );

  expect(putMock).toHaveBeenCalledWith(
    "/api/v1/dashboard/opportunities/42/dismiss",
    null,
    { params: { dismissed: "true" } }
  );
});

it("maps an upstream failure onto a 502 response", async () => {
  putMock.mockRejectedValue(new Error("socket hang up"));

  const response = await PUT(
    new NextRequest("http://localhost/api/dashboard/opportunities/9/dismiss"),
    ctx("9")
  );

  expect(response.status).toBe(502);
  await expect(response.json()).resolves.toEqual({
    error: "Upstream API unreachable",
  });
});
