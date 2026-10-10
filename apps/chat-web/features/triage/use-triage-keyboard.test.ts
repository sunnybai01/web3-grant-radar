// @vitest-environment jsdom
import { expect, it } from "vitest";

import { resolveTriageKey } from "./use-triage-keyboard";

const press = (key: string, target: EventTarget | null = document.body, mods: Partial<KeyboardEvent> = {}) =>
  resolveTriageKey({ key, target, metaKey: false, ctrlKey: false, altKey: false, ...mods } as KeyboardEvent);

it("maps the triage shortcuts", () => {
  expect(press("j")).toBe("next");
  expect(press("K")).toBe("previous");
  expect(press("s")).toBe("shortlist");
  expect(press("d")).toBe("dismiss");
  expect(press("z")).toBe("undo");
  expect(press("o")).toBe("open");
  expect(press("/")).toBe("search");
  expect(press("x")).toBeNull();
});

it("ignores keys typed into fields, dialogs and the copilot", () => {
  const input = document.createElement("input");
  const copilot = document.createElement("div");
  copilot.setAttribute("data-copilotkit", "");
  const inside = document.createElement("span");
  copilot.appendChild(inside);
  document.body.append(input, copilot);

  expect(press("s", input)).toBeNull();
  expect(press("s", inside)).toBeNull();
  expect(press("s", document.body, { metaKey: true })).toBeNull();
});
