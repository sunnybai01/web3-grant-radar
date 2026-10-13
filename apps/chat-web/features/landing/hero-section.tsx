import type { ReactNode } from "react";

import { ButtonLink } from "@/components/ui/button";
import { copy } from "@/lib/copy";
import { cn } from "@/lib/utils";

import { Headline } from "./headline";
import { RadarBackdrop } from "./radar-backdrop";
import { RadarPipeline } from "./radar-pipeline";
import { SHELL } from "./shell";

const t = copy.landing.hero;

/** The hero is in view on load, so it rises in with CSS alone and shows before hydration. */
function RiseIn({ delay = 0, children }: { delay?: number; children: ReactNode }) {
  return (
    <div className="motion-safe:animate-rise-in" style={delay ? { animationDelay: `${delay}ms` } : undefined}>
      {children}
    </div>
  );
}

export function HeroSection() {
  return (
    <header id="top" className="relative overflow-hidden border-b border-line bg-linear-to-b from-surface to-surface-hero">
      <RadarBackdrop />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(720px 340px at 50% 80%, color-mix(in srgb, var(--color-yellow) 26%, transparent), transparent 70%)",
        }}
      />

      <div className={cn(SHELL, "relative pt-20 pb-20 text-center md:pt-24 md:pb-[110px]")}>
        <RiseIn>
          <Headline />
        </RiseIn>

        <RiseIn delay={120}>
          <p className="mx-auto mt-5 max-w-[640px] text-lg leading-[1.6] text-ink-body">{t.lede}</p>
        </RiseIn>

        <RiseIn delay={240}>
          <div className="mt-8 flex justify-center">
            <ButtonLink href="/triage" size="lg">
              {t.cta}
            </ButtonLink>
          </div>
        </RiseIn>

        <RiseIn delay={360}>
          <RadarPipeline />
        </RiseIn>
      </div>
    </header>
  );
}
