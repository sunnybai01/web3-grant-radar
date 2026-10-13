import { ButtonLink } from "@/components/ui/button";
import { FadeUp } from "@/components/ui/fade-up";
import { copy } from "@/lib/copy";
import { cn } from "@/lib/utils";

import { SHELL } from "./shell";

const t = copy.landing.closing;

export function ClosingCta() {
  return (
    <section className="relative overflow-hidden bg-ink py-20 text-white md:py-[140px]">
      {/* A still dot lattice in the accent, fading towards the left. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_left,black,transparent_75%)]"
        style={{
          backgroundImage:
            "radial-gradient(color-mix(in srgb, var(--color-yellow) 30%, transparent) 1.4px, transparent 1.6px)",
          backgroundSize: "13px 13px",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(800px 400px at 80% 50%, color-mix(in srgb, var(--color-yellow) 16%, transparent), transparent 70%)",
        }}
      />

      <div className={cn(SHELL, "relative grid items-end gap-10 md:grid-cols-[1fr_auto]")}>
        <FadeUp>
          <p className="font-mono text-[11px] tracking-[0.12em] text-yellow uppercase">{t.label}</p>
          <h2 className="mt-4 max-w-[24ch] text-[30px] leading-tight font-bold tracking-tight md:text-[38px]">
            {t.title}
          </h2>
        </FadeUp>

        <FadeUp delay={150}>
          <div className="flex flex-wrap items-center gap-3.5">
            <ButtonLink href="/triage" variant="accent" size="lg">
              {t.primary}
            </ButtonLink>
            <ButtonLink href="/operations" variant="ghostDark" size="lg" pillIcon={null}>
              {t.secondary}
            </ButtonLink>
          </div>
        </FadeUp>
      </div>
    </section>
  );
}
