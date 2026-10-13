"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/lib/client";
import { copy } from "@/lib/copy";
import { formatRelative } from "@/lib/format";
import { summarizeManualScan } from "@/lib/manual-scan";
import { queryKeys, useManualScan, useScheduleLogs, useStartScan } from "@/lib/queries";
import { capitalize } from "@/lib/status-tone";

import { StatusDot } from "../ui/badge";
import { Button } from "../ui/button";

/** Scan status line + "Run scan", shown in the top bar on every page. */
export function ScanControl() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const scan = useManualScan();
  const logs = useScheduleLogs();
  const start = useStartScan();
  const previousStatus = useRef<string | undefined>(undefined);

  const status = scan.data?.status;
  const running = status === "running";

  // Announce the end of a scan once, then refresh what depends on it.
  useEffect(() => {
    const before = previousStatus.current;
    previousStatus.current = status;
    if (before !== "running" || !status || status === "running") return;

    void queryClient.invalidateQueries({ queryKey: queryKeys.arrivals });
    void queryClient.invalidateQueries({ queryKey: queryKeys.scheduleLogs });
    void queryClient.invalidateQueries({ queryKey: queryKeys.sourceHealth });

    if (status === "failed") {
      toast.error(copy.scan.failed, { description: scan.data?.error || undefined });
      return;
    }
    const added = summarizeManualScan(scan.data ?? null).new;
    toast.success(copy.scan.finished(added), {
      action: { label: copy.scan.review, onClick: () => router.push("/triage") },
    });
  }, [status, scan.data, queryClient, router]);

  const onStart = () =>
    start.mutate(undefined, {
      onSuccess: () => toast(copy.scan.started),
      onError: (error) => toast.error(copy.scan.failed, { description: errorMessage(error, "") || undefined }),
    });

  const latestRun = logs.data?.items.find((item) => item.job.includes("grant_hackathon"));
  const label = running
    ? null
    : latestRun
      ? copy.scan.lastRun(formatRelative(latestRun.started_at), latestRun.new)
      : copy.scan.neverRun;

  return (
    <div className="flex items-center gap-3">
      {label ? (
        <span className="hidden items-center gap-1.5 font-mono text-[11px] text-ink-mute sm:inline-flex">
          <StatusDot tone={latestRun?.status === "failed" ? "danger" : latestRun ? "success" : "neutral"} />
          {label}
        </span>
      ) : null}
      <Button
        size="sm"
        onClick={onStart}
        loading={start.isPending || running}
        pillIcon={running ? undefined : "↻"}
      >
        {start.isPending
          ? copy.scan.starting
          : running
            ? copy.scan.running(capitalize(scan.data?.current_stage || "scan"))
            : copy.scan.run}
      </Button>
    </div>
  );
}
