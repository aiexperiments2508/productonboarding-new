import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Slot } from "radix-ui";
import { cn } from "./cn";

/* Button.
 *
 * Five tones and three sizes, all built from semantic tokens so a theme or
 * brand-hue change needs no work here.
 *
 * The press feedback is a 1px translate rather than a scale. On a dense screen
 * a scaling button nudges its neighbours' optical alignment; a translate keeps
 * the row still and still reads as a press.
 */

type Tone = "default" | "primary" | "danger" | "ghost" | "subtle";
type Size = "xs" | "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: Tone;
  size?: Size;
  /** Render as the single child element instead of a <button>. */
  asChild?: boolean;
  /** Leading glyph. Sized by the button, so pass the component, not an element. */
  icon?: ReactNode;
  /** Square, icon-only. Requires aria-label. */
  iconOnly?: boolean;
  /** Swaps the icon for a spinner and disables interaction. */
  loading?: boolean;
}

const TONE: Record<Tone, string> = {
  default:
    "bg-raised text-fg border border-strong hover:bg-hover active:bg-active",
  primary:
    "bg-accent text-on-accent border border-accent font-semibold " +
    "hover:bg-accent-hover active:brightness-95 shadow-e1",
  danger:
    "bg-raised text-danger-text border border-danger-border " +
    "hover:bg-danger-soft active:bg-danger-soft",
  ghost:
    "bg-transparent text-muted border border-transparent " +
    "hover:bg-hover hover:text-fg active:bg-active",
  subtle:
    "bg-sunken text-fg border border-transparent hover:bg-hover active:bg-active",
};

const SIZE: Record<Size, string> = {
  xs: "h-[var(--control-h-xs)] px-2 text-xs gap-1 rounded-xs",
  sm: "h-[var(--control-h-sm)] px-2.5 text-sm gap-1.5 rounded-sm",
  md: "h-[var(--control-h-md)] px-3.5 text-base gap-2 rounded-sm",
};

const SIZE_ICON_ONLY: Record<Size, string> = {
  xs: "h-[var(--control-h-xs)] w-[var(--control-h-xs)] p-0 rounded-xs",
  sm: "h-[var(--control-h-sm)] w-[var(--control-h-sm)] p-0 rounded-sm",
  md: "h-[var(--control-h-md)] w-[var(--control-h-md)] p-0 rounded-sm",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      tone = "default", size = "sm", asChild, icon, iconOnly,
      loading, className, children, disabled, ...rest
    },
    ref
  ) {
    const Comp = asChild ? Slot.Root : "button";
    return (
      <Comp
        ref={ref}
        disabled={disabled || loading}
        data-loading={loading || undefined}
        className={cn(
          "inline-flex select-none items-center justify-center whitespace-nowrap",
          "transition-[background-color,border-color,color,transform,box-shadow]",
          "duration-[var(--dur-fast)] ease-standard",
          "active:translate-y-px",
          "disabled:pointer-events-none disabled:opacity-45",
          TONE[tone],
          iconOnly ? SIZE_ICON_ONLY[size] : SIZE[size],
          className
        )}
        {...rest}
      >
        {loading ? <Spinner /> : icon}
        {!iconOnly && children}
      </Comp>
    );
  }
);

/** Indeterminate spinner. An arc rather than a full ring, so the rotation is
 *  visible without needing a colour change. */
export function Spinner({ size = 14 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className="animate-spin-slow shrink-0"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.4"
              opacity="0.22" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.4"
            strokeLinecap="round" />
    </svg>
  );
}
