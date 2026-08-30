import { forwardRef } from "react";
import type { ComponentPropsWithoutRef, ReactNode } from "react";
import { cn } from "./cn";

/* Badge.
 *
 * Status, carried by colour and reinforced by a border so it survives being
 * read on a projector, in dark mode, or by someone who does not separate red
 * from green. Soft fill + matching border + matching text, never a saturated
 * block - on a screen this dense, a dozen solid pills read as an alarm.
 */

export type BadgeTone =
  | "neutral" | "ok" | "warn" | "danger" | "info" | "accent";

const TONE: Record<BadgeTone, string> = {
  neutral: "bg-neutral-soft text-neutral-text border-neutral-border",
  ok: "bg-ok-soft text-ok-text border-ok-border",
  warn: "bg-warn-soft text-warn-text border-warn-border",
  danger: "bg-danger-soft text-danger-text border-danger-border",
  info: "bg-info-soft text-info-text border-info-border",
  accent: "bg-accent-soft text-accent-text border-accent-border",
};

export interface BadgeProps extends ComponentPropsWithoutRef<"span"> {
  tone?: BadgeTone;
  children: ReactNode;
  /** Leading dot in the current colour. Marks a badge as a *class* of thing
   *  rather than one more status pill. */
  dot?: boolean;
  mono?: boolean;
}

/* forwardRef, and the reason is not generality: a tooltip trigger clones its
   child and hands it a ref plus the hover and focus handlers. A plain function
   component drops both silently, so every badge with an explanation attached -
   "3 degraded", "4 mutating" - would look interactive and never open. */
export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(function Badge(
  { tone = "neutral", children, className, dot, mono, ...rest }, ref
) {
  return (
    <span
      ref={ref}
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border",
        "px-1.5 py-px text-xs font-semibold tracking-wide",
        mono && "font-mono",
        TONE[tone],
        className
      )}
      {...rest}
    >
      {dot && (
        <span className="size-1.5 shrink-0 rounded-full bg-current" />
      )}
      {children}
    </span>
  );
});

/** A bare status dot, for rows where a full badge would be too loud. */
export function Dot({
  tone = "neutral", pulse, className,
}: {
  tone?: BadgeTone | "idle";
  pulse?: boolean;
  className?: string;
}) {
  const colour =
    tone === "ok" ? "bg-ok"
    : tone === "warn" ? "bg-warn"
    : tone === "danger" ? "bg-danger"
    : tone === "info" ? "bg-info"
    : tone === "accent" ? "bg-accent"
    : "bg-faint";
  return (
    <span className={cn("relative inline-flex shrink-0", className)}>
      <span className={cn("size-2 rounded-full", colour)} />
      {pulse && (
        <span
          className={cn("absolute inset-0 rounded-full sc-ping", colour)}
          aria-hidden="true"
        />
      )}
    </span>
  );
}
