"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import { client } from "@/lib/client";
import { copy } from "@/lib/copy";
import { applyTriage, removeFromListing } from "@/lib/listing-cache";
import { queryKeys } from "@/lib/queries";
import { belongsToTab, nextSelectionAfterRemoval } from "@/lib/triage-state";
import type {
  DashboardOpportunitiesResponse,
  DashboardOpportunityDetail,
  DashboardOpportunityItem,
  OpportunityFilters,
  TriageStatus,
} from "@/types/chat";

/** The row as it was before the decision, the status it got, and where it sat. */
type UndoEntry = { item: DashboardOpportunityItem; applied: TriageStatus; index: number };

const TOAST_FOR: Record<TriageStatus, (title: string) => string> = {
  new: copy.toasts.movedToNew,
  shortlisted: copy.toasts.shortlisted,
  dismissed: copy.toasts.dismissed,
};

/**
 * Triage decisions are applied to the cached list first, then saved. A failed
 * save puts the list back. Leaving the current tab moves the selection to the
 * next row so the user can keep going.
 */
export function useTriageActions({
  filters,
  items,
  setSelectedId,
}: {
  filters: OpportunityFilters;
  items: DashboardOpportunityItem[];
  setSelectedId: (id: number | null) => void;
}) {
  const queryClient = useQueryClient();
  const lastAction = useRef<UndoEntry | null>(null);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const listingKey = queryKeys.opportunities(filters);

  const patchDetail = useCallback(
    (id: number, status: TriageStatus) => {
      queryClient.setQueryData<DashboardOpportunityDetail>(queryKeys.opportunity(id), (detail) =>
        detail ? { ...detail, triage_status: status } : detail
      );
    },
    [queryClient]
  );

  const commit = useCallback(
    async (item: DashboardOpportunityItem, to: TriageStatus, index?: number) => {
      const previous = queryClient.getQueryData<DashboardOpportunitiesResponse>(listingKey);
      const ids = items.map((row) => row.id);
      const leaves = !belongsToTab(to, filters.status);

      if (previous) queryClient.setQueryData(listingKey, applyTriage(previous, filters.status, item, to, index));
      patchDetail(item.id, to);
      if (leaves) setSelectedId(nextSelectionAfterRemoval(ids, item.id));
      else setSelectedId(item.id);
      setPendingId(item.id);

      try {
        await client.triageOpportunity(item.id, to);
        // Other tabs and filter combinations now hold stale counts: refetch them
        // when they are next shown, but leave the visible list alone.
        void queryClient.invalidateQueries({
          queryKey: queryKeys.opportunitiesRoot,
          refetchType: "none",
          predicate: (query) => JSON.stringify(query.queryKey) !== JSON.stringify(listingKey),
        });
        void queryClient.invalidateQueries({ queryKey: queryKeys.arrivals });
        return true;
      } catch {
        if (previous) queryClient.setQueryData(listingKey, previous);
        patchDetail(item.id, item.triage_status);
        setSelectedId(item.id);
        toast.error(copy.toasts.triageFailed);
        return false;
      } finally {
        setPendingId(null);
      }
    },
    [queryClient, listingKey, items, filters.status, patchDetail, setSelectedId]
  );

  const undo = useCallback(async () => {
    const entry = lastAction.current;
    if (!entry) return;
    lastAction.current = null;
    const ok = await commit(
      { ...entry.item, triage_status: entry.applied },
      entry.item.triage_status,
      entry.index
    );
    if (ok) toast(copy.toasts.undone);
  }, [commit]);

  const triage = useCallback(
    async (item: DashboardOpportunityItem, to: TriageStatus) => {
      if (item.triage_status === to || pendingId === item.id) return;
      const index = items.findIndex((row) => row.id === item.id);
      const ok = await commit(item, to, index);
      if (!ok) return;
      lastAction.current = { item, applied: to, index };
      toast(TOAST_FOR[to](item.title), {
        action: { label: copy.toasts.undo, onClick: () => void undo() },
        duration: 6000,
      });
    },
    [commit, items, pendingId, undo]
  );

  const remove = useCallback(
    async (item: DashboardOpportunityItem) => {
      try {
        await client.deleteOpportunity(item.id);
      } catch {
        toast.error(copy.toasts.deleteFailed);
        return false;
      }
      const listing = queryClient.getQueryData<DashboardOpportunitiesResponse>(listingKey);
      if (listing) queryClient.setQueryData(listingKey, removeFromListing(listing, item.id));
      queryClient.removeQueries({ queryKey: queryKeys.opportunity(item.id) });
      setSelectedId(nextSelectionAfterRemoval(items.map((row) => row.id), item.id));
      if (lastAction.current?.item.id === item.id) lastAction.current = null;
      toast(copy.toasts.deleted(item.title));
      return true;
    },
    [items, listingKey, queryClient, setSelectedId]
  );

  return { triage, undo, remove, pendingId };
}
