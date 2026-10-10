"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ExternalLink } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MonoLabel, ValueStrip } from "@/components/ui/mono-label";
import { copy } from "@/lib/copy";
import { capitalize, trustTone, verificationTone } from "@/lib/status-tone";
import { cn } from "@/lib/utils";
import type { InvestigationResponse, MixedModeResult } from "@/types/chat";

import { runVerification, verificationKey, type Settled } from "./run-verification";

const STEP_LABELS: Record<string, string> = {
  load_event: "Load event",
  retrieve_similar_events: "Retrieve similar events",
  fetch_supporting_evidence: "Fetch supporting evidence",
  verify_event: "Verification",
  finalize_conclusion: "Finalize conclusion",
};

const STEP_DESCRIPTIONS: Record<string, string> = {
  load_event: "Loaded the selected opportunity from the event store.",
  retrieve_similar_events: "Checked historical signals for nearby matches and repeated patterns.",
  fetch_supporting_evidence: "Captured page-level evidence from the application or source URL.",
  verify_event: "Ran deterministic verification checks before forming a recommendation.",
  finalize_conclusion: "Compressed the gathered evidence into a final action recommendation.",
};

/** Runs only on request; results stay cached per opportunity for the session. */
export function VerificationTab({ eventId }: { eventId: number }) {
  const run = useQuery({
    queryKey: verificationKey(eventId),
    queryFn: () => runVerification(eventId),
    enabled: false,
    staleTime: Infinity,
    gcTime: Infinity,
    retry: 0,
  });

  const result = run.data;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-[60ch] text-[0.8125rem] leading-relaxed text-ink-body">{copy.verification.intro}</p>
        <Button size="sm" variant={result ? "outline" : "primary"} loading={run.isFetching} onClick={() => void run.refetch()}>
          {result ? copy.verification.rerun : copy.verification.run}
        </Button>
      </div>

      {run.isFetching && !result ? (
        <p role="status" className="text-[0.8125rem] text-ink-body">
          {copy.verification.running}
        </p>
      ) : null}

      {result ? (
        <>
          <DigestSection digest={result.digest} />
          <InvestigationSection investigation={result.investigation} />
        </>
      ) : null}
    </div>
  );
}

