"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { OpportunityFilters } from "../types/chat";
import { client } from "./client";
import { DEFAULT_FILTERS } from "./triage-state";

export const queryKeys = {
  opportunities: (filters: OpportunityFilters) => ["opportunities", filters] as const,
  opportunitiesRoot: ["opportunities"] as const,
  arrivals: ["opportunities-arrivals"] as const,
  opportunity: (id: number) => ["opportunity", id] as const,
  manualScan: ["manual-scan"] as const,
  sourceHealth: ["source-health"] as const,
  scheduleLogs: ["schedule-logs"] as const,
};

const SCAN_POLL_MS = 4_000;
const ARRIVALS_POLL_MS = 120_000;

/**
 * The visible list never refetches on its own: it changes only when the user
 * acts, changes filters, or asks to load new arrivals.
 */
export function useOpportunities(filters: OpportunityFilters) {
  return useQuery({
    queryKey: queryKeys.opportunities(filters),
    queryFn: () => client.listOpportunities(filters),
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
}

/** Background probe of the New tab, used to announce arrivals without reordering the list. */
export function useArrivalsProbe() {
  return useQuery({
    queryKey: queryKeys.arrivals,
    queryFn: () => client.listOpportunities({ ...DEFAULT_FILTERS, status: "new" }),
    refetchInterval: ARRIVALS_POLL_MS,
    refetchOnWindowFocus: true,
  });
}

export function useOpportunity(id: number | null) {
  return useQuery({
    queryKey: queryKeys.opportunity(id ?? 0),
    queryFn: () => client.getOpportunity(id as number),
    enabled: id !== null,
    staleTime: 60_000,
  });
}

export function useManualScan() {
  return useQuery({
    queryKey: queryKeys.manualScan,
    queryFn: client.manualScan,
    refetchInterval: (query) => (query.state.data?.status === "running" ? SCAN_POLL_MS : false),
  });
}

export function useStartScan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: client.startManualScan,
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.manualScan, data);
    },
  });
}

export function useSourceHealth() {
  return useQuery({ queryKey: queryKeys.sourceHealth, queryFn: client.sourceHealth });
}

export function useScheduleLogs() {
  return useQuery({ queryKey: queryKeys.scheduleLogs, queryFn: () => client.scheduleLogs(50) });
}
