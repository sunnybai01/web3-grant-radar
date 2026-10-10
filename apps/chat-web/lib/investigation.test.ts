import { expect, it } from "vitest";

import { runInvestigation } from "./investigation";

it("executes the investigation request for a selected event", async () => {
  const api = {
    investigate: async (input: { event_id: number }) => ({
      status: "completed",
      event_id: input.event_id,
      mission: {
        id: 7,
        goal: `investigate_event:${input.event_id}`,
        event_id: input.event_id,
        status: "completed",
        mission_type: "single_event_investigation",
        max_steps: 5,
      },
      conclusion: {
        event_id: input.event_id,
        title: "Base Builder Rewards",
        verdict: "verified",
        recommended_action: "promote",
        summary: `Verification verdict for event ${input.event_id}: verified.`,
        similar_events: [],
        supporting_evidence: {
          url: "https://apply.base.org",
          title: "Base Builder Rewards",
          excerpt: "Applications are open for Base builders.",
        },
      },
      trajectory: [],
      error: "",
    }),
  };

  const result = await runInvestigation(api, 42);

  expect(result.status).toBe("completed");
  expect(result.event_id).toBe(42);
  expect(result.conclusion?.recommended_action).toBe("promote");
});
