import { describe, expect, it } from "vitest";

import { describeDeadline, formatAmount, formatChain, formatRelative, formatScore } from "./format";

const NOW = new Date("2026-10-10T04:00:00Z");

describe("describeDeadline", () => {
  it("marks deadlines within a week as urgent", () => {
    expect(describeDeadline("2026-10-14T00:00:00Z", NOW)).toMatchObject({
      label: "closes in 3d",
      state: "urgent",
      daysLeft: 3,
      exact: "Oct 14, 2026",
    });
  });

  it("keeps later deadlines plain", () => {
    expect(describeDeadline("2026-11-01T00:00:00Z", NOW).state).toBe("open");
  });

  it("says today on the last day", () => {
    expect(describeDeadline("2026-10-10T20:00:00Z", NOW).label).toBe("closes today");
  });

  it("treats a missing deadline as rolling and a past one as closed", () => {
    expect(describeDeadline(null, NOW)).toMatchObject({ label: "rolling", state: "rolling", exact: null });
    expect(describeDeadline("2026-10-01T00:00:00Z", NOW)).toMatchObject({ label: "closed", state: "closed" });
  });
});

describe("value formatting", () => {
  it("formats relative times in both directions", () => {
    expect(formatRelative("2026-10-10T03:58:00Z", NOW)).toBe("2m ago");
    expect(formatRelative("2026-10-09T04:00:00Z", NOW)).toBe("1d ago");
    expect(formatRelative("2026-10-10T07:00:00Z", NOW)).toBe("in 3h");
    expect(formatRelative(null, NOW)).toBe("never");
  });

  it("spells out missing amounts and scores", () => {
    expect(formatAmount(null)).toBe("Amount not stated");
    expect(formatAmount("-")).toBe("Amount not stated");
    expect(formatAmount("$50,000")).toBe("$50,000");
    expect(formatScore(null)).toBe("—");
    expect(formatScore(8)).toBe("8.0");
    expect(formatChain("base")).toBe("BASE");
  });
});
