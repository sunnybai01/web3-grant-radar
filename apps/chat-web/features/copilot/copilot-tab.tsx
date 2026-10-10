"use client";

import { CopilotChat } from "@copilotkit/react-ui";

import { MonoLabel } from "@/components/ui/mono-label";
import { copy } from "@/lib/copy";

/**
 * One conversation for the whole session. It always answers about the
 * currently selected opportunity, which the copilot reads through
 * getDashboardContext.
 */
export function CopilotTab({ eventId }: { eventId: number }) {
  return (
    <div className="flex h-[min(560px,65vh)] flex-col">
      <MonoLabel as="p" className="mb-2">
        {copy.copilot.asking(eventId)}
      </MonoLabel>
      <div className="min-h-0 flex-1 overflow-hidden rounded-lg border border-line bg-surface">
        <CopilotChat
          className="h-full"
          labels={{
            title: copy.copilot.title,
            initial: copy.copilot.initial,
            placeholder: copy.copilot.placeholder,
          }}
        />
      </div>
    </div>
  );
}
