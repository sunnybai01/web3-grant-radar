"use client";

import type { ReactNode } from "react";

import { useInView } from "@/lib/use-in-view";
import { cn } from "@/lib/utils";

/** Fades and lifts its content in the first time it scrolls into view. */
export function FadeUp({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  /** Milliseconds, for staggering siblings. */
  delay?: number;
  className?: string;
}) {
  const { ref, inView } = useInView<HTMLDivElement>();

  return (
    <div
      ref={ref}
      data-visible={inView}
      className={cn("fade-up", className)}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  );
}
