import { describe, expect, it } from "vitest";

import {
  DEFAULT_FILTERS,
  hasActiveFilters,
  nextSelectionAfterRemoval,
  parseTriageView,
  serializeTriageView,
  stepSelection,
} from "./triage-state";

describe("triage view in the URL", () => {
  it("round-trips filters and selection", () => {
    const view = {
      filters: { ...DEFAULT_FILTERS, status: "shortlisted" as const, type: "grant" as const, ecosystem: "base", q: "sui", closingSoon: true },
      selectedId: 132,
    };
    const query = serializeTriageView(view);

    expect(query).toBe("status=shortlisted&type=grant&chain=base&q=sui&closing=7d&id=132");
    expect(parseTriageView(new URLSearchParams(query))).toEqual(view);
  });

  it("writes nothing for the default view and ignores junk values", () => {
    expect(serializeTriageView({ filters: DEFAULT_FILTERS, selectedId: null })).toBe("");
    expect(parseTriageView(new URLSearchParams("status=archived&sort=random&id=-4"))).toEqual({
      filters: DEFAULT_FILTERS,
      selectedId: null,
    });
  });

  it("knows when filters narrow the list", () => {
    expect(hasActiveFilters(DEFAULT_FILTERS)).toBe(false);
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, status: "all" })).toBe(false);
    expect(hasActiveFilters({ ...DEFAULT_FILTERS, q: "base" })).toBe(true);
  });
});

describe("selection", () => {
  it("moves to the next row after a removal, or back when it was last", () => {
    expect(nextSelectionAfterRemoval([1, 2, 3], 2)).toBe(3);
    expect(nextSelectionAfterRemoval([1, 2, 3], 3)).toBe(2);
    expect(nextSelectionAfterRemoval([1], 1)).toBeNull();
  });

  it("steps with J/K and stops at the ends", () => {
    expect(stepSelection([1, 2, 3], 1, 1)).toBe(2);
    expect(stepSelection([1, 2, 3], 3, 1)).toBe(3);
    expect(stepSelection([1, 2, 3], 1, -1)).toBe(1);
    expect(stepSelection([1, 2, 3], null, 1)).toBe(1);
    expect(stepSelection([], null, 1)).toBeNull();
  });
});


it("keeps the reward sort in the URL", () => {
  expect(parseTriageView(new URLSearchParams("sort=reward")).filters.sort).toBe("reward");
});
