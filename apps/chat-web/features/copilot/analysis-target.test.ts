import { expect, it } from "vitest";

import { normalizeAnalysisTargetInput } from "./analysis-target";

it("prefers an explicit event id, then the selected one", () => {
  expect(normalizeAnalysisTargetInput({ eventId: 4 }, 9)).toEqual({ event_id: 4 });
  expect(normalizeAnalysisTargetInput({}, 9)).toEqual({ event_id: 9 });
});

it("accepts a source name with an ISO range and clamps the limit", () => {
  expect(
    normalizeAnalysisTargetInput({ sourceName: " base_blog ", from: "2026-10-01", to: "2026-10-10", limit: 500 })
  ).toEqual({ source_name: "base_blog", from: "2026-10-01", to: "2026-10-10", limit: 100 });
});

it("returns an empty target when the range is incomplete or not ISO", () => {
  expect(normalizeAnalysisTargetInput({ sourceName: "base_blog", from: "last week", to: "2026-10-10" })).toEqual({});
  expect(normalizeAnalysisTargetInput({ sourceName: "base_blog" })).toEqual({});
});
