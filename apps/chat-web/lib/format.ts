const DAY_MS = 86_400_000;

export type DeadlineInfo = {
  /** Short relative label: "closes in 4d", "closes today", "rolling", "closed". */
  label: string;
  /** Exact date for tooltips, or null for rolling programmes. */
  exact: string | null;
  state: "urgent" | "open" | "rolling" | "closed";
  daysLeft: number | null;
};

const dateFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
  timeZone: "UTC",
});

const dateTimeFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : dateFormat.format(date);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : dateTimeFormat.format(date);
}

/** Deadlines inside this many days are urgent (rendered red). */
export const URGENT_DAYS = 7;

export function describeDeadline(iso: string | null, now: Date = new Date()): DeadlineInfo {
  if (!iso) return { label: "rolling", exact: null, state: "rolling", daysLeft: null };
  const deadline = new Date(iso);
  if (Number.isNaN(deadline.getTime())) {
    return { label: "rolling", exact: null, state: "rolling", daysLeft: null };
  }
  const exact = formatDate(iso);
  const diff = deadline.getTime() - now.getTime();
  if (diff < 0) return { label: "closed", exact, state: "closed", daysLeft: null };
  const daysLeft = Math.floor(diff / DAY_MS);
  const label = daysLeft === 0 ? "closes today" : `closes in ${daysLeft}d`;
  return { label, exact, state: daysLeft <= URGENT_DAYS ? "urgent" : "open", daysLeft };
}

/** "3m ago", "5h ago", "2d ago"; future times read "in 3h". */
export function formatRelative(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "never";
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return "—";
  const diff = now.getTime() - time;
  const abs = Math.abs(diff);
  const unit =
    abs < 60_000
      ? "now"
      : abs < 3_600_000
        ? `${Math.round(abs / 60_000)}m`
        : abs < DAY_MS
          ? `${Math.round(abs / 3_600_000)}h`
          : `${Math.round(abs / DAY_MS)}d`;
  if (unit === "now") return "just now";
  return diff >= 0 ? `${unit} ago` : `in ${unit}`;
}

/** Clock time for "Next scan at 21:00". */
export function formatClock(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

export function formatScore(score: number | null | undefined): string {
  return score === null || score === undefined ? "—" : score.toFixed(1);
}

export function formatAmount(amount: string | null | undefined): string {
  const trimmed = (amount ?? "").trim();
  return trimmed && trimmed !== "-" ? trimmed : "Amount not stated";
}

export function formatType(type: string): string {
  const lower = type.toLowerCase();
  return lower ? lower[0].toUpperCase() + lower.slice(1) : "Opportunity";
}

export function formatChain(ecosystem: string | null | undefined): string {
  return (ecosystem ?? "").trim().toUpperCase() || "UNKNOWN CHAIN";
}
