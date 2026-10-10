import * as React from "react";

import { cn } from "@/lib/utils";

/** White floating panel: the console's basic container. */
export function Panel({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn("rounded-xl border border-line bg-surface shadow-panel", className)}
      {...props}
    />
  );
}

export function PanelHeader({
  title,
  description,
  actions,
  className,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <h2 className="text-[0.95rem] font-semibold text-ink">{title}</h2>
        {description ? (
          <p className="mt-0.5 text-[0.8125rem] leading-relaxed text-ink-body">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}
