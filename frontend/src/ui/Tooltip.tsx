import type { ReactNode } from "react";
import { Tooltip as RTooltip } from "radix-ui";
import { cn } from "./cn";

/* Tooltip.
 *
 * Replaces the browser's `title=` attribute across the app. `title` waits about
 * a second, cannot be styled, cannot be reached from the keyboard, and on a
 * screen where half the value is in the explanations ("what does SIMULATED
 * mean", "why is this channel blocked") that is most of the product's
 * reasoning hidden behind a slow, inaccessible affordance.
 *
 * Provider lives at the app root so the open-delay is shared: once one tooltip
 * has opened, moving along a toolbar shows the rest instantly instead of
 * re-waiting at every control.
 */

export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <RTooltip.Provider delayDuration={320} skipDelayDuration={280}>
      {children}
    </RTooltip.Provider>
  );
}

export function Tooltip({
  content, children, side = "top", align = "center", mono, className,
}: {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  mono?: boolean;
  className?: string;
}) {
  if (!content) return <>{children}</>;
  return (
    <RTooltip.Root>
      <RTooltip.Trigger asChild>{children}</RTooltip.Trigger>
      <RTooltip.Portal>
        <RTooltip.Content
          side={side}
          align={align}
          sideOffset={6}
          collisionPadding={8}
          className={cn(
            "z-[var(--z-tooltip)] max-w-xs rounded-sm border border-strong",
            "bg-overlay px-2 py-1.5 text-sm text-fg shadow-e3",
            // Radix sets data-state and data-side; entering from the trigger's
            // side is what makes a tooltip feel attached to its control rather
            // than merely appearing near it.
            "data-[state=delayed-open]:animate-scale-in",
            "data-[state=closed]:animate-fade-in data-[state=closed]:opacity-0",
            "whitespace-pre-line",
            mono && "font-mono text-xs",
            className
          )}
        >
          {content}
          <RTooltip.Arrow className="fill-[var(--border-strong)]" width={10} height={5} />
        </RTooltip.Content>
      </RTooltip.Portal>
    </RTooltip.Root>
  );
}
