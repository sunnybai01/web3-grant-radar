const DAY_MS = 86_400_000;

export type DeadlineInfo = {
  /** Short relative label: "closes in 4d", "closes today", "rolling", "deadline not stated", "closed". */
  label: string;
  /** Exact date for tooltips, or null when there is no deadline. */
  exact: string | null;
  state: "urgent" | "open" | "rolling" | "unknown" | "closed";
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

/** A date-only deadline (stored as 00:00 UTC) lasts through that day anywhere on earth (UTC-12). */
const END_OF_DAY_ANYWHERE_MS = 36 * 3_600_000;

function isDateOnly(date: Date): boolean {
  return date.getUTCHours() === 0 && date.getUTCMinutes() === 0 && date.getUTCSeconds() === 0 && date.getUTCMilliseconds() === 0;
}

function utcDayNumber(date: Date): number {
  return Math.floor(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()) / DAY_MS);
}

export function describeDeadline(
  iso: string | null,
  now: Date = new Date(),
  { rolling = false }: { rolling?: boolean } = {}
): DeadlineInfo {
  const deadline = iso ? new Date(iso) : null;
  if (!deadline || Number.isNaN(deadline.getTime())) {
    return rolling
      ? { label: "rolling", exact: null, state: "rolling", daysLeft: null }
      : { label: "deadline not stated", exact: null, state: "unknown", daysLeft: null };
  }
  const exact = formatDate(iso);
  const dateOnly = isDateOnly(deadline);
  const end = deadline.getTime() + (dateOnly ? END_OF_DAY_ANYWHERE_MS : 0);
  if (end < now.getTime()) return { label: "closed", exact, state: "closed", daysLeft: null };
  const daysLeft = dateOnly
    ? Math.max(0, utcDayNumber(deadline) - utcDayNumber(now))
    : Math.floor((end - now.getTime()) / DAY_MS);
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

/** "$3.9M", "$62K", "$800": an estimate, so two significant figures are plenty. */
function usdShort(value: number): string {
  for (const [divisor, suffix] of [[1e9, "B"], [1e6, "M"], [1e3, "K"]] as const) {
    if (value >= divisor) {
      const scaled = value / divisor;
      return `$${scaled < 10 ? Number(scaled.toPrecision(2)) : Math.round(scaled)}${suffix}`;
    }
  }
  return `$${Math.round(value)}`;
}

/** A ticker other than USD ("OP", "APT", "USDC") means part of the amount is not in dollars. */
const NON_USD_TICKER = /\b(?!USD\b)[A-Z]{2,6}\b/;

/** The stated amount, with a USD estimate unless it is already a plain dollar figure. */
export function formatAmount(amount: string | null | undefined, amountUsd?: number | null): string {
  const trimmed = (amount ?? "").trim();
  if (!trimmed || trimmed === "-") return "Amount not stated";
  const plainDollars = trimmed.startsWith("$") && !NON_USD_TICKER.test(trimmed);
  return amountUsd && !plainDollars && !trimmed.includes("≈") ? `${trimmed} (≈ ${usdShort(amountUsd)})` : trimmed;
}

export function formatType(type: string): string {
  const lower = type.toLowerCase();
  return lower ? lower[0].toUpperCase() + lower.slice(1) : "Opportunity";
}

export function formatChain(ecosystem: string | null | undefined): string {
  return (ecosystem ?? "").trim().toUpperCase() || "UNKNOWN CHAIN";
}
