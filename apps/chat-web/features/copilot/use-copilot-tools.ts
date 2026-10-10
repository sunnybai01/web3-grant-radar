"use client";

import { useFrontendTool } from "@copilotkit/react-core/v2";
import { useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { runMixedModeVerification } from "@/lib/actions";
import { client } from "@/lib/client";
import type { DashboardOpportunitiesResponse, DashboardOpportunityItem, OpportunityFilters } from "@/types/chat";

import { verificationKey, type VerificationRun } from "../verification/run-verification";
import { normalizeAnalysisTargetInput } from "./analysis-target";

const analysisToolSchema = z.object({
  eventId: z.number().optional(),
  sourceName: z.string().optional(),
  from: z.string().optional(),
  to: z.string().optional(),
  limit: z.number().optional(),
});

const dashboardContextToolSchema = z.object({
  includeRows: z.boolean().optional(),
  rowLimit: z.number().min(1).max(20).optional(),
});

/**
 * Tools the copilot can call on the triage page. Tool names are part of the
 * system prompt in app/api/copilotkit/route.ts; keep them in sync.
 */
export function useCopilotTools({
  filters,
  listing,
  selected,
}: {
  filters: OpportunityFilters;
  listing: DashboardOpportunitiesResponse | undefined;
  selected: DashboardOpportunityItem | null;
}) {
  const queryClient = useQueryClient();

  useFrontendTool(
    {
      name: "analyzeDatabaseTargets",
      description:
        "Load opportunity records from the database, verify their reliability, and prepare grounded implementation options. Defaults to the selected opportunity.",
      parameters: analysisToolSchema,
      handler: async (input) => {
        const target = normalizeAnalysisTargetInput(input, selected?.id);
        const data = await runMixedModeVerification(client, target);

        // Share the result with the Verification tab of that opportunity.
        if (target.event_id !== undefined) {
          queryClient.setQueryData<VerificationRun>(verificationKey(target.event_id), (previous) => ({
            digest: { ok: true, value: data },
            investigation: previous?.investigation ?? { ok: false, error: "Not run yet. Use Run verification." },
          }));
        }

        return {
          target: input,
          selectedEventIds: data.selected.target_event_ids,
          verification: data.verification,
          options: data.options.options,
        };
      },
    },
    [selected, queryClient]
  );

  useFrontendTool(
    {
      name: "getDashboardContext",
      description:
        "Read the current triage view: status tab, filters, board stats, the selected opportunity and optionally the visible rows.",
      parameters: dashboardContextToolSchema,
      handler: async (input) => {
        const context: Record<string, unknown> = {
          page: "triage",
          statusTab: filters.status,
          filters,
          counts: listing?.counts,
          metrics: listing?.metrics,
          selectedOpportunity: selected,
        };
        if (input.includeRows) {
          context.visibleRows = (listing?.items ?? []).slice(0, input.rowLimit ?? 5).map((item) => ({
            id: item.id,
            score: item.score,
            type: item.type,
            title: item.title,
            ecosystem: item.ecosystem,
            amount: item.amount,
            deadline: item.deadline,
            verification_verdict: item.verification_verdict,
            source_trust: item.source_trust,
            triage_status: item.triage_status,
          }));
        }
        return context;
      },
    },
    [filters, listing, selected]
  );
}
