import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Pill buttons. Primary / outline / danger carry an optional round "pill icon"
 * at the end (an arrow by default) that slides on hover and turns into a
 * spinner while `loading`. Keep one primary button per area.
 */
export const buttonVariants = cva(
  "group inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-full font-bold transition-colors disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary: "bg-ink text-surface hover:bg-ink-raised",
        outline: "border-[1.5px] border-ink bg-surface text-ink hover:bg-yellow-soft",
        danger:
          "border-[1.5px] border-danger bg-surface text-danger hover:bg-danger-badge",
        ghost: "text-ink-body hover:bg-surface-hover hover:text-ink",
        link: "rounded-sm px-0 text-ink underline decoration-ink/25 underline-offset-[3px] hover:decoration-ink",
      },
      size: {
        md: "min-h-10 px-[18px] text-[0.8125rem]",
        sm: "min-h-8 px-3.5 text-xs",
        icon: "size-8 text-ink-body",
      },
    },
    compoundVariants: [
      { variant: "link", size: "md", className: "min-h-0 px-0" },
      { variant: "link", size: "sm", className: "min-h-0 px-0" },
    ],
    defaultVariants: { variant: "primary", size: "md" },
  }
);

const pillIconVariants = cva(
  "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full text-ink",
  {
    variants: {
      variant: {
        primary: "bg-yellow",
        outline: "bg-yellow",
        danger: "bg-danger-badge text-danger",
        ghost: "bg-surface-track",
        link: "hidden",
      },
      size: { md: "size-7 text-sm", sm: "size-6 text-xs", icon: "hidden" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  /** Content of the round pill icon; pass null to hide it. Defaults to an arrow. */
  pillIcon?: React.ReactNode | null;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    className,
    variant = "primary",
    size = "md",
    pillIcon,
    loading = false,
    disabled,
    children,
    type = "button",
    ...props
  },
  ref
) {
  const showsPill =
    pillIcon !== null && size !== "icon" && variant !== "link" && variant !== "ghost";

  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        buttonVariants({ variant, size }),
        showsPill && (size === "sm" ? "pr-1" : "pr-1.5"),
        className
      )}
      {...props}
    >
      {children}
      {showsPill ? (
        <span aria-hidden className={pillIconVariants({ variant, size })}>
          {loading ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : (
            <span className="group-hover:animate-arrow-slide">{pillIcon ?? "→"}</span>
          )}
        </span>
      ) : loading ? (
        <Loader2 aria-hidden className="size-3.5 animate-spin" />
      ) : null}
    </button>
  );
});
