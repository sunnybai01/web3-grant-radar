"use client";

import { useFrontendTool } from "@copilotkit/react-core/v2";
import {
  Activity,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  ExternalLink,
  Eye,
  EyeOff,
  MessageSquare,
  MoreHorizontal,
  RotateCcw,
  SearchCheck,
  ShieldCheck,
  Trash2,
  Unlock,
  XCircle,
} from "lucide-react";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { z } from "zod";

import { runMixedModeVerification } from "../lib/actions";
import { localApi } from "../lib/api";
import {
  getManualScanProgressLabel,
  getScheduleStatusMap,
  summarizeManualScan,
} from "../lib/manual-scan";
import { runInvestigation } from "../lib/investigation";
import type {
  AnalysisTargetInput,
  DailySummaryTriggerResponse,
  DashboardOpportunitiesResponse,
  DashboardOpportunityItem,
  DeleteOpportunityResponse,
  DismissEventResponse,
  DedupResetResponse,
  InvestigationResponse,
  DashboardScheduleLogsResponse,
  DashboardSourceHealthResponse,
  ManualScanStatusResponse,
  MixedModeResult,
  ProposeOptionsRequest,
  ProposeOptionsResponse,
  SelectTargetsRequest,
  SelectTargetsResponse,
  TavilyUnlockResponse,
  VerifyResponse,
} from "../types/chat";
import CopilotDrawer from "./copilot-drawer";
import ResultPanels from "./result-panels";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader } from "./ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { Select } from "./ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/table";

type DashboardTab = "opportunities" | "sourceHealth" | "scheduleLogs";

type EventTypeFilter = "grant" | "hackathon" | "all";
type SourceTrustFilter = "all" | "official" | "discovery";

const analysisToolSchema = z.object({
  eventId: z.number().optional(),
  sourceName: z.string().optional(),
  from: z.string().optional(),
  to: z.string().optional(),
  limit: z.number().optional(),
});

const dashboardContextToolSchema = z.object({
  includeRows: z.boolean().optional(),
  rowLimit: z.number().min(1).max(20).optional(),
});

export function shouldRequestTabData({
  hasData,
  isLoading,
  hasError,
}: {
  hasData: boolean;
  isLoading: boolean;
  hasError: boolean;
}) {
  return !isLoading && (!hasData || hasError);
}

export function scrollToRelatedPanel(
  element: HTMLDivElement | null | undefined
) {
  element?.scrollIntoView({
    behavior: "smooth",
    block: "start",
    inline: "nearest",
  });
}

const isoDatePattern = /^\d{4}-\d{2}-\d{2}(?:[T\s].*)?$/;

function normalizeDateValue(value?: string) {
  if (!value) {
    return undefined;
  }

  const trimmed = value.trim();
  if (!isoDatePattern.test(trimmed)) {
    return undefined;
  }

  return trimmed;
}

export function removeOpportunityFromState(
  dashboardData: DashboardOpportunitiesResponse | null,
  selectedOpportunity: DashboardOpportunityItem | null,
  deletedId: number
) {
  if (!dashboardData) {
    return {
      dashboardData,
      selectedOpportunity:
        selectedOpportunity?.id === deletedId ? null : selectedOpportunity,
    };
  }

  const items = dashboardData.items.filter((item) => item.id !== deletedId);
  const nextSelected =
    selectedOpportunity?.id === deletedId
      ? (items[0] ?? null)
      : selectedOpportunity;

  return {
    dashboardData: {
      ...dashboardData,
      metrics: {
        ...dashboardData.metrics,
        total_shown: items.length,
      },
      items,
    },
    selectedOpportunity: nextSelected,
  };
}

export function normalizeAnalysisTargetInput(
  input: {
    eventId?: number;
    sourceName?: string;
    from?: string;
    to?: string;
    limit?: number;
  },
  fallbackEventId?: number
): AnalysisTargetInput {
  const eventId = input.eventId ?? fallbackEventId;

  if (eventId !== undefined) {
    return { event_id: eventId };
  }

  const sourceName = input.sourceName?.trim();
  const from = normalizeDateValue(input.from);
  const to = normalizeDateValue(input.to);

  if (!sourceName || !from || !to) {
    return {};
  }

  const normalized: AnalysisTargetInput = {
    source_name: sourceName,
    from,
    to,
  };

  if (typeof input.limit === "number") {
    normalized.limit = Math.min(100, Math.max(1, Math.trunc(input.limit)));
  }

  return normalized;
}

