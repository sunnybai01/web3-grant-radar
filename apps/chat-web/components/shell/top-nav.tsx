"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { copy } from "@/lib/copy";
import { cn } from "@/lib/utils";

import { BrandMark } from "../brand-mark";
import { ScanControl } from "./scan-control";

const LINKS = [
  { href: "/triage", label: copy.nav.triage },
  { href: "/operations", label: copy.nav.operations },
];

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-surface/[0.92] backdrop-blur-[10px]">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-4 py-3 md:px-8">
        <div className="flex min-w-0 items-center gap-6">
          <Link href="/" className="flex items-center gap-2 font-bold text-ink">
            <BrandMark />
            <span className="hidden text-[0.9375rem] sm:inline">{copy.brand}</span>
          </Link>
          <nav aria-label="Main" className="flex items-center gap-4">
            {LINKS.map((link) => {
              const active = pathname.startsWith(link.href);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "border-b-2 py-1 text-[0.8125rem] font-semibold transition-colors",
                    active ? "border-yellow text-ink" : "border-transparent text-ink-body hover:text-ink"
                  )}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>
        <ScanControl />
      </div>
    </header>
  );
}
