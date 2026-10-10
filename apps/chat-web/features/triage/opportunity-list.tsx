"use client";

import { Search } from "lucide-react";
import { forwardRef, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, SelectChip } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { Panel } from "@/components/ui/panel";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { copy } from "@/lib/copy";
import { describeDeadline, formatAmount, formatChain, formatClock, formatScore, formatType } from "@/lib/format";
import { verificationLabel, verificationTone } from "@/lib/status-tone";
import { hasActiveFilters } from "@/lib/triage-state";
import { cn } from "@/lib/utils";
import type {
  DashboardOpportunitiesResponse,
  DashboardOpportunityItem,
  OpportunityFilters,
  TriageTab,
} from "@/types/chat";

type ListProps = {
  data: DashboardOpportunitiesResponse | undefined;
  isLoading: boolean;
  isFetching: boolean;
  error: unknown;
  onRetry: () => void;
  filters: OpportunityFilters;
  onFilter: (patch: Partial<OpportunityFilters>) => void;
  selectedId: number | null;
  onSelect: (id: number) => void;
  arrivals: number;
  onShowArrivals: () => void;
};

const SEARCH_DEBOUNCE_MS = 250;

export const OpportunityList = forwardRef<HTMLInputElement, ListProps>(function OpportunityList(
  { data, isLoading, isFetching, error, onRetry, filters, onFilter, selectedId, onSelect, arrivals, onShowArrivals },
  searchRef
) {
  const [query, setQuery] = useState(filters.q);
  const selectedRef = useRef<HTMLButtonElement | null>(null);

  // Follow outside changes to the query, e.g. "Clear filters".
  useEffect(() => {
    setQuery(filters.q);
  }, [filters.q]);

  useEffect(() => {
    if (query === filters.q) return;
    const timer = window.setTimeout(() => onFilter({ q: query }), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query, filters.q, onFilter]);

  // Keep the keyboard selection in view.
  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  const counts = data?.counts;
  const tabs = (["new", "shortlisted", "dismissed", "all"] as TriageTab[]).map((value) => ({
    value,
    label: copy.triage.tabs[value],
    count: counts?.[value],
  }));

  return (
    <Panel className="flex min-h-0 flex-col p-3 md:p-4" aria-busy={isFetching}>
      <div className="flex flex-wrap items-center gap-2">
        <SegmentedControl
          label={copy.triage.listLabel}
          options={tabs}
          value={filters.status}
          onChange={(status) => onFilter({ status })}
        />
        <label className="relative min-w-[160px] flex-1">
          <span className="sr-only">{copy.triage.searchPlaceholder}</span>
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-ink-mute" />
          <Input
            ref={searchRef}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape") (event.target as HTMLInputElement).blur();
            }}
            placeholder={copy.triage.searchPlaceholder}
            className="pl-8"
          />
        </label>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        <SelectChip
          label={copy.triage.filters.type}
          value={filters.type}
          onChange={(event) => onFilter({ type: event.target.value as OpportunityFilters["type"] })}
        >
          <option value="all">{copy.triage.filters.all}</option>
          <option value="grant">{copy.triage.filters.grant}</option>
          <option value="hackathon">{copy.triage.filters.hackathon}</option>
        </SelectChip>
        <SelectChip
          label={copy.triage.filters.source}
          value={filters.trust}
          onChange={(event) => onFilter({ trust: event.target.value as OpportunityFilters["trust"] })}
        >
          <option value="all">{copy.triage.filters.all}</option>
          <option value="official">{copy.triage.filters.official}</option>
          <option value="discovery">{copy.triage.filters.discovery}</option>
        </SelectChip>
        <SelectChip
          label={copy.triage.filters.chain}
          value={filters.ecosystem}
          onChange={(event) => onFilter({ ecosystem: event.target.value })}
        >
          <option value="">{copy.triage.filters.all}</option>
          {(data?.ecosystems ?? []).map((chain) => (
            <option key={chain} value={chain}>
              {chain}
            </option>
          ))}
        </SelectChip>
        {filters.closingSoon ? (
          <button
            type="button"
            onClick={() => onFilter({ closingSoon: false })}
            className="inline-flex h-8 items-center gap-1 rounded-md border border-danger/40 bg-danger-surface px-2.5 font-mono text-[11px] text-danger uppercase hover:bg-danger-badge"
          >
            {copy.triage.filters.closingSoon} ✕
          </button>
        ) : null}
        <span className="flex-1" />
        <SelectChip
          label={copy.triage.filters.sort}
          value={filters.sort}
          onChange={(event) => onFilter({ sort: event.target.value as OpportunityFilters["sort"] })}
        >
          <option value="score">{copy.triage.filters.score}</option>
          <option value="deadline">{copy.triage.filters.deadline}</option>
          <option value="newest">{copy.triage.filters.newest}</option>
        </SelectChip>
      </div>

      {arrivals > 0 ? (
        <div className="mt-2.5 flex items-center justify-between gap-2 rounded-lg border border-yellow bg-yellow-pale px-3 py-2 text-[0.8125rem]">
          <span>{copy.triage.newArrivals(arrivals)}</span>
          <Button size="sm" variant="link" onClick={onShowArrivals}>
            {copy.triage.showNew}
          </Button>
        </div>
      ) : null}

      <div className="mt-2.5 min-h-0 flex-1 overflow-y-auto rounded-lg bg-surface-alt p-1">
        {error && !data ? (
          <ListError error={error} onRetry={onRetry} />
        ) : isLoading ? (
          <ListSkeleton />
        ) : data && data.items.length === 0 ? (
          <ListEmpty filters={filters} nextScanAt={data.next_scan_at} onClear={() => onFilter(CLEARED)} />
        ) : (
          <div role="listbox" aria-label={copy.triage.title} className="flex flex-col gap-0.5">
            {data?.items.map((item) => (
              <OpportunityRow
                key={item.id}
                ref={item.id === selectedId ? selectedRef : undefined}
                item={item}
                selected={item.id === selectedId}
                showStatus={filters.status === "all"}
                onSelect={() => onSelect(item.id)}
              />
            ))}
          </div>
        )}
      </div>

      <div className="mt-2.5 hidden flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-mute lg:flex">
        <span><Kbd>J</Kbd> <Kbd>K</Kbd> {copy.triage.shortcuts.move}</span>
        <span><Kbd>S</Kbd> {copy.triage.shortcuts.shortlist}</span>
        <span><Kbd>D</Kbd> {copy.triage.shortcuts.dismiss}</span>
        <span><Kbd>Z</Kbd> {copy.triage.shortcuts.undo}</span>
        <span><Kbd>O</Kbd> {copy.triage.shortcuts.open}</span>
        <span><Kbd>/</Kbd> {copy.triage.shortcuts.search}</span>
      </div>
    </Panel>
  );
});

