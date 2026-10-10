"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;
export const DialogTitle = DialogPrimitive.Title;
export const DialogDescription = DialogPrimitive.Description;

function Overlay() {
  return <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ink/30 backdrop-blur-[2px]" />;
}

/** Centred modal panel. Radix handles focus trap, Escape and focus return. */
export function DialogContent({
  className,
  children,
  ...props
}: React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      <Overlay />
      <DialogPrimitive.Content
        className={cn(
          "fixed top-1/2 left-1/2 z-50 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-line bg-surface p-6 shadow-dropdown focus:outline-none",
          className
        )}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

/** Full-screen sheet, used for the opportunity detail on phone widths. */
export function SheetContent({
  className,
  children,
  title,
  ...props
}: React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & { title: string }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Content
        className={cn("fixed inset-0 z-50 flex flex-col bg-surface-alt focus:outline-none", className)}
        {...props}
      >
        <div className="flex items-center gap-2 border-b border-line bg-surface px-3 py-2">
          <DialogPrimitive.Close
            className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-[0.8125rem] font-bold text-ink hover:bg-surface-hover"
          >
            <X aria-hidden className="size-4" /> Back to list
          </DialogPrimitive.Close>
          <DialogPrimitive.Title className="sr-only">{title}</DialogPrimitive.Title>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
