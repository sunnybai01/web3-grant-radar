import * as React from "react";

import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, type = "text", ...props }, ref) {
    return (
      <input
        ref={ref}
        type={type}
        className={cn(
          "h-9 w-full rounded-md border border-line-strong bg-surface px-3 text-[0.8125rem] text-ink placeholder:text-ink-mute focus:border-ink focus:shadow-focus focus:outline-none",
          className
        )}
        {...props}
      />
    );
  }
);

/** Native select styled as a mono chip, e.g. "Type: All". */
export const SelectChip = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement> & { label: string }
>(function SelectChip({ className, label, id, children, ...props }, ref) {
  const generatedId = React.useId();
  const selectId = id ?? generatedId;
  return (
    <span className="relative inline-flex items-center">
      <label
        htmlFor={selectId}
        className="pointer-events-none absolute left-2.5 font-mono text-[10px] uppercase tracking-[0.08em] text-ink-mute"
      >
        {label}
      </label>
      <select
        ref={ref}
        id={selectId}
        className={cn(
          "h-8 cursor-pointer appearance-none rounded-md border border-line bg-surface pr-7 font-mono text-[11px] uppercase text-ink hover:border-line-strong focus:border-ink focus:shadow-focus focus:outline-none",
          className
        )}
        style={{ paddingLeft: `calc(${label.length + 1}ch + 0.9rem)` }}
        {...props}
      >
        {children}
      </select>
      <span aria-hidden className="pointer-events-none absolute right-2.5 text-[9px] text-ink-mute">
        ▼
      </span>
    </span>
  );
});
