"use client";

import { ExternalLink } from "lucide-react";

import { StatusDot } from "@/components/ui/badge";
import { MonoLabel, ValueStrip } from "@/components/ui/mono-label";
import { Skeleton } from "@/components/ui/skeleton";
import { copy } from "@/lib/copy";
import { formatDate, formatScore } from "@/lib/format";
import type { DashboardOpportunityDetail, DashboardOpportunityItem } from "@/types/chat";

export function OverviewTab({
  item,
  detail,
  loading,
}: {
  item: DashboardOpportunityItem;
  detail: DashboardOpportunityDetail | undefined;
  loading: boolean;
}) {
  const scores = [
    { label: copy.detail.overview.roi, value: item.scores.roi },
    { label: copy.detail.overview.reputation, value: item.scores.reputation },
    { label: copy.detail.overview.timeliness, value: item.scores.timeliness },
    { label: copy.detail.overview.strategy, value: item.scores.strategy },
  ];

  return (
    <div className="space-y-5">
      <section>
        <MonoLabel as="h3" className="mb-1.5">{copy.detail.overview.summary}</MonoLabel>
        {loading && !detail ? (
          <div className="space-y-1.5">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-5/6" />
          </div>
        ) : (
          <p className="text-[0.8125rem] leading-relaxed whitespace-pre-line text-ink">
            {detail?.description || item.summary || copy.detail.overview.noDescription}
          </p>
        )}
      </section>

      <section>
        <MonoLabel as="h3" className="mb-1.5">{copy.detail.overview.scores}</MonoLabel>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {scores.map((score) => (
            <ValueStrip key={score.label} label={score.label}>
              {formatScore(score.value)}
            </ValueStrip>
          ))}
        </div>
      </section>

      <section>
        <MonoLabel as="h3" className="mb-1.5">{copy.detail.overview.sources}</MonoLabel>
        {loading && !detail ? (
          <Skeleton className="h-4 w-2/3" />
        ) : detail?.sources.length ? (
          <ul className="space-y-1">
            {detail.sources.map((source, index) => (
              <li key={`${source.name}-${index}`} className="flex items-center gap-2 text-[0.8125rem]">
                <StatusDot tone={item.source_trust === "official" && index === 0 ? "success" : "neutral"} />
                {source.url ? (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex min-w-0 items-center gap-1 font-mono text-[12px] text-ink underline decoration-ink/25 underline-offset-[3px] hover:decoration-ink"
                  >
                    <span className="truncate">{source.name}</span>
                    <ExternalLink aria-hidden className="size-3 shrink-0" />
                  </a>
                ) : (
                  <span className="truncate font-mono text-[12px] text-ink">{source.name}</span>
                )}
                <span className="shrink-0 text-[11px] text-ink-mute">· {formatDate(source.fetched_at)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[0.8125rem] text-ink-mute">{copy.detail.overview.noSources}</p>
        )}
      </section>
    </div>
  );
}
