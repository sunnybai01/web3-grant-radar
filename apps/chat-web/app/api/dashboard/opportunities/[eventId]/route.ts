import { NextResponse } from "next/server";
import { api, handleApiError } from "@/lib/api";

export async function DELETE(
  _req: Request,
  { params }: { params: Promise<{ eventId: string }> }
) {
  const { eventId } = await params;
  try {
    const { data, status } = await api.delete(
      `/api/v1/dashboard/opportunities/${eventId}`
    );
    return NextResponse.json(data, { status });
  } catch (error) {
    const { data, status } = handleApiError(error);
    return NextResponse.json(data, { status });
  }
}
