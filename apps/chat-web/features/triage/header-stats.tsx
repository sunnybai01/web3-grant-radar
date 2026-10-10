"use client";

import { MonoLabel } from "@/components/ui/mono-label";
import { Skeleton } from "@/components/ui/skeleton";
import { copy } from "@/lib/copy";
import { cn } from "@/lib/utils";
import type { DashboardOpportunityMetrics, OpportunityFilters } from "@/types/chat";

type Stat = {
  label: string;
  value: string;
  danger?: boolean;
  active?: boolean;
  title?: string;
  onClick?: () => void;
};

/** Whole-board stats. Clicking one applies it as a filter. */
export function HeaderStats({
  metrics,
  filters,
  onFilter,
}: {
  metrics: DashboardOpportunityMetrics | undefined;
  filters: OpportunityFilters;
  onFilter: (patch: Partial<OpportunityFilters>) => void;
}) {
  if (!metrics) {
    return <Skeleton className="h-[58px] w-full max-w-[420px] rounded-xl" />;
  }

  const stats: Stat[] = [
    {
      label: copy.triage.stats.toReview,
      value: String(metrics.to_review),
      active: filters.status === "new" && !filters.closingSoon,
      onClick: () => onFilter({ status: "new", closingSoon: false }),
    },
    {
      label: copy.triage.stats.shortlisted,
      value: String(metrics.shortlisted),
      active: filters.status === "shortlisted" && !filters.closingSoon,
      onClick: () => onFilter({ status: "shortlisted", closingSoon: false }),
    },
    {
      label: copy.triage.stats.closingSoon,
      value: String(metrics.closing_soon),
      danger: metrics.closing_soon > 0,
      active: filters.closingSoon,
      onClick: () => onFilter({ closingSoon: !filters.closingSoon, status: "all", sort: "deadline" }),
    },
    {
      label: copy.triage.stats.verified,
      value: `${metrics.verified_percent}%`,
      title: `${metrics.verified_count} verified · ${metrics.unchecked_count} unchecked of ${metrics.total}`,
    },
  ];

  return (
    <div className="grid grid-cols-2 overflow-hidden rounded-xl border border-line bg-surface shadow-panel sm:flex">
      {stats.map((stat) => {
        const body = (
          <>
            <MonoLabel>{stat.label}</MonoLabel>
            <span
              className={cn(
                "mt-1 block font-mono text-lg leading-none font-semibold tabular-nums",
                stat.danger ? "text-danger" : "text-ink"
              )}
            >
              {stat.value}
            </span>
          </>
        );
        const base = "flex flex-col items-start px-4 py-2.5 text-left sm:border-l sm:first:border-l-0";
        return stat.onClick ? (
          <button
            key={stat.label}
            type="button"
            onClick={stat.onClick}
            aria-pressed={stat.active}
            className={cn(base, "transition-colors hover:bg-surface-hover", stat.active && "bg-yellow-pale")}
          >
            {body}
          </button>
        ) : (
          <div key={stat.label} className={base} title={stat.title}>
            {body}
          </div>
        );
      })}
    </div>
  );
}
