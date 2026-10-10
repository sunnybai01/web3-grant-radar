"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export type SegmentedOption<T extends string> = {
  value: T;
  label: React.ReactNode;
  count?: number;
};

/**
 * Grey track with a raised white segment for the active option. Implements the
 * ARIA tabs pattern (roving tabindex, arrow keys) when used as a tab list.
 */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  className,
}: {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  className?: string;
}) {
  const refs = React.useRef<Array<HTMLButtonElement | null>>([]);

  const onKeyDown = (event: React.KeyboardEvent, index: number) => {
    const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!delta) return;
    event.preventDefault();
    const next = (index + delta + options.length) % options.length;
    refs.current[next]?.focus();
    onChange(options[next].value);
  };

  return (
    <div role="tablist" aria-label={label} className={cn("inline-flex rounded-lg bg-surface-track p-1", className)}>
      {options.map((option, index) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            ref={(node) => {
              refs.current[index] = node;
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(option.value)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[0.8125rem] whitespace-nowrap transition-colors",
              selected
                ? "bg-surface font-semibold text-ink shadow-[0_1px_2px_rgba(16,24,40,0.08)]"
                : "text-ink-body hover:text-ink"
            )}
          >
            {option.label}
            {option.count !== undefined ? (
              <span className="font-mono text-[11px] tabular-nums text-ink-mute">{option.count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
