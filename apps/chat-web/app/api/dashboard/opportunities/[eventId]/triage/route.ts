import { NextRequest, NextResponse } from "next/server";
import { api, handleApiError } from "@/lib/api";

/** Proxy for PUT /api/v1/dashboard/opportunities/{id}/triage with {status}. */
export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ eventId: string }> }
) {
  const { eventId } = await params;
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ detail: "invalid_json" }, { status: 400 });
  }

  try {
    const { data, status } = await api.put(
      `/api/v1/dashboard/opportunities/${eventId}/triage`,
      body
    );
    return NextResponse.json(data, { status });
  } catch (error) {
    const { data, status } = handleApiError(error);
    return NextResponse.json(data, { status });
  }
}
