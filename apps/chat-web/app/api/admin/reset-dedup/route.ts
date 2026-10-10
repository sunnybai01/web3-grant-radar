import { NextRequest, NextResponse } from "next/server";
import { api, handleApiError } from "@/lib/api";

/**
 * Proxy for the dedup reset action.
 *
 * The dashboard button has always posted here, but no route handler existed, so
 * the action 404'd. Backend: POST /api/v1/admin/reset-dedup?full=<bool>.
 */
export async function POST(req: NextRequest) {
  const full = req.nextUrl.searchParams.get("full") ?? "false";

  try {
    const { data, status } = await api.post("/api/v1/admin/reset-dedup", null, {
      params: { full },
    });
    return NextResponse.json(data, { status });
  } catch (error) {
    const { data, status } = handleApiError(error);
    return NextResponse.json(data, { status });
  }
}