export default function AgentChat() {
  const resultsSectionRef = useRef<HTMLDivElement | null>(null);
  const [activeTab, setActiveTab] = useState<DashboardTab>("opportunities");
  const [typeFilter, setTypeFilter] = useState<EventTypeFilter>("all");
  const [sourceFilter, setSourceFilter] = useState<SourceTrustFilter>("all");
  const [dashboardData, setDashboardData] =
    useState<DashboardOpportunitiesResponse | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [isDashboardLoading, setIsDashboardLoading] = useState(true);
  const [sourceHealthData, setSourceHealthData] =
    useState<DashboardSourceHealthResponse | null>(null);
  const [sourceHealthError, setSourceHealthError] = useState<string | null>(
    null
  );
  const [isSourceHealthLoading, setIsSourceHealthLoading] = useState(false);
  const [scheduleLogsData, setScheduleLogsData] =
    useState<DashboardScheduleLogsResponse | null>(null);
  const [scheduleLogsError, setScheduleLogsError] = useState<string | null>(
    null
  );
  const [isScheduleLogsLoading, setIsScheduleLogsLoading] = useState(false);
  const [selectedOpportunity, setSelectedOpportunity] =
    useState<DashboardOpportunityItem | null>(null);
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);
  const [result, setResult] = useState<MixedModeResult | null>(null);
  const [verifyingEventId, setVerifyingEventId] = useState<number | null>(null);
  const [investigation, setInvestigation] =
    useState<InvestigationResponse | null>(null);
  const [isInvestigating, setIsInvestigating] = useState(false);
  const [manualScanStatus, setManualScanStatus] =
    useState<ManualScanStatusResponse | null>(null);
  const [manualScanError, setManualScanError] = useState<string | null>(null);
  const [isManualScanStarting, setIsManualScanStarting] = useState(false);
  const [deletingEventId, setDeletingEventId] = useState<number | null>(null);
  const [dismissingEventId, setDismissingEventId] = useState<number | null>(
    null
  );
  const [dailySummaryStatus, setDailySummaryStatus] =
    useState<DailySummaryTriggerResponse | null>(null);
  const [dailySummaryError, setDailySummaryError] = useState<string | null>(
    null
  );
  const [isDailySummarySending, setIsDailySummarySending] = useState(false);
  const [isUnlockingTavily, setIsUnlockingTavily] = useState(false);
  const [tavilyUnlockResult, setTavilyUnlockResult] = useState<string | null>(
    null
  );
  const [isResettingDedup, setIsResettingDedup] = useState(false);
  const [dedupResetResult, setDedupResetResult] = useState<string | null>(null);

  // Show result notifications for 6 seconds then auto-dismiss
  function showResult(setter: (v: string | null) => void, message: string) {
    setter(message);
    setTimeout(() => setter(null), 6000);
  }

  const api = {
    selectTargets: async (
      body: SelectTargetsRequest
    ): Promise<SelectTargetsResponse> =>
      localApi.post("/api/chat/select-targets", body).then((r) => r.data),
    verify: async (body: {
      target_event_ids: number[];
    }): Promise<VerifyResponse> =>
      localApi.post("/api/chat/verify", body).then((r) => r.data),
    proposeOptions: async (
      body: ProposeOptionsRequest
    ): Promise<ProposeOptionsResponse> =>
      localApi.post("/api/chat/propose-options", body).then((r) => r.data),
    investigate: async (body: {
      event_id: number;
    }): Promise<InvestigationResponse> =>
      localApi.post("/api/chat/investigate", body).then((r) => r.data),
  };

  const currentTarget = useMemo<AnalysisTargetInput>(
    () => ({
      event_id: selectedOpportunity?.id,
    }),
    [selectedOpportunity]
  );

  const manualScanProgressLabel = useMemo(
    () => getManualScanProgressLabel(manualScanStatus),
    [manualScanStatus]
  );

  const manualScanSummary = useMemo(
    () => summarizeManualScan(manualScanStatus),
    [manualScanStatus]
  );

  const manualScanSchedules = useMemo(
    () => getScheduleStatusMap(manualScanStatus),
    [manualScanStatus]
  );

  const dashboardContext = useMemo(() => {
    const activeCounts = {
      opportunities: dashboardData?.items.length ?? 0,
      sourceHealth: sourceHealthData?.items.length ?? 0,
      scheduleLogs: scheduleLogsData?.items.length ?? 0,
    };

    return {
      activeTab,
      loading: {
        opportunities: isDashboardLoading,
        sourceHealth: isSourceHealthLoading,
        scheduleLogs: isScheduleLogsLoading,
      },
      errors: {
        opportunities: dashboardError,
        sourceHealth: sourceHealthError,
        scheduleLogs: scheduleLogsError,
      },
      filters: {
        type: typeFilter,
        source_trust: sourceFilter,
      },
      counts: activeCounts,
      selectedOpportunity: selectedOpportunity
        ? {
            id: selectedOpportunity.id,
            title: selectedOpportunity.title,
            score: selectedOpportunity.score,
            type: selectedOpportunity.type,
            ecosystem: selectedOpportunity.ecosystem,
            amount: selectedOpportunity.amount,
            deadline: selectedOpportunity.deadline,
            source_trust: selectedOpportunity.source_trust,
            verification_verdict: selectedOpportunity.verification_verdict,
            apply_url: selectedOpportunity.apply_url,
          }
        : null,
      opportunitiesMetrics: dashboardData?.metrics ?? null,
      sourceHealthSummary: sourceHealthData?.summary ?? null,
      scheduleLogSummary: scheduleLogsData?.summary ?? null,
      manualScanStatus,
    };
  }, [
    activeTab,
    dashboardData,
    dashboardError,
    typeFilter,
    sourceFilter,
    isDashboardLoading,
    isScheduleLogsLoading,
    isSourceHealthLoading,
    scheduleLogsData,
    scheduleLogsError,
    selectedOpportunity,
    sourceHealthData,
    sourceHealthError,
    manualScanStatus,
  ]);

  async function loadOpportunitiesData() {
    setIsDashboardLoading(true);
    setDashboardError(null);

    try {
      const data = (await localApi.get("/api/dashboard/opportunities"))
        .data as DashboardOpportunitiesResponse;

      setDashboardData(data);
      setSelectedOpportunity((previous) => {
        if (!data.items.length) {
          return null;
        }

        if (previous) {
          const match = data.items.find((item) => item.id === previous.id);
          if (match) {
            return match;
          }
        }

        return data.items[0] ?? null;
      });
    } catch (error) {
      setDashboardError(
        error instanceof Error
          ? error.message
          : "Failed to load dashboard data."
      );
    } finally {
      setIsDashboardLoading(false);
    }
  }

  async function loadSourceHealthData() {
    setIsSourceHealthLoading(true);
    setSourceHealthError(null);

    try {
      const data = (await localApi.get("/api/dashboard/source-health"))
        .data as DashboardSourceHealthResponse;
      setSourceHealthData(data);
    } catch (error) {
      setSourceHealthError(
        error instanceof Error
          ? error.message
          : "Failed to load source health data."
      );
    } finally {
      setIsSourceHealthLoading(false);
    }
  }

  async function loadScheduleLogsData() {
    setIsScheduleLogsLoading(true);
    setScheduleLogsError(null);

    try {
      const data = (await localApi.get("/api/dashboard/schedule-logs?limit=50"))
        .data as DashboardScheduleLogsResponse;
      setScheduleLogsData(data);
    } catch (error) {
      setScheduleLogsError(
        error instanceof Error ? error.message : "Failed to load schedule logs."
      );
    } finally {
      setIsScheduleLogsLoading(false);
    }
  }

  async function loadManualScanStatus(refreshOnCompletion = false) {
    try {
      const data = (await localApi.get("/api/dashboard/manual-scan"))
        .data as ManualScanStatusResponse;
      setManualScanStatus(data);
      setManualScanError(null);

      if (refreshOnCompletion && data.status !== "running" && data.job_id) {
        await Promise.all([
          loadOpportunitiesData(),
          loadSourceHealthData(),
          loadScheduleLogsData(),
        ]);
      }
    } catch (error) {
      setManualScanError(
        error instanceof Error
          ? error.message
          : "Failed to load manual scan status."
      );
    }
  }

  async function triggerManualScan() {
    setIsManualScanStarting(true);
    setManualScanError(null);

    try {
      const data = (await localApi.post("/api/dashboard/manual-scan", {}))
        .data as ManualScanStatusResponse;
      setManualScanStatus(data);
      await loadScheduleLogsData();
    } catch (error) {
      setManualScanError(
        error instanceof Error ? error.message : "Failed to start manual scan."
      );
    } finally {
      setIsManualScanStarting(false);
    }
  }

  async function triggerDailySummary() {
    setIsDailySummarySending(true);
    setDailySummaryError(null);

    try {
      const data = (await localApi.post("/api/dashboard/daily-summary", {}))
        .data as DailySummaryTriggerResponse;
      setDailySummaryStatus(data);
    } catch (error) {
      setDailySummaryError(
        error instanceof Error ? error.message : "Failed to send daily summary."
      );
    } finally {
      setIsDailySummarySending(false);
    }
  }

  async function unlockTavily() {
    setIsUnlockingTavily(true);
    setTavilyUnlockResult(null);

    try {
      const data = (await localApi.post("/api/admin/tavily-unlock", {}))
        .data as TavilyUnlockResponse;
      showResult(setTavilyUnlockResult, data.message);
    } catch (error) {
      showResult(
        setTavilyUnlockResult,
        error instanceof Error ? error.message : "Unlock failed."
      );
    } finally {
      setIsUnlockingTavily(false);
    }
  }

  async function resetDedupState() {
    setIsResettingDedup(true);
    setDedupResetResult(null);

    try {
      const data = (await localApi.post("/api/admin/reset-dedup", {}))
        .data as DedupResetResponse;
      showResult(setDedupResetResult, data.message);
    } catch (error) {
      showResult(
        setDedupResetResult,
        error instanceof Error ? error.message : "Reset failed."
      );
    } finally {
      setIsResettingDedup(false);
    }
  }

  async function deleteOpportunity(item: DashboardOpportunityItem) {
    if (deletingEventId !== null) {
      return;
    }

    if (
      typeof window !== "undefined" &&
      !window.confirm(`Delete opportunity #${item.id}? This cannot be undone.`)
    ) {
      return;
    }

    setDeletingEventId(item.id);
    setDashboardError(null);

    try {
      (await localApi.delete(`/api/dashboard/opportunities/${item.id}`))
        .data as DeleteOpportunityResponse;

      const nextState = removeOpportunityFromState(
        dashboardData,
        selectedOpportunity,
        item.id
      );
      setDashboardData(nextState.dashboardData);
      setSelectedOpportunity(nextState.selectedOpportunity);
      await loadOpportunitiesData();
    } catch (error) {
      setDashboardError(
        error instanceof Error ? error.message : "Failed to delete opportunity."
      );
    } finally {
      setDeletingEventId(null);
    }
  }

  async function deleteSelectedOpportunity() {
    if (!selectedOpportunity) {
      return;
    }

    await deleteOpportunity(selectedOpportunity);
  }

  async function dismissOpportunity(item: DashboardOpportunityItem) {
    if (dismissingEventId !== null) {
      return;
    }

    setDismissingEventId(item.id);
    setDashboardError(null);

    const newDismissed = !item.is_dismissed;

    try {
      const result = (
        await localApi.put(
          `/api/dashboard/opportunities/${item.id}/dismiss?dismissed=${newDismissed}`
        )
      ).data as DismissEventResponse;

      // Update dashboardData to reflect new dismissed status
      setDashboardData((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          items: prev.items.map((it) =>
            it.id === item.id
              ? { ...it, is_dismissed: result.is_dismissed }
              : it
          ),
        };
      });

      // Update selected opportunity if it's the one dismissed/restored
      if (selectedOpportunity?.id === item.id) {
        setSelectedOpportunity((prev) =>
          prev ? { ...prev, is_dismissed: result.is_dismissed } : null
        );
      }
    } catch (error) {
      setDashboardError(
        error instanceof Error
          ? error.message
          : "Failed to dismiss opportunity."
      );
    } finally {
      setDismissingEventId(null);
    }
  }

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      await loadOpportunitiesData();
    })();

    return () => {
      cancelled = true;
    };
  }, [typeFilter, sourceFilter]);

  useEffect(() => {
    if (
      activeTab !== "sourceHealth" ||
      !shouldRequestTabData({
        hasData: Boolean(sourceHealthData),
        isLoading: isSourceHealthLoading,
        hasError: Boolean(sourceHealthError),
      })
    ) {
      return;
    }

    let cancelled = false;

    void (async () => {
      await loadSourceHealthData();
    })();

    return () => {
      cancelled = true;
    };
  }, [activeTab, sourceHealthData, isSourceHealthLoading, sourceHealthError]);

  useEffect(() => {
    if (
      activeTab !== "scheduleLogs" ||
      !shouldRequestTabData({
        hasData: Boolean(scheduleLogsData),
        isLoading: isScheduleLogsLoading,
        hasError: Boolean(scheduleLogsError),
      })
    ) {
      return;
    }

    let cancelled = false;

    void (async () => {
      await loadScheduleLogsData();
    })();

    return () => {
      cancelled = true;
    };
  }, [activeTab, scheduleLogsData, isScheduleLogsLoading, scheduleLogsError]);

  useEffect(() => {
    void loadManualScanStatus();
  }, []);

  useEffect(() => {
    if (manualScanStatus?.status !== "running") {
      return;
    }

    const intervalId = window.setInterval(() => {
      void loadManualScanStatus(true);
    }, 4000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [manualScanStatus?.job_id, manualScanStatus?.status]);

  const analyzeTarget = async (override?: Partial<AnalysisTargetInput>) => {
    const merged: AnalysisTargetInput = {
      ...currentTarget,
      ...override,
    };

    const eventId = merged.event_id ?? null;
    setVerifyingEventId(eventId);
    try {
      const data = await runMixedModeVerification(api, merged);
      setResult(data);
      return data;
    } finally {
      setVerifyingEventId(null);
    }
  };

  const investigateSelectedOpportunity = async (eventId: number) => {
    setIsInvestigating(true);
    try {
      const data = await runInvestigation(api, eventId);
      setInvestigation(data);
      return data;
    } finally {
      setIsInvestigating(false);
    }
  };

  const handleTabChange = (nextTab: DashboardTab) => {
    setActiveTab(nextTab);

    if (
      nextTab === "sourceHealth" &&
      shouldRequestTabData({
        hasData: Boolean(sourceHealthData),
        isLoading: isSourceHealthLoading,
        hasError: Boolean(sourceHealthError),
      })
    ) {
      void loadSourceHealthData();
    }

    if (
      nextTab === "scheduleLogs" &&
      shouldRequestTabData({
        hasData: Boolean(scheduleLogsData),
        isLoading: isScheduleLogsLoading,
        hasError: Boolean(scheduleLogsError),
      })
    ) {
      void loadScheduleLogsData();
    }
  };

  useFrontendTool(
    {
      name: "analyzeDatabaseTargets",
      description:
        "Load opportunity records from the database, verify their reliability, and prepare grounded implementation options.",
      parameters: analysisToolSchema,
      handler: async (input) => {
        const data = await analyzeTarget(
          normalizeAnalysisTargetInput(input, selectedOpportunity?.id)
        );

        return {
          target: input,
          selectedEventIds: data.selected.target_event_ids,
          verification: data.verification,
          options: data.options.options,
        };
      },
    },
    [currentTarget, selectedOpportunity]
  );

  useFrontendTool(
    {
      name: "getDashboardContext",
      description:
        "Read the current dashboard context, including active tab, filters, selected row, and visible data summaries.",
      parameters: dashboardContextToolSchema,
      handler: async (input) => {
        const includeRows = input.includeRows ?? false;
        const rowLimit = input.rowLimit ?? 5;

        const response: Record<string, unknown> = {
          ...dashboardContext,
        };

        if (!includeRows) {
          return response;
        }

        if (activeTab === "opportunities") {
          response.visibleRows = (dashboardData?.items ?? [])
            .slice(0, rowLimit)
            .map((item) => ({
              id: item.id,
              score: item.score,
              type: item.type,
              title: item.title,
              ecosystem: item.ecosystem,
              amount: item.amount,
              deadline: item.deadline,
              verified: item.verified,
              heat: item.heat,
              source_trust: item.source_trust,
              verification_verdict: item.verification_verdict,
            }));
        } else if (activeTab === "sourceHealth") {
          response.visibleRows = (sourceHealthData?.items ?? [])
            .slice(0, rowLimit)
            .map((item) => ({
              source: item.source,
              status: item.status,
              failures: item.failures,
              last_success: item.last_success,
              last_fetch: item.last_fetch,
              last_error: item.last_error,
            }));
        } else {
          response.visibleRows = (scheduleLogsData?.items ?? [])
            .slice(0, rowLimit)
            .map((item) => ({
              id: item.id,
              job: item.job,
              status: item.status,
              started: item.started,
              fetched: item.fetched,
              new: item.new,
              deduped: item.deduped,
              verified: item.verified,
              error: item.error,
            }));
        }

        return response;
      },
    },
    [
      activeTab,
      dashboardContext,
      dashboardData,
      scheduleLogsData,
      sourceHealthData,
    ]
  );

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(249,115,22,0.12),_transparent_40%),hsl(var(--background))] px-4 py-6 md:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-5">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Badge className="bg-primary/12 text-primary hover:bg-primary/12 text-xs font-medium">
              Signal Room
            </Badge>
            <h1 className="text-xl font-semibold tracking-[-0.03em] md:text-2xl">
              Opportunity Pipeline
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <Button
              disabled={
                isManualScanStarting || manualScanStatus?.status === "running"
              }
              onClick={() => void triggerManualScan()}
            >
              {isManualScanStarting
                ? "Starting..."
                : manualScanStatus?.status === "running"
                  ? "Scanning"
                  : "Run Scan"}
            </Button>
            <div className="mx-1 h-6 w-px bg-border/80" aria-hidden="true" />
            <Button
              disabled={isDailySummarySending}
              variant="outline"
              className="text-xs"
              onClick={() => void triggerDailySummary()}
            >
              {isDailySummarySending ? "Sending..." : "Daily Summary"}
            </Button>
            <Button
              disabled={isUnlockingTavily}
              variant="outline"
              className="text-xs"
              onClick={() => void unlockTavily()}
            >
              <Unlock className="mr-1 h-3 w-3" />
              {isUnlockingTavily ? "..." : "Tavily"}
            </Button>
            <Button
              disabled={isResettingDedup}
              variant="outline"
              className="text-xs"
              onClick={() => void resetDedupState()}
            >
              <RotateCcw className="mr-1 h-3 w-3" />
              {isResettingDedup ? "..." : "Dedup"}
            </Button>
          </div>
        </div>

        {tavilyUnlockResult || dedupResetResult || manualScanStatus?.job_id ? (
          <div className="flex flex-wrap items-center gap-3 rounded-full border border-border/60 bg-card/95 px-4 py-2 text-sm shadow-sm">
            {manualScanStatus?.job_id ? (
              <>
                <Badge variant="outline" className="text-xs capitalize">
                  {manualScanStatus.status}
                </Badge>
                <span className="text-muted-foreground">
                  {manualScanStatus.current_stage
                    ? `Stage: ${manualScanStatus.current_stage}`
                    : `Job #${manualScanStatus.job_id.slice(0, 8)}`}
                </span>
                <span className="tabular-nums text-xs text-muted-foreground">
                  fetched {manualScanSummary.fetched} · new{" "}
                  {manualScanSummary.new} · verified{" "}
                  {manualScanSummary.verified} · pushed{" "}
                  {manualScanSummary.pushed}
                </span>
              </>
            ) : null}
            {tavilyUnlockResult ? (
              <span className="flex items-center gap-2 text-muted-foreground">
                <Unlock className="h-3 w-3" />
                {tavilyUnlockResult}
              </span>
            ) : null}
            {dedupResetResult ? (
              <span className="flex items-center gap-2 text-muted-foreground">
                <RotateCcw className="h-3 w-3" />
                {dedupResetResult}
              </span>
            ) : null}
          </div>
        ) : null}

        <div className="grid gap-3 md:grid-cols-5">
          <MetricCard
            label="Total Shown"
            value={dashboardData?.metrics.total_shown ?? "-"}
            icon={CircleDashed}
          />
          <MetricCard
            label="Avg Score"
            value={dashboardData?.metrics.avg_score ?? "-"}
          />
          <MetricCard
            label="Verified %"
            value={
              dashboardData ? `${dashboardData.metrics.verified_percent}%` : "-"
            }
            hint={
              dashboardData?.metrics.unchecked_count
                ? `${dashboardData.metrics.unchecked_count} unchecked`
                : undefined
            }
            variant="success"
            icon={CheckCircle2}
          />
          <MetricCard
            label="Grants / Hacks"
            value={
              dashboardData
                ? `${dashboardData.metrics.grants}/${dashboardData.metrics.hackathons}`
                : "-"
            }
          />
          <MetricCard
            label="Official / Discovery"
            value={
              dashboardData
                ? `${dashboardData.metrics.official}/${dashboardData.metrics.discovery}`
                : "-"
            }
          />
        </div>

        <Card className="border-border/70 bg-card/95 shadow-sm">
          <CardHeader className="pb-2">
            <div
              className="rounded-full bg-muted/60 p-1 inline-flex gap-0.5"
              role="tablist"
            >
              {(["opportunities", "sourceHealth", "scheduleLogs"] as const).map(
                (tab) => {
                  const labels: Record<DashboardTab, string> = {
                    opportunities: "Opportunities",
                    sourceHealth: "Source Health",
                    scheduleLogs: "Schedule Logs",
                  };
                  return (
                    <button
                      key={tab}
                      role="tab"
                      aria-selected={activeTab === tab}
                      onClick={() => handleTabChange(tab)}
                      className={`rounded-full px-4 py-1.5 text-sm font-medium transition-all ${
                        activeTab === tab
                          ? "bg-background text-foreground shadow-sm"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {labels[tab]}
                    </button>
                  );
                }
              )}
            </div>
          </CardHeader>
          <CardContent>
            {activeTab === "opportunities" ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-foreground">
                    {dashboardData?.items.length ?? 0} opportunities
                  </h2>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5">
                      <label className="text-xs text-muted-foreground">
                        Type
                      </label>
                      <Select
                        className="h-8 w-28 rounded-full text-xs"
                        value={typeFilter}
                        onChange={(e) =>
                          setTypeFilter(e.target.value as EventTypeFilter)
                        }
                      >
                        <option value="all">All</option>
                        <option value="grant">Grant</option>
                        <option value="hackathon">Hackathon</option>
                      </Select>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <label className="text-xs text-muted-foreground">
                        Source
                      </label>
                      <Select
                        className="h-8 w-28 rounded-full text-xs"
                        value={sourceFilter}
                        onChange={(e) =>
                          setSourceFilter(e.target.value as SourceTrustFilter)
                        }
                      >
                        <option value="all">All</option>
                        <option value="official">Official</option>
                        <option value="discovery">Discovery</option>
                      </Select>
                    </div>
                  </div>
                </div>

                {dashboardError ? (
                  <EmptyState
                    title="Dashboard load failed"
                    description={dashboardError}
                  />
                ) : isDashboardLoading ? (
                  <EmptyState
                    title="Loading opportunities"
                    description="Fetching the current filtered opportunity set..."
                  />
                ) : !dashboardData?.items.length ? (
                  <EmptyState
                    title="No opportunities match your filters"
                    description="Adjust the current filter set to broaden the result window."
                  />
                ) : (
                  <>
                    <div className="rounded-xl border border-border">
                      <Table>
                        <TableHeader className="bg-muted/60 text-left text-xs uppercase tracking-[0.18em] text-muted-foreground">
                          <TableRow>
                            <TableHead className="px-4 py-3">Score</TableHead>
                            <TableHead className="px-4 py-3">Type</TableHead>
                            <TableHead className="px-4 py-3">Title</TableHead>
                            <TableHead className="px-4 py-3 w-[50px]">
                              Link
                            </TableHead>
                            <TableHead className="px-4 py-3">
                              Ecosystem
                            </TableHead>
                            <TableHead className="px-4 py-3">Amount</TableHead>
                            <TableHead className="px-4 py-3">
                              Deadline
                            </TableHead>
                            <TableHead className="px-4 py-3">Heat</TableHead>
                            <TableHead className="px-4 py-3">Trust</TableHead>
                            <TableHead className="px-4 py-3">
                              Verified
                            </TableHead>
                            <TableHead className="px-4 py-3">Status</TableHead>
                            <TableHead className="px-4 py-3 w-[50px]"></TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {dashboardData.items
                            .filter((item) => {
                              if (
                                typeFilter !== "all" &&
                                item.type.toLowerCase() !== typeFilter
                              )
                                return false;
                              if (
                                sourceFilter !== "all" &&
                                item.source_trust !== sourceFilter
                              )
                                return false;
                              return true;
                            })
                            .map((item) => {
                              const isSelected =
                                item.id === selectedOpportunity?.id;
                              return (
                                <TableRow
                                  key={item.id}
                                  data-state={
                                    isSelected ? "selected" : undefined
                                  }
                                  className={`${
                                    isSelected
                                      ? "bg-primary/10 shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.25)] border-l-[3px] border-l-primary"
                                      : "hover:bg-accent/50 border-l-[3px] border-l-transparent"
                                  } ${item.is_dismissed ? "opacity-50" : ""}`}
                                >
                                  <TableCell className="px-4 py-3 font-medium text-foreground">
                                    {item.score ?? "-"}
                                  </TableCell>
                                  <TableCell className="px-4 py-3 text-muted-foreground">
                                    {item.type}
                                  </TableCell>
                                  <TableCell className="px-4 py-3">
                                    <button
                                      type="button"
                                      className={`text-left font-medium text-foreground ${item.is_dismissed ? "line-through" : ""}`}
                                      onClick={() =>
                                        setSelectedOpportunity(item)
                                      }
                                    >
                                      {item.title}
                                    </button>
                                  </TableCell>
                                  <TableCell className="px-4 py-3">
                                    {item.apply_url ? (
                                      <a
                                        href={item.apply_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-1 text-muted-foreground hover:text-primary transition-colors"
                                        title={item.apply_url}
                                      >
                                        <ExternalLink className="h-3.5 w-3.5" />
                                      </a>
                                    ) : (
                                      <span className="text-muted-foreground/40">
                                        —
                                      </span>
                                    )}
                                  </TableCell>
                                  <TableCell className="px-4 py-3 text-muted-foreground">
                                    {item.ecosystem}
                                  </TableCell>
                                  <TableCell className="px-4 py-3 text-muted-foreground">
                                    {item.amount}
                                  </TableCell>
                                  <TableCell className="px-4 py-3 text-muted-foreground">
                                    {item.deadline}
                                  </TableCell>
                                  <TableCell className="px-4 py-3 text-muted-foreground">
                                    {item.heat}
                                  </TableCell>
                                  <TableCell className="px-4 py-3 text-muted-foreground">
                                    {item.source_trust === "official"
                                      ? "Official"
                                      : "Discovery"}
                                  </TableCell>
                                  <TableCell className="px-4 py-3">
                                    {item.verified ? (
                                      <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100 text-xs font-normal">
                                        Verified
                                      </Badge>
                                    ) : (
                                      <Badge
                                        variant="outline"
                                        className="text-xs font-normal text-muted-foreground"
                                      >
                                        Unverified
                                      </Badge>
                                    )}
                                  </TableCell>
                                  <TableCell className="px-4 py-3">
                                    {item.is_dismissed ? (
                                      <Badge className="bg-muted text-muted-foreground hover:bg-muted text-xs font-normal">
                                        Dismissed
                                      </Badge>
                                    ) : (
                                      <Badge className="bg-emerald-100 text-emerald-700 hover:bg-emerald-100 text-xs font-normal">
                                        Active
                                      </Badge>
                                    )}
                                  </TableCell>
                                  <TableCell className="px-4 py-3">
                                    <DropdownMenu>
                                      <DropdownMenuTrigger asChild>
                                        <button
                                          type="button"
                                          aria-label="Actions"
                                          className={`inline-flex h-8 w-8 items-center justify-center rounded-full transition-colors ${
                                            isSelected
                                              ? "bg-primary text-primary-foreground"
                                              : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                          }`}
                                        >
                                          <MoreHorizontal className="h-4 w-4" />
                                        </button>
                                      </DropdownMenuTrigger>
                                      <DropdownMenuContent
                                        align="end"
                                        className="w-40"
                                      >
                                        <DropdownMenuItem
                                          onSelect={() => {
                                            setSelectedOpportunity(item);
                                            void analyzeTarget({
                                              event_id: item.id,
                                            });
                                            window.requestAnimationFrame(() => {
                                              scrollToRelatedPanel(
                                                resultsSectionRef.current
                                              );
                                            });
                                          }}
                                          disabled={
                                            verifyingEventId === item.id
                                          }
                                        >
                                          <SearchCheck className="h-4 w-4" />
                                          Verify
                                        </DropdownMenuItem>
                                        <DropdownMenuItem
                                          onSelect={() => {
                                            setSelectedOpportunity(item);
                                            setIsCopilotOpen(true);
                                            window.requestAnimationFrame(() => {
                                              scrollToRelatedPanel(
                                                resultsSectionRef.current
                                              );
                                            });
                                          }}
                                        >
                                          <MessageSquare className="h-4 w-4" />
                                          Ask Copilot
                                        </DropdownMenuItem>
                                        <DropdownMenuItem
                                          onSelect={() =>
                                            void dismissOpportunity(item)
                                          }
                                          disabled={
                                            dismissingEventId === item.id
                                          }
                                        >
                                          {item.is_dismissed ? (
                                            <Eye className="h-4 w-4" />
                                          ) : (
                                            <EyeOff className="h-4 w-4" />
                                          )}
                                          {item.is_dismissed
                                            ? "Restore"
                                            : "Dismiss"}
                                        </DropdownMenuItem>
                                        <DropdownMenuSeparator />
                                        <DropdownMenuItem
                                          onSelect={() =>
                                            void deleteOpportunity(item)
                                          }
                                          disabled={deletingEventId === item.id}
                                          className="text-rose-600 focus:text-rose-600"
                                        >
                                          <Trash2 className="h-4 w-4" />
                                          Delete
                                        </DropdownMenuItem>
                                      </DropdownMenuContent>
                                    </DropdownMenu>
                                  </TableCell>
                                </TableRow>
                              );
                            })}
                        </TableBody>
                      </Table>
                    </div>
                  </>
                )}
              </div>
            ) : activeTab === "sourceHealth" ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-foreground">
                    {sourceHealthData?.summary.total_sources ?? 0} sources
                  </h2>
                </div>

                {sourceHealthError ? (
                  <EmptyState
                    title="Source health load failed"
                    description={sourceHealthError}
                    icon={<ShieldCheck className="h-5 w-5 text-primary" />}
                    actionLabel="Retry"
                    onAction={() => void loadSourceHealthData()}
                  />
                ) : isSourceHealthLoading ? (
                  <EmptyState
                    title="Loading source health"
                    description="Fetching latest source health records..."
                    icon={<ShieldCheck className="h-5 w-5 text-primary" />}
                  />
                ) : !sourceHealthData?.items.length ? (
                  <EmptyState
                    title="No source health data yet"
                    description="The source health table is empty right now."
                    icon={<ShieldCheck className="h-5 w-5 text-primary" />}
                  />
                ) : (
                  <>
                    <div className="grid gap-4 md:grid-cols-4">
                      <MetricCard
                        label="Total Sources"
                        value={sourceHealthData.summary.total_sources}
                      />
                      <MetricCard
                        label="Healthy"
                        value={sourceHealthData.summary.healthy}
                        variant="success"
                        icon={CheckCircle2}
                      />
                      <MetricCard
                        label="Degraded"
                        value={sourceHealthData.summary.degraded}
                        variant="warning"
                      />
                      <MetricCard
                        label="Down"
                        value={sourceHealthData.summary.down}
                        variant="danger"
                        icon={XCircle}
                      />
                    </div>
                    <div className="overflow-x-auto rounded-xl border border-border">
                      <table className="min-w-full divide-y divide-border text-sm">
                        <thead className="bg-muted/60 text-left text-xs uppercase tracking-[0.18em] text-muted-foreground">
                          <tr>
                            <th className="px-4 py-3">Source</th>
                            <th className="px-4 py-3">Status</th>
                            <th className="px-4 py-3">Last Success</th>
                            <th className="px-4 py-3">Last Fetch</th>
                            <th className="px-4 py-3">Failures</th>
                            <th className="px-4 py-3">Last Error</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border bg-background/40">
                          {sourceHealthData.items.map((item) => (
                            <tr
                              key={item.source}
                              className="hover:bg-accent/50"
                            >
                              <td className="px-4 py-3 font-medium text-foreground">
                                {item.source}
                              </td>
                              <td className="px-4 py-3">
                                <SourceStatusBadge status={item.status} />
                              </td>
                              <td className="px-4 py-3 text-muted-foreground">
                                {item.last_success}
                              </td>
                              <td className="px-4 py-3 text-muted-foreground">
                                {item.last_fetch}
                              </td>
                              <td className="px-4 py-3 text-muted-foreground">
                                {item.failures}
                              </td>
                              <td className="px-4 py-3 text-muted-foreground">
                                {item.last_error || "-"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-foreground">
                    {scheduleLogsData?.summary.total_runs ?? 0} runs
                  </h2>
                </div>

                {scheduleLogsError ? (
                  <EmptyState
                    title="Schedule logs load failed"
                    description={scheduleLogsError}
                    icon={<Activity className="h-5 w-5 text-primary" />}
                    actionLabel="Retry"
                    onAction={() => void loadScheduleLogsData()}
                  />
                ) : isScheduleLogsLoading ? (
                  <EmptyState
                    title="Loading schedule logs"
                    description="Fetching recent scheduler runs..."
                    icon={<Activity className="h-5 w-5 text-primary" />}
                  />
                ) : !scheduleLogsData?.items.length ? (
                  <EmptyState
                    title="No schedule logs yet"
                    description="The schedule log table is empty right now."
                    icon={<Activity className="h-5 w-5 text-primary" />}
                  />
                ) : (
                  <>
                    <div className="grid gap-4 md:grid-cols-4">
                      <MetricCard
                        label="Total Runs"
                        value={scheduleLogsData.summary.total_runs}
                        icon={Activity}
                      />
                      <MetricCard
                        label="Success"
                        value={scheduleLogsData.summary.success}
                        variant="success"
                        icon={CheckCircle2}
                      />
                      <MetricCard
                        label="Failed"
                        value={scheduleLogsData.summary.failed}
                        variant="danger"
                        icon={XCircle}
                      />
                      <MetricCard
                        label="Running"
                        value={scheduleLogsData.summary.running}
                        variant="warning"
                        icon={CircleDashed}
                      />
                    </div>
                    <div className="overflow-x-auto rounded-xl border border-border">
                      <table className="min-w-full divide-y divide-border text-sm">
                        <thead className="bg-muted/60 text-left text-xs uppercase tracking-[0.18em] text-muted-foreground">
                          <tr>
                            <th className="px-4 py-3">Job</th>
                            <th className="px-4 py-3">Status</th>
                            <th className="px-4 py-3">Started</th>
                            <th className="px-4 py-3">Fetched</th>
                            <th className="px-4 py-3">New</th>
                            <th className="px-4 py-3">Deduped</th>
                            <th className="px-4 py-3">Verified</th>
                            <th className="px-4 py-3">Error</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border bg-background/40">
                          {scheduleLogsData.items.map((item) => (
                            <tr key={item.id} className="hover:bg-accent/50">
                              <td className="px-4 py-3 font-medium text-foreground">
                                {item.job}
                              </td>
                              <td className="px-4 py-3">
                                <SourceStatusBadge status={item.status} />
                              </td>
                              <td className="px-4 py-3 text-muted-foreground">
                                {item.started}
                              </td>
                              <td className="px-4 py-3 text-muted-foreground">
                                {item.fetched}
                              </td>
                              <td className="px-4 py-3 text-muted-foreground">
                                {item.new}
                              </td>
                              <td className="px-4 py-3 text-muted-foreground">
                                {item.deduped}
                              </td>
                              <td className="px-4 py-3 text-muted-foreground">
                                {item.verified}
                              </td>
                              <td className="px-4 py-3 text-muted-foreground">
                                {item.error || "-"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <div ref={resultsSectionRef}>
          <ResultPanels
            data={result}
            investigation={investigation}
            isRunning={verifyingEventId !== null}
            isInvestigating={isInvestigating}
          />
        </div>
      </div>
      <CopilotDrawer
        open={isCopilotOpen}
        opportunity={selectedOpportunity}
        onClose={() => setIsCopilotOpen(false)}
      />
    </main>
  );
}

function SourceStatusBadge({ status }: { status: string }) {
  const s = status.toLowerCase();
  const variant =
    s === "healthy"
      ? ("success" as const)
      : s === "degraded"
        ? ("warning" as const)
        : ("danger" as const);
  const colors = {
    success: "bg-emerald-100 text-emerald-700",
    warning: "bg-amber-100 text-amber-700",
    danger: "bg-rose-100 text-rose-700",
  };
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${colors[variant]}`}
    >
      {status}
    </span>
  );
}

function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  variant = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  icon?: React.ComponentType<{ className?: string }>;
  variant?: "default" | "success" | "warning" | "danger";
}) {
  const variantStyles = {
    default: "",
    success: "border-l-[3px] border-l-emerald-500",
    warning: "border-l-[3px] border-l-amber-500",
    danger: "border-l-[3px] border-l-rose-500",
  };

  const iconVariantStyles = {
    default: "text-muted-foreground",
    success: "text-emerald-500",
    warning: "text-amber-500",
    danger: "text-rose-500",
  };

  return (
    <Card
      className={`group border-border/70 bg-card/95 shadow-sm transition-shadow hover:shadow-md ${variantStyles[variant]}`}
    >
      <CardContent className="px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-medium uppercase tracking-[0.1em] text-muted-foreground">
            {label}
          </p>
          {Icon ? (
            <Icon className={`h-4 w-4 ${iconVariantStyles[variant]}`} />
          ) : null}
        </div>
        <p className="mt-1 text-xl font-semibold tracking-[-0.03em] tabular-nums">
          {value}
        </p>
        {hint ? (
          <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

function EmptyState({
  title,
  description,
  icon,
  actionLabel,
  onAction,
}: {
  title: string;
  description: string;
  icon?: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-background/70 p-6 text-sm text-muted-foreground">
      <div className="flex items-center gap-2 text-foreground">
        {icon}
        <span className="font-medium">{title}</span>
      </div>
      <p className="mt-2">{description}</p>
      {actionLabel && onAction ? (
        <Button className="mt-4" variant="outline" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </div>
  );
}
