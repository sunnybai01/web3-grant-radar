import { NextRequest, NextResponse } from "next/server";
import { api, handleApiError } from "@/lib/api";

export async function GET(req: NextRequest) {
  try {
    const query = req.nextUrl.searchParams.toString();
    const { data, status } = await api.get(
      `/api/v1/dashboard/opportunities${query ? `?${query}` : ""}`
    );
    return NextResponse.json(data, { status });
  } catch (error) {
    const { data, status } = handleApiError(error);
    return NextResponse.json(data, { status });
  }
}
