import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

/** Status pill. Tone is a verdict colour; use `neutral` / `highlight` for choices. */
export const badgeVariants = cva(
  "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-[10.5px] font-semibold uppercase leading-none tracking-[0.02em] whitespace-nowrap",
  {
    variants: {
      tone: {
        success: "bg-success-badge text-success",
        warning: "bg-warning-badge text-warning",
        danger: "bg-danger-badge text-danger",
        neutral: "bg-neutral-badge text-ink-body",
        highlight: "bg-yellow-soft text-ink",
      },
    },
    defaultVariants: { tone: "neutral" },
  }
);

export type Tone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

export function Badge({
  className,
  tone,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

const dotTone: Record<Tone, string> = {
  success: "bg-success",
  warning: "bg-warning-dot",
  danger: "bg-danger",
  neutral: "bg-ink-mute",
  highlight: "bg-yellow",
};

export function StatusDot({ tone = "neutral", className }: { tone?: Tone; className?: string }) {
  return <span aria-hidden className={cn("inline-block size-2 shrink-0 rounded-full", dotTone[tone], className)} />;
}
