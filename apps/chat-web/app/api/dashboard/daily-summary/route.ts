import { NextResponse } from "next/server";
import { api, handleApiError } from "@/lib/api";

export async function POST() {
  try {
    const { data, status } = await api.post("/api/v1/dashboard/daily-summary");
    return NextResponse.json(data, { status });
  } catch (error) {
    const { data, status } = handleApiError(error);
    return NextResponse.json(data, { status });
  }
}
