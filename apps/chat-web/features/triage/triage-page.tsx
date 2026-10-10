"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Dialog, SheetContent } from "@/components/ui/dialog";
import { Eyebrow } from "@/components/ui/mono-label";
import { Panel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { copy } from "@/lib/copy";
import { queryKeys, useArrivalsProbe, useOpportunities, useOpportunity } from "@/lib/queries";
import { stepSelection } from "@/lib/triage-state";
import type { DashboardOpportunityItem } from "@/types/chat";

import { useCopilotTools } from "../copilot/use-copilot-tools";
import { HeaderStats } from "./header-stats";
import { OpportunityDetail } from "./opportunity-detail";
import { OpportunityList } from "./opportunity-list";
import { useTriageActions } from "./use-triage-actions";
import { useTriageKeyboard } from "./use-triage-keyboard";
import { useTriageView } from "./use-triage-view";

const DESKTOP_QUERY = "(min-width: 1024px)";

function useIsDesktop() {
  const [desktop, setDesktop] = useState(true);
  useEffect(() => {
    const media = window.matchMedia(DESKTOP_QUERY);
    const update = () => setDesktop(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return desktop;
}

/** Ids already on screen at least once; anything else in the New probe is an arrival. */
function useArrivals(visibleIds: number[]) {
  const probe = useArrivalsProbe();
  const seen = useRef<Set<number> | null>(null);
  const [, bump] = useState(0);

  if (probe.data && seen.current === null) seen.current = new Set(probe.data.items.map((item) => item.id));
  visibleIds.forEach((id) => seen.current?.add(id));

  const unseen = (probe.data?.items ?? []).filter((item) => !seen.current?.has(item.id));
  const acknowledge = useCallback(() => {
    probe.data?.items.forEach((item) => seen.current?.add(item.id));
    bump((value) => value + 1);
  }, [probe.data]);

  return { count: unseen.length, acknowledge };
}

export function TriagePage() {
  const queryClient = useQueryClient();
  const isDesktop = useIsDesktop();
  const { filters, selectedId, setFilters, setSelectedId } = useTriageView();
  const listing = useOpportunities(filters);
  const items = useMemo(() => listing.data?.items ?? [], [listing.data]);
  const [sheetOpen, setSheetOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  const inList = items.find((item) => item.id === selectedId) ?? null;
  // A selection from the URL may sit on another tab: load it on its own.
  const outside = useOpportunity(inList || listing.isLoading ? null : selectedId);
  const selected: DashboardOpportunityItem | null = inList ?? outside.data ?? null;

  // On desktop something is always selected once the list has rows.
  useEffect(() => {
    if (!isDesktop || !listing.data || listing.isPlaceholderData) return;
    const missing = selectedId === null || (!inList && (outside.isError || (!outside.isLoading && !outside.data)));
    if (missing && items.length) setSelectedId(items[0].id);
  }, [isDesktop, listing.data, listing.isPlaceholderData, selectedId, inList, outside.isError, outside.isLoading, outside.data, items, setSelectedId]);

  const arrivals = useArrivals(items.map((item) => item.id));
  const { triage, undo, remove, pendingId } = useTriageActions({ filters, items, setSelectedId });

  useCopilotTools({ filters, listing: listing.data, selected });

  const select = useCallback(
    (id: number) => {
      setSelectedId(id);
      if (!isDesktop) setSheetOpen(true);
    },
    [isDesktop, setSelectedId]
  );

  useTriageKeyboard({
    next: () => setSelectedId(stepSelection(items.map((item) => item.id), selectedId, 1)),
    previous: () => setSelectedId(stepSelection(items.map((item) => item.id), selectedId, -1)),
    shortlist: () => selected && void triage(selected, "shortlisted"),
    dismiss: () => selected && void triage(selected, "dismissed"),
    undo: () => void undo(),
    open: () => selected?.apply_url && window.open(selected.apply_url, "_blank", "noopener,noreferrer"),
    search: () => searchRef.current?.focus(),
  });

  const showArrivals = () => {
    arrivals.acknowledge();
    void queryClient.invalidateQueries({ queryKey: queryKeys.opportunitiesRoot });
  };

  const detail = selected ? (
    <OpportunityDetail
      item={selected}
      pending={pendingId === selected.id}
      onTriage={(status) => void triage(selected, status)}
      onDelete={async () => {
        const ok = await remove(selected);
        if (ok) setSheetOpen(false);
        return ok;
      }}
    />
  ) : null;

  return (
    // On desktop the page fits the viewport below the 57px top bar: the list and
    // the detail scroll on their own instead of the whole page scrolling.
    <main className="mx-auto w-full max-w-[1440px] px-4 pt-6 pb-10 md:px-8 lg:flex lg:h-[calc(100dvh-57px)] lg:flex-col lg:pb-6">
      <div className="mb-5 flex shrink-0 flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <Eyebrow>{copy.triage.eyebrow}</Eyebrow>
          <h1 className="mt-1 text-[1.6rem] leading-tight font-bold tracking-tight text-ink">{copy.triage.title}</h1>
          <p className="mt-1 max-w-[70ch] text-[0.875rem] text-ink-body">{copy.triage.description}</p>
        </div>
        <HeaderStats metrics={listing.data?.metrics} filters={filters} onFilter={setFilters} />
      </div>

      <div className="grid gap-4 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="lg:flex lg:min-h-0 lg:flex-col">
          <OpportunityList
            ref={searchRef}
            data={listing.data}
            isLoading={listing.isLoading}
            isFetching={listing.isFetching}
            error={listing.error}
            onRetry={() => void listing.refetch()}
            filters={filters}
            onFilter={setFilters}
            selectedId={selectedId}
            onSelect={select}
            arrivals={arrivals.count}
            onShowArrivals={showArrivals}
          />
        </div>

        {isDesktop ? (
          <Panel className="p-5 lg:min-h-0 lg:overflow-y-auto">
            {detail ??
              (listing.isLoading ? (
                <div className="space-y-3">
                  <Skeleton className="h-3 w-1/3" />
                  <Skeleton className="h-6 w-2/3" />
                  <Skeleton className="h-24 w-full" />
                </div>
              ) : (
                <p className="py-16 text-center text-[0.875rem] text-ink-mute">{copy.triage.selectPrompt}</p>
              ))}
          </Panel>
        ) : (
          <Dialog open={sheetOpen && Boolean(selected)} onOpenChange={setSheetOpen}>
            <SheetContent title={selected?.title ?? copy.triage.title}>
              <Panel className="p-4">{detail}</Panel>
            </SheetContent>
          </Dialog>
        )}
      </div>
    </main>
  );
}
