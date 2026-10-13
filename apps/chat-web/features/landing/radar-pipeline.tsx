import { Badge } from "@/components/ui/badge";
import { copy } from "@/lib/copy";
import { cn } from "@/lib/utils";

const flow = copy.landing.flow;

// Source chips and the fan-in curves share this grid, so the curves start at the chips.
const CHIP_HEIGHT = 30;
const CHIP_GAP = 8;
const FAN_HEIGHT = flow.sources.length * CHIP_HEIGHT + (flow.sources.length - 1) * CHIP_GAP;
const fanPath = (index: number) => {
  const y = CHIP_HEIGHT / 2 + index * (CHIP_HEIGHT + CHIP_GAP);
  return `M0 ${y} C36 ${y} 36 ${FAN_HEIGHT / 2} 64 ${FAN_HEIGHT / 2}`;
};

function Connector({ delay }: { delay: number }) {
  return (
    <svg width="36" height="12" viewBox="0 0 36 12" aria-hidden className="shrink-0 text-ink-mute">
      <line x1="0" y1="6" x2="28" y2="6" stroke="currentColor" strokeWidth="1" />
      <path d="M28 2 L35 6 L28 10 Z" fill="currentColor" />
      <circle
        cx="3"
        cy="6"
        r="2.5"
        className="fill-yellow-deep opacity-0 motion-safe:animate-flow-x"
        style={{ animationDelay: `${delay}ms` }}
      />
    </svg>
  );
}

function ConnectorDown({ delay }: { delay: number }) {
  return (
    <svg width="12" height="22" viewBox="0 0 12 22" aria-hidden className="shrink-0 text-ink-mute">
      <line x1="6" y1="0" x2="6" y2="15" stroke="currentColor" strokeWidth="1" />
      <path d="M2 14 L6 21 L10 14 Z" fill="currentColor" />
      <circle
        cx="6"
        cy="3"
        r="2"
        className="fill-yellow-deep opacity-0 motion-safe:animate-flow-y"
        style={{ animationDelay: `${delay}ms` }}
      />
    </svg>
  );
}

function FanIn() {
  return (
    <svg
      width="72"
      height={FAN_HEIGHT}
      viewBox={`0 0 72 ${FAN_HEIGHT}`}
      aria-hidden
      className="shrink-0 text-ink-mute"
    >
      {flow.sources.map((source, index) => (
        <path key={source} d={fanPath(index)} fill="none" stroke="currentColor" strokeWidth="1" />
      ))}
      <path d={`M64 ${FAN_HEIGHT / 2 - 4} L71 ${FAN_HEIGHT / 2} L64 ${FAN_HEIGHT / 2 + 4} Z`} fill="currentColor" />
      {flow.sources.map((source, index) => (
        <circle
          key={source}
          r="2.5"
          className="fill-yellow-deep opacity-0 motion-safe:animate-flow-path"
          style={{ offsetPath: `path('${fanPath(index)}')`, animationDelay: `${index * 300}ms` }}
        />
      ))}
    </svg>
  );
}

/** The pipeline as one sealed box, its name on a tab over the top border. */
function SealedBox({ label, className }: { label: string; className?: string }) {
  return (
    <div className={cn("relative rounded-xl border-[1.5px] border-ink bg-surface px-5 pt-[22px] pb-4 text-left", className)}>
      <span className="absolute -top-[11px] left-4 rounded-md bg-ink px-2.5 py-[3px] font-mono text-[10px] text-white">
        {label}
      </span>
      <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono text-[13px] text-ink">
        {flow.stages.map((stage, index) => (
          <li key={stage} className="flex items-center gap-2">
            {index > 0 ? <span aria-hidden className="text-ink-mute">→</span> : null}
            {stage}
          </li>
        ))}
      </ol>
    </div>
  );
}

function OpportunityCard({ className }: { className?: string }) {
  const card = flow.card;
  return (
    <div className={cn("rounded-xl border border-line bg-surface p-4 text-left shadow-panel", className)}>
      <div className="flex items-center gap-2">
        <Badge tone="neutral">{card.type}</Badge>
        <span className="font-mono text-[11px] text-ink-mute">{card.chain}</span>
        <span className="ml-auto font-mono text-sm font-semibold tabular-nums text-ink">{card.score}</span>
      </div>
      <p className="mt-2.5 text-sm font-semibold text-ink">{card.title}</p>
      <p className="mt-1 font-mono text-[11px] text-ink-body">
        {card.reward} · {card.deadline}
      </p>
      <Badge tone="success" className="mt-3">
        ✓ {card.verified}
      </Badge>
    </div>
  );
}

function Verdict() {
  return (
    <div className="flex flex-col items-center gap-2.5">
      <span className="grid size-[84px] place-items-center rounded-full bg-yellow font-mono text-[12px] font-medium text-ink">
        {flow.verdict}
      </span>
      <span className="max-w-[140px] text-center font-mono text-[10px] leading-relaxed text-ink-mute">
        {flow.verdictNote}
      </span>
      <span className="font-mono text-xs font-medium text-success">{flow.delivered}</span>
    </div>
  );
}

const chipClass =
  "inline-flex items-center rounded-lg border border-line bg-surface px-3 font-mono text-[12px] leading-none text-ink";

/** The hero diagram: sources fan into the pipeline, out comes one scored opportunity. */
export function RadarPipeline() {
  return (
    <div className="mt-12 md:mt-[72px]" aria-hidden>
      <div className="mx-auto hidden items-center justify-center gap-3.5 min-[1180px]:flex">
        <div className="flex flex-col items-end" style={{ gap: CHIP_GAP }}>
          {flow.sources.map((source) => (
            <span key={source} className={chipClass} style={{ height: CHIP_HEIGHT }}>
              {source}
            </span>
          ))}
        </div>
        <FanIn />
        <SealedBox label={flow.pipelineLabel} />
        <Connector delay={0} />
        <OpportunityCard className="w-[264px]" />
        <Connector delay={500} />
        <Verdict />
      </div>

      <div className="mx-auto flex max-w-[420px] flex-col items-center gap-2 min-[1180px]:hidden">
        <div className="flex flex-wrap justify-center gap-1.5">
          {flow.sources.map((source) => (
            <span key={source} className={cn(chipClass, "h-7 text-[11px]")}>
              {source}
            </span>
          ))}
        </div>
        <ConnectorDown delay={0} />
        <SealedBox label={flow.pipelineLabel} className="w-full" />
        <ConnectorDown delay={250} />
        <OpportunityCard className="w-full" />
        <ConnectorDown delay={500} />
        <Verdict />
      </div>
    </div>
  );
}
