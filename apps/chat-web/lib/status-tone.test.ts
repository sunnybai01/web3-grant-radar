import { expect, it } from "vitest";

import { runTone, sourceHealthTone, verificationLabel, verificationTone } from "./status-tone";

it("colours successful and running runs correctly (success used to render red)", () => {
  expect(runTone("success")).toBe("success");
  expect(runTone("running")).toBe("warning");
  expect(runTone("failed")).toBe("danger");
  expect(runTone("skipped")).toBe("neutral");
});

it("maps source health and verification verdicts", () => {
  expect(sourceHealthTone("healthy")).toBe("success");
  expect(sourceHealthTone("down")).toBe("danger");
  expect(verificationTone("unchecked", false)).toBe("neutral");
  expect(verificationTone("degraded", false)).toBe("warning");
  expect(verificationLabel("unknown", false)).toBe("Unchecked");
});

it("colours and labels by verdict only, never by the legacy verified flag", () => {
  // 25 degraded Events still carried is_verified=true and showed a green Verified badge.
  expect(verificationTone("degraded", true)).toBe("warning");
  expect(verificationLabel("degraded", true)).toBe("Degraded");
  expect(verificationTone("verified", false)).toBe("success");
  expect(verificationLabel("verified", false)).toBe("Verified");
  expect(verificationLabel("unverified", false)).toBe("Unchecked");
  expect(verificationTone("unverified", false)).toBe("neutral");
});
