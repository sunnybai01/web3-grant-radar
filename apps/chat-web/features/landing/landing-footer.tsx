import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { FadeUp } from "@/components/ui/fade-up";
import { copy } from "@/lib/copy";
import { cn } from "@/lib/utils";

import { SHELL } from "./shell";

const t = copy.landing.footer;

export function LandingFooter() {
  return (
    <footer className="border-t border-line bg-surface-alt pt-14 pb-10">
      <div className={cn(SHELL, "grid gap-10 md:grid-cols-[2fr_1fr_1fr]")}>
        <FadeUp>
          <div className="flex items-center gap-2.5 text-[0.95rem] font-semibold text-ink">
            <BrandMark className="size-6" />
            {copy.brand}
          </div>
          <p className="mt-4 max-w-[34ch] text-[0.9rem] leading-6 text-ink-body">{t.blurb}</p>
        </FadeUp>

        {t.columns.map(({ title, links }, index) => (
          <FadeUp key={title} delay={(index + 1) * 100}>
            <h4 className="mb-4 font-mono text-[10px] font-medium tracking-[0.18em] text-ink-mute uppercase">{title}</h4>
            <ul className="grid gap-2.5">
              {links.map(({ label, href }) => (
                <li key={label}>
                  <Link href={href} className="text-[0.875rem] text-ink-body transition-colors hover:text-ink">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </FadeUp>
        ))}
      </div>

      <div className={SHELL}>
        <div className="mt-10 flex flex-wrap justify-between gap-3 border-t border-line pt-7 text-[0.8rem] text-ink-mute">
          <span>{t.schedule}</span>
          <span>{t.copyright}</span>
        </div>
      </div>
    </footer>
  );
}
