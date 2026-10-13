"use client";

import { useEffect, useState } from "react";

import { Typewriter } from "@/components/ui/typewriter";
import { copy } from "@/lib/copy";

const { title, highlight } = copy.landing.hero;
const CURSOR = "_";

function renderTitle(shown: string) {
  const start = title.indexOf(highlight);
  const end = start + highlight.length;
  const highlighted = shown.slice(start, end);

  return (
    <>
      {shown.slice(0, start)}
      {highlighted ? <span className="text-spectrum motion-safe:animate-gradient-pan">{highlighted}</span> : null}
      {shown.slice(end)}
    </>
  );
}

/** The hero title, typed out on a loop unless the reader prefers reduced motion. */
export function Headline() {
  // The server and the first client render show the whole title; typing starts after mount.
  const [animate, setAnimate] = useState(false);
  useEffect(() => {
    setAnimate(!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  }, []);

  return (
    <h1 className="mx-auto max-w-[13.6em] text-4xl leading-[1.12] font-bold tracking-tight text-ink md:text-5xl lg:text-[54px]">
      {animate ? (
        <>
          <span className="sr-only">{title}</span>
          {/* The invisible full title holds the height, so typing never reflows the page. */}
          <span aria-hidden className="grid">
            <span className="invisible col-start-1 row-start-1">
              {renderTitle(title)}
              <span className="ml-1 inline-block">{CURSOR}</span>
            </span>
            <Typewriter
              className="col-start-1 row-start-1"
              text={title}
              startDelayMs={800}
              eraseMs={50}
              cursor={CURSOR}
              cursorClassName="font-light text-ink-body"
              renderText={renderTitle}
            />
          </span>
        </>
      ) : (
        renderTitle(title)
      )}
    </h1>
  );
}
