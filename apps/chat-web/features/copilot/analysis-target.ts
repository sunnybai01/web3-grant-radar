import type { AnalysisTargetInput } from "@/types/chat";

const isoDatePattern = /^\d{4}-\d{2}-\d{2}(?:[T\s].*)?$/;

function normalizeDateValue(value?: string) {
  const trimmed = value?.trim();
  return trimmed && isoDatePattern.test(trimmed) ? trimmed : undefined;
}

/**
 * Turn the copilot's tool arguments into a select-targets request: an explicit
 * or selected event id wins; otherwise a source name plus an ISO date range.
 */
export function normalizeAnalysisTargetInput(
  input: { eventId?: number; sourceName?: string; from?: string; to?: string; limit?: number },
  fallbackEventId?: number
): AnalysisTargetInput {
  const eventId = input.eventId ?? fallbackEventId;
  if (eventId !== undefined) return { event_id: eventId };

  const sourceName = input.sourceName?.trim();
  const from = normalizeDateValue(input.from);
  const to = normalizeDateValue(input.to);
  if (!sourceName || !from || !to) return {};

  const normalized: AnalysisTargetInput = { source_name: sourceName, from, to };
  if (typeof input.limit === "number") {
    normalized.limit = Math.min(100, Math.max(1, Math.trunc(input.limit)));
  }
  return normalized;
}
