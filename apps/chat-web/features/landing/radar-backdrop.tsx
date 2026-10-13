import type { CSSProperties } from "react";

const SWEEP_SECONDS = 8;

/** Contacts on the scope: clockwise angle from 12 o'clock, distance from the centre (0–1). */
const BLIPS = [
  { angle: 34, distance: 0.62 },
  { angle: 98, distance: 0.36 },
  { angle: 151, distance: 0.8 },
  { angle: 214, distance: 0.55 },
  { angle: 263, distance: 0.28 },
  { angle: 318, distance: 0.72 },
];

const RINGS = [0.25, 0.5, 0.75, 1];

function blipStyle({ angle, distance }: (typeof BLIPS)[number]): CSSProperties {
  const radians = (angle * Math.PI) / 180;
  return {
    left: `${50 + distance * 50 * Math.sin(radians)}%`,
    top: `${50 - distance * 50 * Math.cos(radians)}%`,
    // Flare exactly when the sweep's leading edge reaches this angle.
    animationDelay: `${(angle / 360) * SWEEP_SECONDS}s`,
  };
}

/** The hero's backdrop: a radar scope in the accent colour, sweeping slowly. CSS only. */
export function RadarBackdrop() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div className="absolute top-[34%] left-1/2 aspect-square w-[1120px] -translate-x-1/2 -translate-y-1/2 [mask-image:radial-gradient(closest-side,black_45%,transparent)]">
        {RINGS.map((ring) => (
          <div
            key={ring}
            className="absolute rounded-full border border-yellow-deep/15"
            style={{ inset: `${(1 - ring) * 50}%` }}
          />
        ))}
        <div className="absolute inset-y-0 left-1/2 w-px bg-yellow-deep/10" />
        <div className="absolute inset-x-0 top-1/2 h-px bg-yellow-deep/10" />

        <div
          className="absolute inset-0 rounded-full motion-safe:animate-radar-sweep"
          style={{
            background:
              "conic-gradient(from 0turn, transparent 0turn 0.72turn, color-mix(in srgb, var(--color-yellow) 22%, transparent) 1turn)",
          }}
        />

        {BLIPS.map((blip) => (
          <span
            key={blip.angle}
            className="absolute -mt-1 -ml-1 size-2 rounded-full bg-yellow-deep opacity-25 motion-safe:animate-radar-blip"
            style={blipStyle(blip)}
          />
        ))}
      </div>
    </div>
  );
}
