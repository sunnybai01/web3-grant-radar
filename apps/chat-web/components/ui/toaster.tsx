"use client";

import { Toaster as Sonner } from "sonner";

export function Toaster() {
  return (
    <Sonner
      position="top-center"
      toastOptions={{
        classNames: {
          toast:
            "!rounded-lg !border !border-line-strong !bg-surface !font-sans !text-[0.8125rem] !text-ink !shadow-panel",
          description: "!text-ink-body",
          actionButton: "!bg-ink !text-surface !rounded-full !font-bold",
          error: "!border-danger/40",
          success: "!border-success/35",
        },
      }}
    />
  );
}
