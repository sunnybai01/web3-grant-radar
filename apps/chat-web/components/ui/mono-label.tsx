import * as React from "react";

import { cn } from "@/lib/utils";

/** Small uppercase mono caption that sits above values. */
export function MonoLabel({
  className,
  as: Component = "span",
  ...props
}: React.HTMLAttributes<HTMLElement> & { as?: React.ElementType }) {
  return (
    <Component
      className={cn("font-mono text-[10px] uppercase tracking-[0.12em] text-ink-mute", className)}
      {...props}
    />
  );
}

/** Page eyebrow: the same caption in the text-safe yellow. */
export function Eyebrow({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("font-mono text-[11px] uppercase tracking-[0.12em] text-yellow-deep", className)}
      {...props}
    />
  );
}

/** Caption + grey mono value strip. */
export function ValueStrip({
  label,
  children,
  className,
  valueClassName,
  wrap = false,
}: {
  label: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  valueClassName?: string;
  /** Let long values (amounts) wrap onto two lines instead of truncating. */
  wrap?: boolean;
}) {
  return (
    <div className={cn("min-w-0 rounded-md bg-surface-alt px-2.5 py-2", className)}>
      <MonoLabel as="div">{label}</MonoLabel>
      <div
        className={cn(
          "mt-1 font-mono text-[0.8125rem] font-medium tabular-nums text-ink",
          wrap ? "line-clamp-2 break-words" : "truncate",
          valueClassName
        )}
        title={wrap && typeof children === "string" ? children : undefined}
      >
        {children}
      </div>
    </div>
  );
}
