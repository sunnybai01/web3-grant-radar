import { CopilotChat } from "@copilotkit/react-ui";
import { X } from "lucide-react";
import React from "react";

import type { DashboardOpportunityItem } from "../types/chat";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";

type CopilotDrawerProps = {
  open: boolean;
  opportunity: DashboardOpportunityItem | null;
  onClose: () => void;
};

export default function CopilotDrawer({
  open,
  opportunity,
  onClose,
}: CopilotDrawerProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/30 backdrop-blur-[1px]">
      <button
        type="button"
        aria-label="Close copilot drawer"
        className="flex-1 cursor-default"
        onClick={onClose}
      />
      <aside className="flex h-full w-full max-w-2xl flex-col border-l border-border/70 bg-card/98 shadow-2xl backdrop-blur xl:max-w-3xl">
        <div className="flex items-start justify-between gap-4 border-b border-border/70 px-6 py-5">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Badge className="bg-primary/12 text-primary hover:bg-primary/12">
                Ask Copilot
              </Badge>
              {opportunity ? (
                <Badge variant="outline">#{opportunity.id}</Badge>
              ) : null}
            </div>
            <div>
              <h2 className="text-xl font-semibold tracking-[-0.03em] text-foreground">
                {opportunity?.title ?? "Grant Radar Copilot"}
              </h2>
              <p className="text-sm text-muted-foreground">
                {opportunity
                  ? `${opportunity.type} · ${opportunity.ecosystem ?? "-"} · score ${opportunity.score ?? "-"}`
                  : "Ask follow-up questions about the selected opportunity."}
              </p>
            </div>
          </div>
          <Button variant="outline" className="rounded-full" onClick={onClose}>
            <X className="mr-2 h-4 w-4" /> Close
          </Button>
        </div>

        <div className="flex-1 overflow-hidden p-6">
          <div className="h-full overflow-hidden rounded-3xl border border-border/70 bg-background/80">
            <CopilotChat
              className="h-full"
              labels={{
                title: "Grant Radar Copilot",
                initial:
                  "Ask about the selected opportunity, compare it against others in the visible table, or request a deeper prioritization rationale.",
                placeholder:
                  "Example: Why is this opportunity worth prioritizing this week?",
              }}
            />
          </div>
        </div>
      </aside>
    </div>
  );
}
