"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Eyebrow } from "@/components/ui/mono-label";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { client, errorMessage } from "@/lib/client";
import { copy } from "@/lib/copy";
import { formatDateTime, formatRelative } from "@/lib/format";
import { summarizeManualScan } from "@/lib/manual-scan";
import { queryKeys, useManualScan, useScheduleLogs, useSourceHealth, useStartScan } from "@/lib/queries";
import { capitalize, runTone, sourceHealthTone } from "@/lib/status-tone";
import { cn } from "@/lib/utils";
import type { ManualScanStatusResponse } from "@/types/chat";

export function OperationsPage() {
  return (
    <main className="mx-auto w-full max-w-[1120px] px-4 pt-6 pb-16 md:px-8">
      <Eyebrow>{copy.operations.eyebrow}</Eyebrow>
      <h1 className="mt-1 text-[1.6rem] leading-tight font-bold tracking-tight text-ink">{copy.operations.title}</h1>
      <p className="mt-1 max-w-[70ch] text-[0.875rem] text-ink-body">{copy.operations.description}</p>

      <div className="mt-6 space-y-5">
        <ScanPanel />
        <SourcesPanel />
        <RunsPanel />
        <MaintenancePanel />
      </div>
    </main>
  );
}

// --- Manual scan -------------------------------------------------------------

function useElapsed(startedAt: string | undefined, running: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  if (!startedAt || !running) return null;
  const seconds = Math.max(0, Math.round((now - new Date(startedAt).getTime()) / 1000));
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
}

type StepState = "done" | "current" | "todo";

function scanSteps(scan: ManualScanStatusResponse | undefined): { label: string; state: StepState }[] {
  const running = scan?.status === "running";
  const finished = Boolean(scan?.triggered) && !running && Boolean(scan?.status);
  return [
    { label: copy.operations.scan.steps.queued, state: running || finished ? "done" : "todo" },
    { label: copy.operations.scan.steps.running, state: running ? "current" : finished ? "done" : "todo" },
    { label: copy.operations.scan.steps.done, state: finished ? "done" : "todo" },
  ];
}

function ScanPanel() {
  const scan = useManualScan();
  const start = useStartScan();
  const data = scan.data;
  const running = data?.status === "running";
  const elapsed = useElapsed(data?.started_at, running);
  const totals = summarizeManualScan(data ?? null);
  const hasRun = Boolean(data?.triggered || data?.started_at);

  return (
    <Panel className="p-5">
      <PanelHeader
        title={copy.operations.scan.title}
        description={copy.operations.scan.description}
        actions={
          <Button
            size="sm"
            pillIcon={running ? undefined : "↻"}
            loading={start.isPending || running}
            onClick={() =>
              start.mutate(undefined, {
                onSuccess: () => toast(copy.scan.started),
                onError: (error) => toast.error(copy.scan.failed, { description: errorMessage(error, "") || undefined }),
              })
            }
          >
            {running ? copy.scan.running(capitalize(data?.current_stage || "scan")) : copy.scan.run}
          </Button>
        }
      />

      {scan.isLoading ? (
        <Skeleton className="mt-4 h-10 w-full" />
      ) : !hasRun ? (
        <p className="mt-4 text-[0.8125rem] text-ink-mute">{copy.operations.scan.idle}</p>
      ) : (
        <>
          <ol className="mt-4 flex items-center gap-2">
            {scanSteps(data).map((step, index, steps) => (
              <li key={step.label} className={cn("flex items-center gap-2", index < steps.length - 1 && "flex-1")}>
                <span
                  className={cn(
                    "inline-flex size-[26px] shrink-0 items-center justify-center rounded-full border-[1.5px] font-mono text-[10px]",
                    step.state === "done" && "border-yellow bg-yellow font-bold text-ink",
                    step.state === "current" && "border-ink font-bold text-ink",
                    step.state === "todo" && "border-line-strong text-ink-mute"
                  )}
                >
                  {step.state === "done" ? "✓" : String(index + 1).padStart(2, "0")}
                </span>
                <span className={cn("text-[0.8125rem]", step.state === "todo" ? "text-ink-mute" : "font-semibold text-ink")}>
                  {step.label}
                  {step.state === "current" && elapsed ? (
                    <span className="ml-1.5 font-mono text-[11px] font-normal text-ink-mute">
                      {copy.operations.scan.elapsed(elapsed)}
                    </span>
                  ) : null}
                </span>
                {index < steps.length - 1 ? (
                  <span aria-hidden className={cn("h-0.5 flex-1 rounded", step.state === "done" ? "bg-yellow" : "bg-line")} />
                ) : null}
              </li>
            ))}
          </ol>

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {data?.status && data.status !== "running" ? (
              <Badge tone={runTone(data.status)}>{data.status}</Badge>
            ) : null}
            <span className="rounded-md bg-surface-alt px-2.5 py-1.5 font-mono text-[11.5px] text-ink-body tabular-nums">
              fetched {totals.fetched} · new {totals.new} · deduped {totals.deduped} · classified {totals.classified} ·
              verified {totals.verified} · pushed {totals.pushed}
            </span>
            {data?.finished_at ? (
              <span className="font-mono text-[11px] text-ink-mute">{formatRelative(data.finished_at)}</span>
            ) : null}
          </div>
          {data?.error ? (
            <p className="mt-2 font-mono text-[11.5px] text-danger">reason: {data.error}</p>
          ) : null}
        </>
      )}
    </Panel>
  );
}

