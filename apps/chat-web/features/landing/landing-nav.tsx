import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { copy } from "@/lib/copy";
import { cn } from "@/lib/utils";

import { SHELL } from "./shell";

const t = copy.landing.nav;

const SECTION_LINKS = [
  { href: "#how", label: t.how },
  { href: "#console", label: t.console },
];

export function LandingNav() {
  return (
    <nav aria-label="Main" className="sticky top-0 z-40 border-b border-line bg-surface/[0.92] backdrop-blur-[10px]">
      <div className={cn(SHELL, "flex items-center justify-between gap-4 py-4")}>
        <a href="#top" className="flex items-center gap-2.5 text-[0.95rem] font-semibold text-ink">
          <BrandMark className="size-6" />
          {copy.brand}
        </a>

        <div className="hidden gap-8 text-[0.9rem] md:flex">
          {SECTION_LINKS.map(({ href, label }) => (
            <a
              key={href}
              href={href}
              className="border-b-2 border-transparent pb-0.5 text-ink-body transition-colors hover:border-yellow hover:text-ink"
            >
              {label}
            </a>
          ))}
        </div>

        <Link
          href="/triage"
          className="inline-flex items-center gap-1.5 text-[0.875rem] font-semibold text-ink transition-colors hover:text-ink-body"
        >
          {t.open}
          <ArrowRight aria-hidden className="size-4" />
        </Link>
      </div>
    </nav>
  );
}