function ErrorBanner({ title, error }: { title: string; error: string }) {
  return (
    <div role="alert" className="flex gap-3 rounded-lg border-[1.5px] border-danger/45 bg-danger-surface p-3.5">
      <span aria-hidden className="inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-danger text-[11px] font-bold text-surface">
        ✕
      </span>
      <div className="min-w-0">
        <p className="text-[0.875rem] font-semibold text-danger">{title}</p>
        <p className="mt-0.5 font-mono text-[11px] break-words text-ink-body">reason: {error}</p>
      </div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <MonoLabel as="h3" className="mb-2">{children}</MonoLabel>;
}

function DigestSection({ digest }: { digest: Settled<MixedModeResult> }) {
  if (!digest.ok) return <ErrorBanner title={copy.verification.failed} error={digest.error} />;
  const { verification, options } = digest.value;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-2">
        <ValueStrip label={copy.verification.confidence}>{verification.score}</ValueStrip>
        <ValueStrip label={copy.verification.level}>{capitalize(verification.level ?? "—")}</ValueStrip>
        <div className="rounded-md bg-surface-alt px-2.5 py-2">
          <MonoLabel as="div">{copy.verification.verdict}</MonoLabel>
          <Badge className="mt-1.5" tone={trustTone(verification.verdict)}>
            {verification.verdict}
          </Badge>
        </div>
      </div>

      <section>
        <SectionTitle>{copy.verification.evidence}</SectionTitle>
        {(verification.evidence ?? []).length ? (
          <ul className="space-y-1.5">
            {(verification.evidence ?? []).map((item, index) => (
              <li key={`${item.category}-${index}`} className="rounded-md border border-line px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[11px] text-ink-body uppercase">{item.category ?? "evidence"}</span>
                  {item.impact ? (
                    <Badge tone={item.impact === "positive" ? "success" : item.impact === "negative" ? "danger" : "neutral"}>
                      {item.impact}
                    </Badge>
                  ) : null}
                </div>
                {item.detail ? <p className="mt-1 text-[0.8125rem] text-ink">{item.detail}</p> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[0.8125rem] text-ink-mute">{copy.verification.noEvidence}</p>
        )}
      </section>

      <div className="grid gap-4 sm:grid-cols-2">
        <BulletList title={copy.verification.unknowns} items={verification.unknowns} empty={copy.verification.noUnknowns} />
        <BulletList title={copy.verification.conflicts} items={verification.conflicts} empty={copy.verification.noConflicts} />
      </div>

      {options.options?.length ? (
        <section>
          <SectionTitle>{copy.verification.paths}</SectionTitle>
          <div className="grid gap-2 sm:grid-cols-2">
            {options.options.map((option) => (
              <div key={option.tier} className="rounded-md border border-line p-3">
                <MonoLabel as="div" className="text-yellow-deep">{option.tier}</MonoLabel>
                <p className="mt-1 text-[0.8125rem] text-ink">{option.summary}</p>
                {option.assumptions.length ? (
                  <ul className="mt-1.5 space-y-0.5 text-[12px] text-ink-body">
                    {option.assumptions.map((assumption) => (
                      <li key={assumption}>– {assumption}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function BulletList({ title, items, empty }: { title: string; items?: string[]; empty: string }) {
  return (
    <section>
      <SectionTitle>{title}</SectionTitle>
      {items?.length ? (
        <ul className="space-y-1 text-[0.8125rem] text-ink">
          {items.map((item) => (
            <li key={item} className="flex gap-2">
              <span aria-hidden className="text-ink-mute">–</span>
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[0.8125rem] text-ink-mute">{empty}</p>
      )}
    </section>
  );
}

export function InvestigationSection({ investigation }: { investigation: Settled<InvestigationResponse> }) {
  const [stepsOpen, setStepsOpen] = useState(false);
  if (!investigation.ok) return <ErrorBanner title={copy.verification.investigationFailed} error={investigation.error} />;
  const { conclusion, trajectory, error } = investigation.value;

  return (
    <section className="space-y-4 border-t border-line pt-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[0.875rem] font-semibold text-ink">{copy.verification.investigation}</h3>
        {conclusion ? (
          <div className="flex items-center gap-1.5">
            <Badge tone={verificationTone(conclusion.verdict, false)}>{conclusion.verdict}</Badge>
            <Badge tone="highlight">{conclusion.recommended_action}</Badge>
          </div>
        ) : null}
      </div>

      {error ? <ErrorBanner title={copy.verification.investigationFailed} error={error} /> : null}
      {conclusion?.summary ? <p className="text-[0.8125rem] leading-relaxed text-ink">{conclusion.summary}</p> : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <section>
          <SectionTitle>{copy.verification.similar}</SectionTitle>
          {conclusion?.similar_events.length ? (
            <ul className="space-y-1">
              {conclusion.similar_events.map((event) => (
                <li key={event.event_id} className="flex items-baseline justify-between gap-2 text-[0.8125rem]">
                  <span className="truncate text-ink">{event.title}</span>
                  <span className="shrink-0 font-mono text-[11px] text-ink-mute">
                    {copy.verification.similarity(event.similarity)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[0.8125rem] text-ink-mute">{copy.verification.noSimilar}</p>
          )}
        </section>
        <section>
          <SectionTitle>{copy.verification.evidencePage}</SectionTitle>
          {conclusion?.supporting_evidence ? (
            <div className="text-[0.8125rem]">
              <a
                href={conclusion.supporting_evidence.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 font-semibold text-ink underline decoration-ink/25 underline-offset-[3px] hover:decoration-ink"
              >
                {conclusion.supporting_evidence.title}
                <ExternalLink aria-hidden className="size-3" />
              </a>
              <p className="mt-1 text-ink-body">{conclusion.supporting_evidence.excerpt}</p>
            </div>
          ) : (
            <p className="text-[0.8125rem] text-ink-mute">{copy.verification.noEvidencePage}</p>
          )}
        </section>
      </div>

      <div>
        <button
          type="button"
          aria-expanded={stepsOpen}
          onClick={() => setStepsOpen((open) => !open)}
          className="inline-flex items-center gap-1.5 text-[0.8125rem] font-semibold text-ink"
        >
          <ChevronDown aria-hidden className={cn("size-4 transition-transform", !stepsOpen && "-rotate-90")} />
          {copy.verification.steps}
          <span className="rounded-full bg-surface-alt px-1.5 font-mono text-[11px] text-ink-body">{trajectory.length}</span>
        </button>
        {stepsOpen ? (
          trajectory.length ? (
            <ol className="mt-2 space-y-2">
              {trajectory.map((step) => (
                <li key={`${step.step_index}-${step.action}`} className="rounded-md border border-line p-3">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex size-6 items-center justify-center rounded-full border-[1.5px] border-line-strong font-mono text-[10px] text-ink">
                      {String(step.step_index).padStart(2, "0")}
                    </span>
                    <span className="text-[0.8125rem] font-semibold text-ink">{STEP_LABELS[step.action] ?? step.action}</span>
                  </div>
                  {STEP_DESCRIPTIONS[step.action] ? (
                    <p className="mt-1.5 text-[12px] text-ink-body">{STEP_DESCRIPTIONS[step.action]}</p>
                  ) : null}
                  {step.thought ? <p className="mt-1 text-[12px] text-ink-body">{step.thought}</p> : null}
                  <div className="mt-2 grid gap-2 md:grid-cols-2">
                    <JsonBlock label={copy.verification.stepInput} value={step.action_input} />
                    <JsonBlock label={copy.verification.stepObservation} value={step.observation} />
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-2 text-[0.8125rem] text-ink-mute">{copy.verification.noSteps}</p>
          )
        ) : null}
      </div>
    </section>
  );
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-w-0">
      <MonoLabel as="div">{label}</MonoLabel>
      <pre className="mt-1 max-h-48 overflow-auto rounded-md bg-surface-alt p-2 font-mono text-[11px] text-ink-body">
        {JSON.stringify(value ?? {}, null, 2)}
      </pre>
    </div>
  );
}
