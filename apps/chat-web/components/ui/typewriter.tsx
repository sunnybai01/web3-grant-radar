"use client";

import { useEffect, useState, type ReactNode } from "react";

type Phase = "typing" | "holding" | "erasing" | "resting";

/** Types `text` out, holds, erases and starts over. */
export function Typewriter({
  text,
  className,
  typeMs = 60,
  eraseMs = 40,
  startDelayMs = 0,
  holdMs = 2400,
  restMs = 400,
  cursor = "_",
  cursorClassName,
  renderText,
}: {
  text: string;
  className?: string;
  typeMs?: number;
  eraseMs?: number;
  startDelayMs?: number;
  holdMs?: number;
  restMs?: number;
  cursor?: ReactNode;
  cursorClassName?: string;
  /** Renders the visible prefix, e.g. to highlight part of it. */
  renderText?: (shown: string) => ReactNode;
}) {
  const [length, setLength] = useState(0);
  const [phase, setPhase] = useState<Phase>("resting");
  const [started, setStarted] = useState(startDelayMs === 0);

  useEffect(() => {
    if (started) return;
    const id = window.setTimeout(() => setStarted(true), startDelayMs);
    return () => window.clearTimeout(id);
  }, [started, startDelayMs]);

  useEffect(() => {
    if (!started) return;

    const next = (): [number, () => void] => {
      switch (phase) {
        case "resting":
          return [length === 0 ? 0 : restMs, () => setPhase("typing")];
        case "typing":
          if (length < text.length) return [typeMs, () => setLength((n) => n + 1)];
          return [0, () => setPhase("holding")];
        case "holding":
          return [holdMs, () => setPhase("erasing")];
        case "erasing":
          if (length > 0) return [eraseMs, () => setLength((n) => n - 1)];
          return [restMs, () => setPhase("typing")];
      }
    };

    const [delay, step] = next();
    const id = window.setTimeout(step, delay);
    return () => window.clearTimeout(id);
  }, [started, phase, length, text, typeMs, eraseMs, holdMs, restMs]);

  const shown = text.slice(0, length);

  return (
    <span className={className}>
      {renderText ? renderText(shown) : shown}
      <span aria-hidden className={`ml-1 inline-block animate-caret ${cursorClassName ?? ""}`}>
        {cursor}
      </span>
    </span>
  );
}
