import { describe, expect, it } from "vitest";

import { makeItem, makeListing as listing } from "../test/fixtures";
import { applyTriage, removeFromListing } from "./listing-cache";

describe("applyTriage", () => {
  it("removes a row that leaves the tab and moves the counts", () => {
    const before = listing([makeItem(1), makeItem(2)]);
    const after = applyTriage(before, "new", before.items[0], "shortlisted");

    expect(after.items.map((item) => item.id)).toEqual([2]);
    expect(after.counts).toMatchObject({ new: 1, shortlisted: 1 });
    expect(after.metrics).toMatchObject({ to_review: 1, shortlisted: 1 });
  });

  it("re-inserts a row at its old position on undo", () => {
    const start = listing([makeItem(1), makeItem(2), makeItem(3)]);
    const removed = applyTriage(start, "new", start.items[1], "dismissed");
    const restored = applyTriage(removed, "new", { ...start.items[1], triage_status: "dismissed" }, "new", 1);

    expect(restored.items.map((item) => item.id)).toEqual([1, 2, 3]);
    expect(restored.counts).toMatchObject({ new: 3, dismissed: 0 });
    expect(restored.metrics.total).toBe(3);
  });

  it("updates the row in place on the All tab", () => {
    const before = listing([makeItem(1)]);
    const after = applyTriage(before, "all", before.items[0], "dismissed");

    expect(after.items[0].triage_status).toBe("dismissed");
    expect(after.metrics.total).toBe(0);
  });
});

it("removeFromListing drops the row and its count", () => {
  const after = removeFromListing(listing([makeItem(1), makeItem(2)]), 1);

  expect(after.items.map((item) => item.id)).toEqual([2]);
  expect(after.counts).toMatchObject({ new: 1, all: 1 });
});
