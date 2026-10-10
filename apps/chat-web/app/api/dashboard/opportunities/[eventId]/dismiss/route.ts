import { NextRequest, NextResponse } from "next/server";
import { api, handleApiError } from "@/lib/api";

/**
 * Proxy for the dismiss/restore toggle.
 *
 * The client has always called this path, but no route handler existed, so the
 * PUT 404'd and "Dismiss" silently failed. The backend route is
 * PUT /api/v1/dashboard/opportunities/{id}/dismiss?dismissed=<bool>.
 */
export async function PUT(
  req: NextRequest,
  { params }: { params: Promise<{ eventId: string }> }
) {
  const { eventId } = await params;
  const dismissed = req.nextUrl.searchParams.get("dismissed") ?? "true";

  try {
    const { data, status } = await api.put(
      `/api/v1/dashboard/opportunities/${eventId}/dismiss`,
      null,
      { params: { dismissed } }
    );
    return NextResponse.json(data, { status });
  } catch (error) {
    const { data, status } = handleApiError(error);
    return NextResponse.json(data, { status });
  }
}
