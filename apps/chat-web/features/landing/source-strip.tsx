import { FadeUp } from "@/components/ui/fade-up";
import { copy } from "@/lib/copy";
import { cn } from "@/lib/utils";

import { SHELL } from "./shell";

/** Where the radar looks, as one quiet mono line under the hero. */
export function SourceStrip() {
  return (
    <div className="border-b border-line bg-surface py-[18px]">
      <FadeUp>
        <ul
          aria-label="Sources"
          className={cn(
            SHELL,
            "flex flex-wrap justify-center gap-x-10 gap-y-2.5 font-mono text-[11px] tracking-[0.12em] text-ink-mute uppercase"
          )}
        >
          {copy.landing.sources.map((source) => (
            <li key={source}>{source}</li>
          ))}
        </ul>
      </FadeUp>
    </div>
  );
}