// --- Sources -----------------------------------------------------------------

function TableError({ title, error, onRetry }: { title: string; error: unknown; onRetry: () => void }) {
  return (
    <div role="alert" className="mt-4 rounded-lg border-[1.5px] border-danger/45 bg-danger-surface p-3.5">
      <p className="text-[0.875rem] font-semibold text-danger">{title}</p>
      <p className="mt-0.5 font-mono text-[11px] text-ink-body">reason: {errorMessage(error, "unknown error")}</p>
      <Button size="sm" variant="link" className="mt-2" onClick={onRetry}>
        {copy.triage.retry}
      </Button>
    </div>
  );
}

function SourcesPanel() {
  const health = useSourceHealth();
  const [view, setView] = useState<"problems" | "all">("problems");
  const items = health.data?.items ?? [];
  const problems = items.filter((item) => item.status.toLowerCase() !== "healthy");
  const rows = view === "problems" ? problems : items;
  const t = copy.operations.sources;

  return (
    <Panel className="p-5">
      <PanelHeader
        title={t.title}
        description={health.data ? t.description(health.data.summary.total_sources) : undefined}
        actions={
          <SegmentedControl
            label={t.title}
            value={view}
            onChange={setView}
            options={[
              { value: "problems", label: t.problems, count: problems.length },
              { value: "all", label: t.all, count: items.length },
            ]}
          />
        }
      />
      {health.error ? (
        <TableError title={t.loadError} error={health.error} onRetry={() => void health.refetch()} />
      ) : health.isLoading ? (
        <Skeleton className="mt-4 h-24 w-full" />
      ) : rows.length === 0 ? (
        <p className="mt-4 text-[0.8125rem] text-ink-mute">{items.length ? t.noProblems : t.empty}</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-[0.8125rem]">
            <thead>
              <tr>
                {[t.columns.source, t.columns.status, t.columns.lastSuccess, t.columns.failures, t.columns.lastError].map((label) => (
                  <th key={label} scope="col" className="px-2 py-1.5 font-mono text-[10px] font-normal tracking-[0.12em] text-ink-mute uppercase">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.source} className="border-t border-line">
                  <td className="px-2 py-2 font-mono text-[12px] text-ink">{item.source}</td>
                  <td className="px-2 py-2">
                    <Badge tone={sourceHealthTone(item.status)}>{item.status}</Badge>
                  </td>
                  <td className="px-2 py-2 font-mono text-[12px] text-ink-body" title={item.last_success}>
                    {formatRelative(item.last_success_at)}
                  </td>
                  <td className="px-2 py-2 font-mono text-[12px] text-ink-body tabular-nums">{item.failures}</td>
                  <td className="max-w-[280px] truncate px-2 py-2 font-mono text-[12px] text-ink-body" title={item.last_error}>
                    {item.last_error || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// --- Recent runs -------------------------------------------------------------

function RunsPanel() {
  const logs = useScheduleLogs();
  const t = copy.operations.runs;
  const rows = (logs.data?.items ?? []).slice(0, 15);

  return (
    <Panel className="p-5">
      <PanelHeader title={t.title} />
      {logs.error ? (
        <TableError title={t.loadError} error={logs.error} onRetry={() => void logs.refetch()} />
      ) : logs.isLoading ? (
        <Skeleton className="mt-4 h-24 w-full" />
      ) : rows.length === 0 ? (
        <p className="mt-4 text-[0.8125rem] text-ink-mute">{t.empty}</p>
      ) : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-[0.8125rem]">
            <thead>
              <tr>
                {[t.columns.job, t.columns.status, t.columns.started, t.columns.flow, t.columns.error].map((label) => (
                  <th key={label} scope="col" className="px-2 py-1.5 font-mono text-[10px] font-normal tracking-[0.12em] text-ink-mute uppercase">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.id} className="border-t border-line">
                  <td className="px-2 py-2 font-mono text-[12px] text-ink">{item.job.replace(/^pipeline_/, "")}</td>
                  <td className="px-2 py-2">
                    <Badge tone={runTone(item.status)}>{item.status}</Badge>
                  </td>
                  <td className="px-2 py-2 font-mono text-[12px] text-ink-body" title={formatRelative(item.started_at)}>
                    {formatDateTime(item.started_at)}
                  </td>
                  <td className="px-2 py-2 font-mono text-[12px] text-ink-body tabular-nums">
                    {item.fetched} → {item.new} → {item.verified}
                  </td>
                  <td className="max-w-[260px] truncate px-2 py-2 font-mono text-[12px] text-ink-body" title={item.error}>
                    {item.error || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// --- Maintenance -------------------------------------------------------------

function MaintenanceRow({
  title,
  description,
  danger = false,
  action,
}: {
  title: string;
  description: string;
  danger?: boolean;
  action: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3 border-t border-line py-4 first:border-t-0 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="text-[0.875rem] font-semibold text-ink">{title}</p>
        <p className={cn("mt-0.5 text-[0.8125rem]", danger ? "text-danger" : "text-ink-body")}>{description}</p>
      </div>
      <div className="shrink-0">{action}</div>
    </div>
  );
}

function MaintenancePanel() {
  const queryClient = useQueryClient();
  const [confirmReset, setConfirmReset] = useState(false);
  const t = copy.operations.maintenance;

  const summary = useMutation({
    mutationFn: client.sendDailySummary,
    onSuccess: (data) =>
      data.status === "failed" || data.error
        ? toast.error(t.summary.failed, { description: data.error || undefined })
        : toast.success(t.summary.done),
    onError: (error) => toast.error(t.summary.failed, { description: errorMessage(error, "") || undefined }),
  });

  const tavily = useMutation({
    mutationFn: client.unlockTavily,
    onSuccess: (data) => {
      toast.success(data.message || `Unlocked ${data.unlocked_count} source(s).`);
      void queryClient.invalidateQueries({ queryKey: queryKeys.sourceHealth });
    },
    onError: (error) => toast.error(t.tavily.failed, { description: errorMessage(error, "") || undefined }),
  });

  const reset = useMutation({
    mutationFn: client.resetDedup,
    onSuccess: (data) => {
      setConfirmReset(false);
      if (data.status === "failed" || data.error) {
        toast.error(t.dedup.failed, { description: data.error || undefined });
      } else {
        toast.success(data.message);
      }
    },
    onError: (error) => toast.error(t.dedup.failed, { description: errorMessage(error, "") || undefined }),
  });

  return (
    <Panel className="p-5">
      <PanelHeader title={t.title} className="mb-4" />
      <MaintenanceRow
        title={t.summary.title}
        description={t.summary.description}
        action={
          <Button size="sm" variant="outline" loading={summary.isPending} onClick={() => summary.mutate()}>
            {t.summary.action}
          </Button>
        }
      />
      <MaintenanceRow
        title={t.tavily.title}
        description={t.tavily.description}
        action={
          <Button size="sm" variant="outline" loading={tavily.isPending} onClick={() => tavily.mutate()}>
            {t.tavily.action}
          </Button>
        }
      />
      <MaintenanceRow
        title={t.dedup.title}
        description={t.dedup.description}
        danger
        action={
          <Button size="sm" variant="danger" pillIcon="!" onClick={() => setConfirmReset(true)}>
            {t.dedup.action}
          </Button>
        }
      />

      <Dialog open={confirmReset} onOpenChange={setConfirmReset}>
        <DialogContent>
          <DialogTitle className="text-[1.05rem] font-semibold text-ink">{t.dedup.confirmTitle}</DialogTitle>
          <DialogDescription className="mt-2 text-[0.8125rem] leading-relaxed text-ink-body">
            {t.dedup.confirmBody}
          </DialogDescription>
          <div className="mt-5 flex items-center justify-end gap-3">
            <DialogClose asChild>
              <Button variant="link">{copy.deleteDialog.cancel}</Button>
            </DialogClose>
            <Button variant="danger" pillIcon="!" loading={reset.isPending} onClick={() => reset.mutate()}>
              {t.dedup.confirm}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Panel>
  );
}
