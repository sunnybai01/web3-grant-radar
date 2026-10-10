import React from "react";
import { renderToString } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("@copilotkit/react-core/v2", () => ({
  useFrontendTool: () => undefined,
}));

vi.mock("@copilotkit/react-ui", () => ({
  CopilotChat: () => <div>Copilot Chat Mock</div>,
}));

import AgentChat from "./agent-chat";
import { normalizeAnalysisTargetInput } from "./agent-chat";
import { removeOpportunityFromState } from "./agent-chat";
import { scrollToRelatedPanel } from "./agent-chat";
import { shouldRequestTabData } from "./agent-chat";

it("renders dashboard-first workspace", () => {
  const html = renderToString(<AgentChat />);
  // The dashboard is the page itself; the Copilot lives behind a drawer that only
  // mounts on demand, so no copilot surface appears in the initial render.
  expect(html).toContain("Opportunity Pipeline");
  expect(html).toContain("Run Scan");
  expect(html).toContain("Daily Summary");
  expect(html).toContain("Source Health");
  expect(html).toContain("Schedule Logs");
  expect(html).not.toContain("Copilot Chat Mock");
});

it("removes a deleted opportunity from dashboard state", () => {
  const first = {
    id: 1,
    score: 8.1,
    type: "GRANT",
    title: "Base Builder Fund",
    ecosystem: "base",
    amount: "$50,000",
    deadline: "2026-07-20",
    heat: 2,
    verified: true,
    source_trust: "official",
    verification_verdict: "verified",
    apply_url: "https://apply.base.org",
    is_dismissed: false,
  };
  const second = {
    id: 2,
    score: 7.4,
    type: "HACKATHON",
    title: "Sui Overflow",
    ecosystem: "sui",
    amount: "$20,000",
    deadline: "2026-08-01",
    heat: 1,
    verified: true,
    source_trust: "official",
    verification_verdict: "verified",
    apply_url: "https://sui.io/overflow",
    is_dismissed: false,
  };

  const result = removeOpportunityFromState(
    {
      metrics: {
        total_shown: 2,
        avg_score: 7.8,
        verified_percent: 100,
        grants: 1,
        hackathons: 1,
        official: 2,
        discovery: 0,
      },
      items: [first, second],
    },
    second,
    2
  );

  expect(result.dashboardData?.items).toEqual([first]);
  expect(result.selectedOpportunity).toEqual(first);
});

it("keeps the current selection when deleting a different row", () => {
  const first = {
    id: 1,
    score: 8.1,
    type: "GRANT",
    title: "Base Builder Fund",
    ecosystem: "base",
    amount: "$50,000",
    deadline: "2026-07-20",
    heat: 2,
    verified: true,
    source_trust: "official",
    verification_verdict: "verified",
    apply_url: "https://apply.base.org",
    is_dismissed: false,
  };
  const second = {
    id: 2,
    score: 7.4,
    type: "HACKATHON",
    title: "Sui Overflow",
    ecosystem: "sui",
    amount: "$20,000",
    deadline: "2026-08-01",
    heat: 1,
    verified: true,
    source_trust: "official",
    verification_verdict: "verified",
    apply_url: "https://sui.io/overflow",
    is_dismissed: false,
  };

  const result = removeOpportunityFromState(
    {
      metrics: {
        total_shown: 2,
        avg_score: 7.8,
        verified_percent: 100,
        grants: 1,
        hackathons: 1,
        official: 2,
        discovery: 0,
      },
      items: [first, second],
    },
    first,
    2
  );

  expect(result.dashboardData?.items).toEqual([first]);
  expect(result.selectedOpportunity).toEqual(first);
  expect(result.dashboardData?.metrics.total_shown).toBe(1);
});

it("prefers a specific event id over free-form tool filters", () => {
  expect(
    normalizeAnalysisTargetInput(
      {
        eventId: 3,
        sourceName: "Solana Foundation",
        from: "superteam.fun",
        to: "superteam.fun",
        limit: 5,
      },
      9
    )
  ).toEqual({ event_id: 3 });
});

it("keeps source queries only when the date range is ISO-like", () => {
  expect(
    normalizeAnalysisTargetInput({
      sourceName: "Solana Foundation",
      from: "2026-07-01",
      to: "2026-07-02T00:00:00Z",
      limit: 999,
    })
  ).toEqual({
    source_name: "Solana Foundation",
    from: "2026-07-01",
    to: "2026-07-02T00:00:00Z",
    limit: 100,
  });
});

it("requests tab data when the panel is empty or previously failed", () => {
  expect(
    shouldRequestTabData({
      hasData: false,
      isLoading: false,
      hasError: false,
    })
  ).toBe(true);

  expect(
    shouldRequestTabData({
      hasData: true,
      isLoading: false,
      hasError: true,
    })
  ).toBe(true);

  expect(
    shouldRequestTabData({
      hasData: true,
      isLoading: false,
      hasError: false,
    })
  ).toBe(false);

  expect(
    shouldRequestTabData({
      hasData: false,
      isLoading: true,
      hasError: true,
    })
  ).toBe(false);
});

it("scrolls the related panel into view with smooth alignment", () => {
  const scrollIntoView = vi.fn();

  scrollToRelatedPanel({ scrollIntoView } as unknown as HTMLDivElement);

  expect(scrollIntoView).toHaveBeenCalledWith({
    behavior: "smooth",
    block: "start",
    inline: "nearest",
  });
});
