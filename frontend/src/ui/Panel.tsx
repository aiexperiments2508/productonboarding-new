import type { CSSProperties, ReactNode } from "react";
import { cn } from "./cn";

/* Panel.
 *
 * The unit of layout. A titled surface with an optional toolbar, and a body
 * that can be flush when its content draws its own edges (tables, feeds, the
 * network map).
 *
 * The header uses a sunken strip rather than the body colour, so a screen of
 * six panels reads as six things rather than one long scroll of white - the
 * separation comes from the surface change, not from heavier borders.
 */

export function Panel({
  title, subtitle, actions, children, flush, scroll, className, bodyClassName,
  style, icon, tone,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  /** Body has no padding. For content that draws to its own edge. */
  flush?: boolean;
  /** Body scrolls inside the panel rather than lengthening the page.
   *
   *  A section of six dense panels used to be one column of vertical scroll,
   *  which pushed the header off the top and made "look at the map and the
   *  feed together" impossible. A panel that owns its own overflow keeps its
   *  title in place and keeps its neighbours on screen. The panel already has
   *  `flex flex-col overflow-hidden`, so this is the one class its body was
   *  missing - bound by whatever height the caller gives it. */
  scroll?: boolean;
  className?: string;
  bodyClassName?: string;
  style?: CSSProperties;
  icon?: ReactNode;
  /** Left accent stripe, for a panel that needs attention. */
  tone?: "warn" | "danger" | "accent";
}) {
  const stripe =
    tone === "warn" ? "before:bg-warn"
    : tone === "danger" ? "before:bg-danger"
    : tone === "accent" ? "before:bg-accent"
    : "";
  return (
    <section
      style={style}
      className={cn(
        "relative flex min-w-0 flex-col overflow-hidden rounded-md",
        "border border-subtle bg-raised shadow-e1",
        tone &&
          "before:absolute before:inset-y-0 before:left-0 before:w-0.5 " +
            "before:content-['']",
        stripe,
        className
      )}
    >
      {(title || actions) && (
        <header
          className={cn(
            "flex min-h-[var(--panel-head-h)] shrink-0 items-center gap-2",
            "border-b border-subtle bg-sunken/60 px-3"
          )}
        >
          {icon && <span className="shrink-0 text-faint">{icon}</span>}
          {title && (
            <h2 className="truncate text-xs font-semibold uppercase tracking-caps text-muted">
              {title}
            </h2>
          )}
          {subtitle && (
            <span className="truncate text-xs text-faint">{subtitle}</span>
          )}
          {actions && (
            <div className="ml-auto flex shrink-0 items-center gap-1.5">
              {actions}
            </div>
          )}
        </header>
      )}
      <div
        className={cn(
          "min-w-0 flex-1",
          scroll && "min-h-0 overflow-y-auto",
          !flush && "p-[var(--panel-pad)]",
          bodyClassName
        )}
      >
        {children}
      </div>
    </section>
  );
}

/** A labelled group inside a panel body. Cheaper than nesting panels, which
 *  stacks two borders and two header strips for no added meaning. */
export function Section({
  label, actions, children, className,
}: {
  label: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <div className="flex items-center gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-caps text-faint">
          {label}
        </h3>
        <span className="h-px flex-1 bg-subtle" />
        {actions}
      </div>
      {children}
    </div>
  );
}
