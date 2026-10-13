import { cn } from "@/lib/utils";

export type MonoSpan = { text: string; tone?: "key" | "value" | "verdict" };

const toneClass: Record<NonNullable<MonoSpan["tone"]>, string> = {
  key: "text-ink-mute",
  value: "text-ink",
  verdict: "text-success",
};

/** Grey mono strip with a sample of what a stage produces. */
export function MonoSample({ sample, className }: { sample: readonly MonoSpan[]; className?: string }) {
  return (
    <span
      className={cn(
        "mt-auto block rounded-md bg-surface-alt px-2.5 py-2 font-mono text-[11px] leading-relaxed break-words whitespace-pre-wrap",
        className
      )}
    >
      {sample.map(({ text, tone }, index) => (
        <span key={index} className={tone && toneClass[tone]}>
          {text}
        </span>
      ))}
    </span>
  );
}
