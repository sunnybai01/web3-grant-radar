import { FadeUp } from "@/components/ui/fade-up";
import { Kbd } from "@/components/ui/kbd";
import { copy } from "@/lib/copy";
import { cn } from "@/lib/utils";

import { MonoSample } from "./mono-sample";
import { SectionHead } from "./section-head";
import { CARD, SHELL } from "./shell";

const t = copy.landing.console;

export function ConsoleSection() {
  return (
    <section id="console" className="scroll-mt-16 border-t border-line bg-surface-alt py-16 md:py-24">
      <div className={SHELL}>
        <FadeUp>
          <SectionHead label={t.label} title={t.title} description={t.description} />
        </FadeUp>

        <ul className="grid gap-6 [grid-template-columns:repeat(auto-fit,minmax(280px,1fr))]">
          {t.features.map((feature, index) => (
            <li key={feature.title}>
              <FadeUp delay={index * 80} className="h-full">
                <div className={cn(CARD, "flex h-full flex-col gap-2")}>
                  <h3 className="text-base font-semibold text-ink">{feature.title}</h3>
                  <p className="mb-2 text-sm leading-[1.55] text-ink-body">{feature.description}</p>
                  {"keys" in feature ? (
                    <span className="mt-auto flex gap-1.5 rounded-md bg-surface-alt px-2.5 py-2">
                      {feature.keys.map((key) => (
                        <Kbd key={key} className="min-w-6 text-[11px]">
                          {key}
                        </Kbd>
                      ))}
                    </span>
                  ) : (
                    <MonoSample sample={feature.sample} />
                  )}
                </div>
              </FadeUp>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
