import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function SectionHead({
  label,
  title,
  description,
  tone = "light",
}: {
  label: string;
  title: ReactNode;
  description?: ReactNode;
  tone?: "light" | "dark";
}) {
  return (
    <div className="mb-9">
      <p
        className={cn(
          "mb-2.5 font-mono text-[11px] uppercase tracking-[0.12em]",
          tone === "dark" ? "text-yellow" : "text-yellow-deep"
        )}
      >
        {label}
      </p>
      <h2
        className={cn(
          "text-[26px] leading-tight font-bold tracking-tight md:text-[32px]",
          tone === "dark" ? "text-white" : "text-ink"
        )}
      >
        {title}
      </h2>
      {description ? (
        <p
          className={cn(
            "mt-2 max-w-[62ch] text-base leading-[1.6]",
            tone === "dark" ? "text-dark-dim" : "text-ink-body"
          )}
        >
          {description}
        </p>
      ) : null}
    </div>
  );
}
