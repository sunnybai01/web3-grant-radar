import { NextResponse } from "next/server";
import { api, handleApiError } from "@/lib/api";

/**
 * Proxy for the manual Tavily cooldown unlock.
 *
 * The dashboard button has always posted here, but no route handler existed, so
 * the action 404'd. Backend: POST /api/v1/admin/tavily-unlock.
 */
export async function POST() {
  try {
    const { data, status } = await api.post("/api/v1/admin/tavily-unlock");
    return NextResponse.json(data, { status });
  } catch (error) {
    const { data, status } = handleApiError(error);
    return NextResponse.json(data, { status });
  }
}
