import type {
  DashboardOpportunitiesResponse,
  DashboardOpportunityItem,
  TriageStatus,
  TriageTab,
} from "../types/chat";
import { belongsToTab } from "./triage-state";

/**
 * Pure updates to a cached listing after a triage decision, so the list reacts
 * immediately and the server round-trip never reshuffles what the user sees.
 */

function adjustCounts(
  listing: DashboardOpportunitiesResponse,
  from: TriageStatus,
  to: TriageStatus
): DashboardOpportunitiesResponse {
  if (from === to) return listing;
  const counts = { ...listing.counts };
  counts[from] = Math.max(0, counts[from] - 1);
  counts[to] = counts[to] + 1;

  const metrics = { ...listing.metrics };
  if (from === "new") metrics.to_review = Math.max(0, metrics.to_review - 1);
  if (to === "new") metrics.to_review += 1;
  if (from === "shortlisted") metrics.shortlisted = Math.max(0, metrics.shortlisted - 1);
  if (to === "shortlisted") metrics.shortlisted += 1;
  if (from === "dismissed") metrics.total += 1;
  if (to === "dismissed") metrics.total = Math.max(0, metrics.total - 1);

  return { ...listing, counts, metrics };
}

/**
 * Move `item` to status `to` inside a listing for `tab`. When the item should
 * appear on this tab but is not there (an undo), it is re-inserted at `index`.
 */
export function applyTriage(
  listing: DashboardOpportunitiesResponse,
  tab: TriageTab,
  item: DashboardOpportunityItem,
  to: TriageStatus,
  index?: number
): DashboardOpportunitiesResponse {
  const updated = { ...item, triage_status: to };
  const present = listing.items.some((row) => row.id === item.id);
  let items: DashboardOpportunityItem[];

  if (belongsToTab(to, tab)) {
    if (present) {
      items = listing.items.map((row) => (row.id === item.id ? updated : row));
    } else {
      items = [...listing.items];
      items.splice(Math.min(index ?? items.length, items.length), 0, updated);
    }
  } else {
    items = listing.items.filter((row) => row.id !== item.id);
  }

  return adjustCounts({ ...listing, items }, item.triage_status, to);
}

/** Drop a deleted row and its count. */
export function removeFromListing(
  listing: DashboardOpportunitiesResponse,
  id: number
): DashboardOpportunitiesResponse {
  const row = listing.items.find((item) => item.id === id);
  if (!row) return listing;
  const counts = { ...listing.counts };
  counts[row.triage_status] = Math.max(0, counts[row.triage_status] - 1);
  counts.all = Math.max(0, counts.all - 1);
  return { ...listing, counts, items: listing.items.filter((item) => item.id !== id) };
}
