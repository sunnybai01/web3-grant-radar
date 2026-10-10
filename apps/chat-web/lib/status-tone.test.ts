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
  expect(verificationTone("anything", true)).toBe("success");
  expect(verificationLabel("unknown", false)).toBe("Unchecked");
});
