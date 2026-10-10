"use client";

import { useEffect, useRef } from "react";

export type TriageKeyHandlers = {
  next: () => void;
  previous: () => void;
  shortlist: () => void;
  dismiss: () => void;
  undo: () => void;
  open: () => void;
  search: () => void;
};

/** True when a keystroke belongs to a text field, a dialog or the Copilot chat. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return true;
  return Boolean(target.closest("[data-copilotkit], [role='dialog'], [role='menu']"));
}

const KEYS: Record<string, keyof TriageKeyHandlers> = {
  j: "next",
  ArrowDown: "next",
  k: "previous",
  ArrowUp: "previous",
  s: "shortlist",
  d: "dismiss",
  z: "undo",
  o: "open",
  "/": "search",
};

export function resolveTriageKey(event: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "altKey" | "target">) {
  if (event.metaKey || event.ctrlKey || event.altKey) return null;
  if (isTypingTarget(event.target)) return null;
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  return KEYS[key] ?? null;
}

/** J/K move, S shortlist, D dismiss, Z undo, O open apply page, / search. */
export function useTriageKeyboard(handlers: TriageKeyHandlers, enabled = true) {
  const latest = useRef(handlers);
  latest.current = handlers;

  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (event: KeyboardEvent) => {
      const action = resolveTriageKey(event);
      if (!action) return;
      event.preventDefault();
      latest.current[action]();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [enabled]);
}
