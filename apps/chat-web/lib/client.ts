import { localApi } from "./api";
import type {
  DailySummaryTriggerResponse,
  DashboardOpportunitiesResponse,
  DashboardOpportunityDetail,
  DashboardOpportunityItem,
  DashboardScheduleLogsResponse,
  DashboardSourceHealthResponse,
  DedupResetResponse,
  DeleteOpportunityResponse,
  InvestigationResponse,
  ManualScanStatusResponse,
  OpportunityFilters,
  ProposeOptionsRequest,
  ProposeOptionsResponse,
  SelectTargetsRequest,
  SelectTargetsResponse,
  TavilyUnlockResponse,
  TriageStatus,
  VerifyResponse,
} from "../types/chat";

/** Browser-side calls to the Next.js proxy routes under /api. */

export function opportunityQueryParams(filters: OpportunityFilters) {
  const params = new URLSearchParams({ status: filters.status, sort: filters.sort });
  if (filters.type !== "all") params.append("event_types", filters.type);
  if (filters.trust !== "all") params.set("source_trust", filters.trust);
  if (filters.ecosystem) params.set("ecosystem", filters.ecosystem);
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.closingSoon) params.set("closing_within_days", "7");
  return params;
}

export const client = {
  listOpportunities: (filters: OpportunityFilters) =>
    localApi
      .get<DashboardOpportunitiesResponse>(
        `/api/dashboard/opportunities?${opportunityQueryParams(filters)}`
      )
      .then((r) => r.data),
  getOpportunity: (id: number) =>
    localApi.get<DashboardOpportunityDetail>(`/api/dashboard/opportunities/${id}`).then((r) => r.data),
  triageOpportunity: (id: number, status: TriageStatus) =>
    localApi
      .put<DashboardOpportunityItem>(`/api/dashboard/opportunities/${id}/triage`, { status })
      .then((r) => r.data),
  deleteOpportunity: (id: number) =>
    localApi.delete<DeleteOpportunityResponse>(`/api/dashboard/opportunities/${id}`).then((r) => r.data),

  sourceHealth: () =>
    localApi.get<DashboardSourceHealthResponse>("/api/dashboard/source-health").then((r) => r.data),
  scheduleLogs: (limit = 50) =>
    localApi
      .get<DashboardScheduleLogsResponse>(`/api/dashboard/schedule-logs?limit=${limit}`)
      .then((r) => r.data),
  manualScan: () =>
    localApi.get<ManualScanStatusResponse>("/api/dashboard/manual-scan").then((r) => r.data),
  startManualScan: () =>
    localApi.post<ManualScanStatusResponse>("/api/dashboard/manual-scan").then((r) => r.data),
  sendDailySummary: () =>
    localApi.post<DailySummaryTriggerResponse>("/api/dashboard/daily-summary").then((r) => r.data),
  unlockTavily: () =>
    localApi.post<TavilyUnlockResponse>("/api/admin/tavily-unlock").then((r) => r.data),
  resetDedup: () =>
    localApi.post<DedupResetResponse>("/api/admin/reset-dedup").then((r) => r.data),

  selectTargets: (body: SelectTargetsRequest) =>
    localApi.post<SelectTargetsResponse>("/api/chat/select-targets", body).then((r) => r.data),
  verify: (body: { target_event_ids: number[] }) =>
    localApi.post<VerifyResponse>("/api/chat/verify", body).then((r) => r.data),
  proposeOptions: (body: ProposeOptionsRequest) =>
    localApi.post<ProposeOptionsResponse>("/api/chat/propose-options", body).then((r) => r.data),
  investigate: (body: { event_id: number }) =>
    localApi.post<InvestigationResponse>("/api/chat/investigate", body).then((r) => r.data),
};

/** Human-readable message from an axios / proxy error. */
export function errorMessage(error: unknown, fallback: string): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    for (const key of ["detail", "error", "message"]) {
      if (typeof record[key] === "string" && record[key]) return record[key] as string;
    }
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
