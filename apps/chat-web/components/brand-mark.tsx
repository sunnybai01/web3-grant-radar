import { cn } from "@/lib/utils";

/** The radar's mark: an ink disc with a yellow core. app/icon.svg draws the same. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cn("relative inline-block size-5 shrink-0 rounded-full bg-ink", className)}>
      <span className="absolute inset-1/4 rounded-full bg-yellow" />
    </span>
  );
}