const CLEARED: Partial<OpportunityFilters> = {
  type: "all",
  trust: "all",
  ecosystem: "",
  q: "",
  closingSoon: false,
};

export const OpportunityRow = forwardRef<
  HTMLButtonElement,
  { item: DashboardOpportunityItem; selected: boolean; showStatus: boolean; onSelect: () => void }
>(function OpportunityRow({ item, selected, showStatus, onSelect }, ref) {
  const deadline = describeDeadline(item.deadline);
  return (
    <button
      ref={ref}
      type="button"
      role="option"
      aria-selected={selected}
      onClick={onSelect}
      className={cn(
        "grid w-full grid-cols-[2.5rem_minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2.5 py-2.5 text-left transition-colors",
        selected ? "bg-surface shadow-selected" : "hover:bg-surface"
      )}
    >
      <span className={cn("text-center font-mono text-[0.9rem] font-semibold tabular-nums", item.score === null && "text-ink-mute")}>
        {formatScore(item.score)}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[0.8125rem] font-semibold text-ink">{item.title}</span>
        <span className="mt-0.5 block truncate text-[11.5px] text-ink-mute">
          <span className="font-mono">{formatChain(item.ecosystem)}</span>
          {" · "}
          {formatType(item.type)}
          {" · "}
          {formatAmount(item.amount)}
          {" · "}
          <span
            title={deadline.exact ?? undefined}
            className={cn(
              deadline.state === "urgent" && "font-semibold text-danger",
              deadline.state === "closed" && "line-through"
            )}
          >
            {deadline.label}
          </span>
        </span>
      </span>
      <span className="flex flex-col items-end gap-1">
        <Badge tone={verificationTone(item.verification_verdict, item.verified)}>
          {verificationLabel(item.verification_verdict, item.verified)}
        </Badge>
        {showStatus && item.triage_status !== "new" ? (
          <Badge tone={item.triage_status === "shortlisted" ? "highlight" : "neutral"}>
            {copy.triage.tabs[item.triage_status]}
          </Badge>
        ) : null}
      </span>
    </button>
  );
});

function ListSkeleton() {
  return (
    <div className="flex flex-col gap-0.5" aria-label="Loading opportunities">
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className="grid grid-cols-[2.5rem_1fr_4rem] items-center gap-3 rounded-md bg-surface px-2.5 py-3">
          <Skeleton className="h-3.5" />
          <div className="space-y-1.5">
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-2.5 w-1/2" />
          </div>
          <Skeleton className="h-4 rounded-full" />
        </div>
      ))}
    </div>
  );
}

function ListEmpty({
  filters,
  nextScanAt,
  onClear,
}: {
  filters: OpportunityFilters;
  nextScanAt: string | null;
  onClear: () => void;
}) {
  const filtered = hasActiveFilters(filters);
  const clock = formatClock(nextScanAt);
  let title: string;
  let body: string | null = null;
  if (filtered) title = copy.triage.empty.filtered;
  else if (filters.status === "new") {
    title = copy.triage.empty.newCaughtUp;
    body = clock ? copy.triage.empty.nextScan(clock) : null;
  } else if (filters.status === "shortlisted") title = copy.triage.empty.shortlisted;
  else title = copy.triage.empty.dismissed;

  return (
    <div className="flex flex-col items-center gap-1.5 px-6 py-12 text-center">
      <p className="text-[0.875rem] font-semibold text-ink">{title}</p>
      {body ? <p className="text-[0.8125rem] text-ink-body">{body}</p> : null}
      {filtered ? (
        <Button size="sm" variant="link" onClick={onClear}>
          {copy.triage.filters.clear}
        </Button>
      ) : null}
    </div>
  );
}

function ListError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const reason = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="m-2 flex gap-3 rounded-lg border-[1.5px] border-danger/45 bg-danger-surface p-3.5">
      <span aria-hidden className="inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-danger text-[11px] font-bold text-surface">
        ✕
      </span>
      <div className="min-w-0">
        <p className="text-[0.875rem] font-semibold text-danger">{copy.triage.loadError}</p>
        <p className="mt-0.5 truncate font-mono text-[11px] text-ink-body">reason: {reason}</p>
        <Button size="sm" variant="link" className="mt-2" onClick={onRetry}>
          {copy.triage.retry}
        </Button>
      </div>
    </div>
  );
}
