"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { parseTriageView, serializeTriageView } from "@/lib/triage-state";
import type { OpportunityFilters } from "@/types/chat";

/** Filters + selection, mirrored into the URL with replaceState (no navigation). */
export function useTriageView() {
  const searchParams = useSearchParams();
  const [view, setView] = useState(() => parseTriageView(new URLSearchParams(searchParams.toString())));

  useEffect(() => {
    const query = serializeTriageView(view);
    const url = `${window.location.pathname}${query ? `?${query}` : ""}`;
    if (url !== `${window.location.pathname}${window.location.search}`) {
      window.history.replaceState(window.history.state, "", url);
    }
  }, [view]);

  const setFilters = useCallback((patch: Partial<OpportunityFilters>) => {
    setView((current) => ({ ...current, filters: { ...current.filters, ...patch } }));
  }, []);

  const setSelectedId = useCallback((selectedId: number | null) => {
    setView((current) => (current.selectedId === selectedId ? current : { ...current, selectedId }));
  }, []);

  return { filters: view.filters, selectedId: view.selectedId, setFilters, setSelectedId };
}
