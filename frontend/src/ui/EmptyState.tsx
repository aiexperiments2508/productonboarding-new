import type { ReactNode } from "react";
import { cn } from "./cn";

/* Empty state.
 *
 * Three parts, and the third is the one that matters: an illustration so the
 * panel does not read as broken, a sentence saying what is missing, and - where
 * one exists - the control that fills it. An empty state that explains without
 * offering the next step just leaves the reviewer to go and find it.
 */

export function EmptyState({
  art, title, children, action, compact, className,
}: {
  art?: ReactNode;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  /** For small panels where a full illustration would crowd the body. */
  compact?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 text-center",
        compact ? "px-4 py-6" : "px-6 py-9",
        className
      )}
    >
      {art && !compact && (
        <div className="animate-fade-in opacity-90">{art}</div>
      )}
      <div className="max-w-sm">
        {title && (
          <div className="text-base font-medium text-fg">{title}</div>
        )}
        {children && (
          <p className="mt-1 text-sm leading-relaxed text-muted">{children}</p>
        )}
      </div>
      {action && <div className="pt-0.5">{action}</div>}
    </div>
  );
}
