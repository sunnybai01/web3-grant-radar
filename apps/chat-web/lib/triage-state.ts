import type { OpportunityFilters, OpportunitySort, TriageTab } from "../types/chat";

/** The triage view lives in the URL so it survives refresh and can be shared. */

export const DEFAULT_FILTERS: OpportunityFilters = {
  status: "new",
  type: "all",
  trust: "all",
  ecosystem: "",
  q: "",
  sort: "score",
  closingSoon: false,
};

const TABS: TriageTab[] = ["new", "shortlisted", "dismissed", "all"];
const SORTS: OpportunitySort[] = ["score", "deadline", "newest"];

function pick<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return value && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

export type TriageView = { filters: OpportunityFilters; selectedId: number | null };

export function parseTriageView(params: URLSearchParams): TriageView {
  const id = Number(params.get("id"));
  return {
    filters: {
      status: pick(params.get("status"), TABS, DEFAULT_FILTERS.status),
      type: pick(params.get("type"), ["all", "grant", "hackathon"] as const, "all"),
      trust: pick(params.get("trust"), ["all", "official", "discovery"] as const, "all"),
      ecosystem: (params.get("chain") ?? "").toLowerCase(),
      q: params.get("q") ?? "",
      sort: pick(params.get("sort"), SORTS, DEFAULT_FILTERS.sort),
      closingSoon: params.get("closing") === "7d",
    },
    selectedId: Number.isInteger(id) && id > 0 ? id : null,
  };
}

/** Only non-default values are written, so the default view keeps a clean URL. */
export function serializeTriageView({ filters, selectedId }: TriageView): string {
  const params = new URLSearchParams();
  if (filters.status !== DEFAULT_FILTERS.status) params.set("status", filters.status);
  if (filters.type !== "all") params.set("type", filters.type);
  if (filters.trust !== "all") params.set("trust", filters.trust);
  if (filters.ecosystem) params.set("chain", filters.ecosystem);
  if (filters.q) params.set("q", filters.q);
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set("sort", filters.sort);
  if (filters.closingSoon) params.set("closing", "7d");
  if (selectedId !== null) params.set("id", String(selectedId));
  return params.toString();
}

export function hasActiveFilters(filters: OpportunityFilters): boolean {
  return (
    filters.type !== "all" ||
    filters.trust !== "all" ||
    Boolean(filters.ecosystem) ||
    Boolean(filters.q.trim()) ||
    filters.closingSoon
  );
}

/**
 * Which row to select after `removedId` leaves the list: the next one, or the
 * previous one when the removed row was last.
 */
export function nextSelectionAfterRemoval(ids: number[], removedId: number): number | null {
  const index = ids.indexOf(removedId);
  if (index === -1) return ids[0] ?? null;
  const remaining = ids.filter((id) => id !== removedId);
  if (remaining.length === 0) return null;
  return remaining[Math.min(index, remaining.length - 1)];
}

/** Neighbour for J/K navigation; stays put at either end. */
export function stepSelection(ids: number[], current: number | null, delta: 1 | -1): number | null {
  if (ids.length === 0) return null;
  const index = current === null ? -1 : ids.indexOf(current);
  if (index === -1) return ids[0];
  return ids[Math.max(0, Math.min(ids.length - 1, index + delta))];
}

/** Does a row in `status` belong on the `tab` list? */
export function belongsToTab(status: string, tab: TriageTab): boolean {
  return tab === "all" || status === tab;
}
