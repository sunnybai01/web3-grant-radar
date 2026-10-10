import { afterEach, beforeEach, expect, it, vi } from "vitest";

// The dashboard proxy routes go through the shared axios client in @/lib/api, so
// assertions have to observe that client. The previous version spied on the
// global fetch, which the migration away from fetch made a no-op — the test
// passed only because it never observed a call at all.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: { delete: vi.fn(), get: vi.fn(), post: vi.fn(), put: vi.fn() },
  };
});

import { DELETE, GET } from "./route";
import { api } from "@/lib/api";

const deleteMock = api.delete as unknown as ReturnType<typeof vi.fn>;
const getMock = api.get as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  deleteMock.mockReset();
  getMock.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

it("proxies delete requests with the resolved dynamic event id", async () => {
  deleteMock.mockResolvedValue({
    data: { status: "success", event_id: 42, deleted: true },
    status: 200,
  });

  const response = await DELETE(new Request("http://localhost"), {
    params: Promise.resolve({ eventId: "42" }),
  });

  expect(deleteMock).toHaveBeenCalledWith("/api/v1/dashboard/opportunities/42");
  expect(response.status).toBe(200);
  await expect(response.json()).resolves.toEqual({
    status: "success",
    event_id: 42,
    deleted: true,
  });
});

it("maps an upstream failure onto a 502 response", async () => {
  deleteMock.mockRejectedValue(new Error("socket hang up"));

  const response = await DELETE(new Request("http://localhost"), {
    params: Promise.resolve({ eventId: "7" }),
  });

  expect(response.status).toBe(502);
  await expect(response.json()).resolves.toEqual({
    error: "Upstream API unreachable",
  });
});

it("proxies the detail lookup with the resolved event id", async () => {
  getMock.mockResolvedValue({ data: { id: 7, title: "Base Builder Grants", sources: [] }, status: 200 });

  const response = await GET(new Request("http://localhost/api/dashboard/opportunities/7"), {
    params: Promise.resolve({ eventId: "7" }),
  });

  expect(getMock).toHaveBeenCalledWith("/api/v1/dashboard/opportunities/7");
  expect(response.status).toBe(200);
  await expect(response.json()).resolves.toMatchObject({ id: 7 });
});
