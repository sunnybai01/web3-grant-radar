import { FadeUp } from "@/components/ui/fade-up";
import { copy } from "@/lib/copy";
import { cn } from "@/lib/utils";

import { MonoSample } from "./mono-sample";
import { SectionHead } from "./section-head";
import { CARD, SHELL } from "./shell";

const t = copy.landing.how;

export function HowItWorks() {
  return (
    <section id="how" className="scroll-mt-16 bg-surface py-16 md:py-24">
      <div className={SHELL}>
        <FadeUp>
          <SectionHead label={t.label} title={t.title} description={t.description} />
        </FadeUp>

        <ol className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(260px,1fr))]">
          {t.stages.map(({ num, title, description, sample }, index) => (
            <li key={num}>
              <FadeUp delay={index * 80} className="h-full">
                <div className={cn(CARD, "flex h-full flex-col gap-2")}>
                  <span className="font-mono text-[13px] font-medium text-yellow-deep">{num}</span>
                  <h3 className="text-base font-semibold text-ink">{title}</h3>
                  <p className="mb-2 text-sm leading-[1.55] text-ink-body">{description}</p>
                  <MonoSample sample={sample} />
                </div>
              </FadeUp>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
