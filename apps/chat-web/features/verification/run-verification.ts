import { runMixedModeVerification } from "@/lib/actions";
import { client } from "@/lib/client";
import { runInvestigation } from "@/lib/investigation";
import type { InvestigationResponse, MixedModeResult } from "@/types/chat";

export type Settled<T> = { ok: true; value: T } | { ok: false; error: string };

export type VerificationRun = {
  digest: Settled<MixedModeResult>;
  investigation: Settled<InvestigationResponse>;
};

export const verificationKey = (eventId: number) => ["verification", eventId] as const;

function settle<T>(result: PromiseSettledResult<T>, fallback: string): Settled<T> {
  if (result.status === "fulfilled") return { ok: true, value: result.value };
  const reason = result.reason as { response?: { data?: { detail?: string; error?: string } }; message?: string };
  return {
    ok: false,
    error: reason?.response?.data?.detail || reason?.response?.data?.error || reason?.message || fallback,
  };
}

/**
 * The digest (trust score, evidence, ways to take part) and the investigation
 * (history and supporting page) run side by side; one failing does not hide
 * the other.
 */
export async function runVerification(eventId: number): Promise<VerificationRun> {
  const [digest, investigation] = await Promise.allSettled([
    runMixedModeVerification(client, { event_id: eventId }),
    runInvestigation(client, eventId),
  ]);
  return {
    digest: settle(digest, "Verification request failed."),
    investigation: settle(investigation, "Investigation request failed."),
  };
}
