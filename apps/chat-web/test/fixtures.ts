import type { DashboardOpportunitiesResponse, DashboardOpportunityItem } from "../types/chat";

export function makeItem(id: number, overrides: Partial<DashboardOpportunityItem> = {}): DashboardOpportunityItem {
  return {
    id,
    score: 7,
    scores: { roi: null, reputation: null, timeliness: null, strategy: null },
    type: "GRANT",
    title: `Opportunity ${id}`,
    summary: "",
    ecosystem: "base",
    amount: "$10,000",
    deadline: null,
    first_seen: null,
    heat: 1,
    source_count: 1,
    verified: false,
    verification_verdict: "unchecked",
    source_trust: "official",
    apply_url: "https://example.com",
    triage_status: "new",
    ...overrides,
  };
}

export function makeListing(items: DashboardOpportunityItem[]): DashboardOpportunitiesResponse {
  return {
    items,
    counts: { new: items.length, shortlisted: 0, dismissed: 0, all: items.length },
    metrics: {
      to_review: items.length,
      shortlisted: 0,
      closing_soon: 0,
      verified_percent: 0,
      verified_count: 0,
      unchecked_count: 0,
      total: items.length,
    },
    ecosystems: ["base"],
    next_scan_at: "2026-10-10T21:00:00+08:00",
  };
}
