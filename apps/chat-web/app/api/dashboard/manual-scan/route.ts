import { NextResponse } from "next/server";
import { api, handleApiError } from "@/lib/api";

export async function GET() {
  try {
    const { data, status } = await api.get("/api/v1/dashboard/manual-scan");
    return NextResponse.json(data, { status });
  } catch (error) {
    const { data, status } = handleApiError(error);
    return NextResponse.json(data, { status });
  }
}

export async function POST() {
  try {
    const { data, status } = await api.post("/api/v1/dashboard/manual-scan");
    return NextResponse.json(data, { status });
  } catch (error) {
    const { data, status } = handleApiError(error);
    return NextResponse.json(data, { status });
  }
}
