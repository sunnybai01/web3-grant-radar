import * as React from "react";

import { cn } from "@/lib/utils";

export function Kbd({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        "inline-flex min-w-[1.25rem] items-center justify-center rounded border border-b-2 border-line-strong bg-surface px-1 font-mono text-[10px] text-ink-body",
        className
      )}
      {...props}
    />
  );
}
