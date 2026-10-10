import { NextResponse } from "next/server";
import { api, handleApiError } from "@/lib/api";

export async function GET() {
  try {
    const { data, status } = await api.get("/api/v1/dashboard/source-health");
    return NextResponse.json(data, { status });
  } catch (error) {
    const { data, status } = handleApiError(error);
    return NextResponse.json(data, { status });
  }
}
