import { describe, expect, it } from "vitest";

import {
  getManualScanProgressLabel,
  getScheduleStatusMap,
  summarizeManualScan,
} from "./manual-scan";

describe("manual scan helpers", () => {
  it("summarizes schedule totals", () => {
    const summary = summarizeManualScan({
      job_id: "job-1",
      status: "success",
      triggered: true,
      started_at: "2026-07-02T09:00:00Z",
      finished_at: "2026-07-02T09:01:00Z",
      current_stage: "",
      error: "",
      schedules: [
        {
          schedule: "grant_hackathon",
          status: "success",
          fetched: 12,
          new: 2,
          deduped: 10,
          classified: 2,
          verified: 1,
          fraud: 0,
          pushed: 1,
          error: "",
        },
      ],
    });

    expect(summary).toEqual({
      fetched: 12,
      new: 2,
      deduped: 10,
      classified: 2,
      verified: 1,
      fraud: 0,
      pushed: 1,
    });
  });

  it("maps schedule progress for running job", () => {
    const schedules = getScheduleStatusMap({
      job_id: "job-2",
      status: "running",
      triggered: true,
      started_at: "2026-07-02T09:00:00Z",
      finished_at: "",
      current_stage: "grant_hackathon",
      error: "",
      schedules: [],
    });

    expect(schedules).toEqual([
      {
        schedule: "grant_hackathon",
        status: "running",
        result: null,
      },
    ]);
  });

  it("returns readable progress labels", () => {
    expect(getManualScanProgressLabel(null)).toBe("No manual scan yet");
    expect(
      getManualScanProgressLabel({
        job_id: "job-3",
        status: "running",
        triggered: true,
        started_at: "2026-07-02T09:00:00Z",
        finished_at: "",
        current_stage: "grant_hackathon",
        error: "",
        schedules: [],
      })
    ).toBe("Running grant_hackathon");
  });
});
