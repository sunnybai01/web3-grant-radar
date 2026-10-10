import { NextRequest } from "next/server";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, api: { delete: vi.fn(), get: vi.fn(), post: vi.fn(), put: vi.fn() } };
});

import { api } from "@/lib/api";
import { PUT } from "./route";

const putMock = api.put as unknown as ReturnType<typeof vi.fn>;
const ctx = (eventId: string) => ({ params: Promise.resolve({ eventId }) });
const request = (body: string) =>
  new NextRequest("http://localhost/api/dashboard/opportunities/42/triage", { method: "PUT", body });

beforeEach(() => {
  putMock.mockReset();
});

it("forwards the triage status to the backend", async () => {
  putMock.mockResolvedValue({ data: { id: 42, triage_status: "shortlisted" }, status: 200 });

  const response = await PUT(request(JSON.stringify({ status: "shortlisted" })), ctx("42"));

  expect(putMock).toHaveBeenCalledWith("/api/v1/dashboard/opportunities/42/triage", { status: "shortlisted" });
  expect(response.status).toBe(200);
  await expect(response.json()).resolves.toEqual({ id: 42, triage_status: "shortlisted" });
});

it("passes backend validation errors through", async () => {
  putMock.mockRejectedValue(
    Object.assign(new Error("422"), { isAxiosError: true, response: { status: 422, data: { detail: "bad status" } } })
  );

  const response = await PUT(request(JSON.stringify({ status: "archived" })), ctx("42"));

  expect(response.status).toBe(422);
});

it("rejects a body that is not JSON", async () => {
  const response = await PUT(request("not json"), ctx("42"));

  expect(response.status).toBe(400);
  expect(putMock).not.toHaveBeenCalled();
});
