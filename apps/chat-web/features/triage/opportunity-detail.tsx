"use client";

import { MoreHorizontal, RotateCcw, Trash2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Eyebrow, MonoLabel, ValueStrip } from "@/components/ui/mono-label";
import { copy } from "@/lib/copy";
import { describeDeadline, formatAmount, formatChain, formatDate, formatScore, formatType } from "@/lib/format";
import { useOpportunity } from "@/lib/queries";
import { verificationLabel, verificationTone } from "@/lib/status-tone";
import { cn } from "@/lib/utils";
import type { DashboardOpportunityItem, TriageStatus } from "@/types/chat";

import { CopilotTab } from "../copilot/copilot-tab";
import { VerificationTab } from "../verification/verification-tab";
import { OverviewTab } from "./overview-tab";

type DetailTab = "overview" | "verification" | "copilot";
const TABS: DetailTab[] = ["overview", "verification", "copilot"];

export function OpportunityDetail({
  item,
  pending,
  onTriage,
  onDelete,
}: {
  item: DashboardOpportunityItem;
  pending: boolean;
  onTriage: (status: TriageStatus) => void;
  onDelete: () => Promise<boolean>;
}) {
  const [tab, setTab] = useState<DetailTab>("overview");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const detail = useOpportunity(item.id);
  const deadline = describeDeadline(item.deadline, undefined, { rolling: item.rolling });
  const official = item.source_trust === "official";

  return (
    <article aria-label={item.title} className="flex flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Eyebrow>
          {formatType(item.type)} · {formatChain(item.ecosystem)} ·{" "}
          {official ? copy.detail.officialSource : copy.detail.discoverySource}
        </Eyebrow>
        <MonoLabel>
          #{item.id}
          {item.first_seen ? ` · ${copy.detail.firstSeen(formatDate(item.first_seen))}` : ""}
        </MonoLabel>
      </div>

      <h2 className="mt-1.5 text-[1.2rem] leading-snug font-bold tracking-tight text-ink">{item.title}</h2>
      {item.summary ? (
        <p className="mt-1 line-clamp-2 text-[0.8125rem] leading-relaxed text-ink-body">{item.summary}</p>
      ) : null}

      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <ValueStrip label={copy.detail.facts.amount} wrap>
          {formatAmount(item.amount, item.amount_usd)}
        </ValueStrip>
        <ValueStrip
          label={copy.detail.facts.deadline}
          valueClassName={cn(
            deadline.state === "urgent" && "text-danger",
            deadline.state === "closed" && "text-ink-mute line-through",
            deadline.state === "unknown" && "text-ink-mute"
          )}
        >
          <span title={deadline.exact ?? undefined}>
            {deadline.exact ? `${deadline.exact} · ${deadline.label.replace("closes in ", "")}` : deadline.label}
          </span>
        </ValueStrip>
        <ValueStrip label={copy.detail.facts.score}>
          {formatScore(item.score)}
          {item.score !== null ? <span className="text-ink-mute"> / 10</span> : null}
        </ValueStrip>
        <div className="rounded-md bg-surface-alt px-2.5 py-2">
          <MonoLabel as="div">{copy.detail.facts.verification}</MonoLabel>
          <Badge className="mt-1.5" tone={verificationTone(item.verification_verdict, item.verified)}>
            {verificationLabel(item.verification_verdict, item.verified)}
          </Badge>
        </div>
        <ValueStrip label={copy.detail.facts.seenIn}>{copy.detail.seenIn(item.source_count)}</ValueStrip>
        <ValueStrip label={copy.detail.facts.heat}>{copy.detail.heat(item.heat)}</ValueStrip>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {item.triage_status === "shortlisted" ? (
          <Badge tone="highlight" className="px-3 py-2 text-[11px]">✓ {copy.detail.actions.shortlisted}</Badge>
        ) : (
          <Button onClick={() => onTriage("shortlisted")} loading={pending}>
            {copy.detail.actions.shortlist}
          </Button>
        )}
        {item.apply_url ? (
          <a
            href={item.apply_url}
            target="_blank"
            rel="noreferrer"
            className={cn(buttonVariants({ variant: "outline" }), "pr-1.5")}
          >
            {copy.detail.actions.openApply}
            <span aria-hidden className="inline-flex size-7 items-center justify-center rounded-full bg-yellow text-sm text-ink">
              ↗
            </span>
          </a>
        ) : null}
        {item.source_url ? (
          <a
            href={item.source_url}
            target="_blank"
            rel="noreferrer"
            className={buttonVariants({ variant: "link" })}
          >
            {copy.detail.actions.openSource} ↗
          </a>
        ) : null}
        {item.triage_status === "dismissed" ? (
          <Button variant="link" onClick={() => onTriage("new")}>
            {copy.detail.actions.moveToNew}
          </Button>
        ) : (
          <Button variant="link" onClick={() => onTriage("dismissed")} disabled={pending}>
            {copy.detail.actions.dismiss}
          </Button>
        )}
        <span className="flex-1" />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={copy.detail.actions.more}>
              <MoreHorizontal aria-hidden className="size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            {item.triage_status !== "new" ? (
              <>
                <DropdownMenuItem onSelect={() => onTriage("new")}>
                  <RotateCcw aria-hidden /> {copy.detail.actions.moveToNew}
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            ) : null}
            <DropdownMenuItem destructive onSelect={() => setConfirmDelete(true)}>
              <Trash2 aria-hidden /> {copy.detail.actions.delete}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div role="tablist" aria-label="Opportunity details" className="mt-5 flex gap-5 border-b border-line">
        {TABS.map((value) => (
          <button
            key={value}
            id={`detail-tab-${value}`}
            type="button"
            role="tab"
            aria-selected={tab === value}
            aria-controls={`detail-panel-${value}`}
            tabIndex={tab === value ? 0 : -1}
            onClick={() => setTab(value)}
            onKeyDown={(event) => {
              const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
              if (!delta) return;
              const next = TABS[(TABS.indexOf(value) + delta + TABS.length) % TABS.length];
              setTab(next);
              document.getElementById(`detail-tab-${next}`)?.focus();
            }}
            className={cn(
              "-mb-px border-b-2 py-2 text-[0.8125rem] font-semibold transition-colors",
              tab === value ? "border-yellow text-ink" : "border-transparent text-ink-mute hover:text-ink"
            )}
          >
            {copy.detail.tabs[value]}
          </button>
        ))}
      </div>

      <div className="pt-4">
        <div id="detail-panel-overview" role="tabpanel" aria-labelledby="detail-tab-overview" hidden={tab !== "overview"}>
          <OverviewTab item={item} detail={detail.data} loading={detail.isLoading} />
        </div>
        <div id="detail-panel-verification" role="tabpanel" aria-labelledby="detail-tab-verification" hidden={tab !== "verification"}>
          {tab === "verification" ? <VerificationTab eventId={item.id} /> : null}
        </div>
        {/* Stays mounted so the conversation survives tab and row switches. */}
        <div id="detail-panel-copilot" role="tabpanel" aria-labelledby="detail-tab-copilot" hidden={tab !== "copilot"}>
          <CopilotTab eventId={item.id} />
        </div>
      </div>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogTitle className="text-[1.05rem] font-semibold text-ink">{copy.deleteDialog.title}</DialogTitle>
          <DialogDescription className="mt-2 text-[0.8125rem] leading-relaxed text-ink-body">
            <span className="mb-2 block font-semibold text-ink">{item.title}</span>
            {copy.deleteDialog.body}
          </DialogDescription>
          <div className="mt-5 flex items-center justify-end gap-3">
            <DialogClose asChild>
              <Button variant="link">{copy.deleteDialog.cancel}</Button>
            </DialogClose>
            <Button
              variant="danger"
              pillIcon="!"
              loading={deleting}
              onClick={async () => {
                setDeleting(true);
                const ok = await onDelete();
                setDeleting(false);
                if (ok) setConfirmDelete(false);
              }}
            >
              {copy.deleteDialog.confirm}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </article>
  );
}
