import type { ReactNode } from "react";
import { Tabs as RTabs } from "radix-ui";
import { cn } from "./cn";

/* Tabs.
 *
 * The fourth hand-rolled tab bar in this repository is the reason this file
 * exists. Supplier Intake had one built from plain buttons, and the Ops Console
 * and the Vendor Portal each have their own - four implementations of one
 * control, and the three that are not this one had no `role`, no
 * `aria-selected` and no arrow keys, so none of them could be operated without
 * a mouse.
 *
 * Radix supplies the parts that are tedious to get right and invisible when
 * they are wrong: the roving tabindex (one stop for the whole bar, arrows to
 * move within it), the `tablist`/`tab`/`tabpanel` wiring, and the id linkage
 * between a tab and the panel it controls.
 *
 * Two things on top of that are worth naming.
 *
 * Radix renders every panel and marks the inactive ones `hidden` rather than
 * unmounting them. `hidden` is an attribute, `display: flex` is a rule, and the
 * rule would normally win - the only reason it does not here is that Tailwind's
 * preflight ships `[hidden] { display: none !important }`. Worth knowing,
 * because the same pairing without that `!important` is a live bug, and this
 * repository already had one: the Vendor Portal's `.tabs { display: flex }`
 * kept a hidden tab bar on screen.
 *
 * And `TabList` is sticky by default. This app's shell does not scroll, so a
 * tab set lives inside whatever scroller its section owns; a bar that scrolled
 * away would take the reader's only way back with it, forty rows down.
 */

export function Tabs({
  value, onValueChange, children, fill, className,
}: {
  value: string;
  onValueChange: (v: string) => void;
  children: ReactNode;
  /** Take the remaining height and let a `scroll` panel overflow inside it.
   *
   *  `flex-1` alone is a trap: when the viewport is shorter than the pinned
   *  chrome above the tabs, the free space is negative and the panel resolves
   *  to zero - it does not overflow, it disappears. So the floor comes with
   *  it, and is not optional. Below 20rem of room the tab set stops shrinking
   *  and whatever scroller the section put above it takes over. */
  fill?: boolean;
  className?: string;
}) {
  return (
    <RTabs.Root
      value={value}
      onValueChange={onValueChange}
      className={cn(
        "flex flex-col gap-3",
        // Deliberately not `min-h-0` - that is the class that lets this
        // collapse to nothing. See the note on `fill`.
        fill && "min-h-[20rem] flex-1",
        className
      )}
    >
      {children}
    </RTabs.Root>
  );
}

/** The bar. Underlined rather than boxed - the panel below draws its own edges,
 *  and a second container around the tabs stacks two borders for no added
 *  meaning. */
export function TabList({
  children, ariaLabel, actions, sticky = true, className,
}: {
  children: ReactNode;
  ariaLabel?: string;
  /** Trailing controls belonging to the tab set rather than to one panel. */
  actions?: ReactNode;
  /** Stays put while the panel scrolls under it. Needs an opaque background,
   *  which is why this carries `bg-canvas` rather than leaving it transparent. */
  sticky?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center gap-2 border-b border-subtle",
        sticky && "sticky top-0 z-[var(--z-sticky)] bg-canvas",
        className
      )}
    >
      <RTabs.List
        aria-label={ariaLabel}
        className="flex min-w-0 flex-1 gap-0.5 overflow-x-auto"
      >
        {children}
      </RTabs.List>
      {actions && <div className="flex shrink-0 items-center gap-1.5 pb-1">{actions}</div>}
    </div>
  );
}

export function Tab({
  value, children, count, className,
}: {
  value: string;
  children: ReactNode;
  /** A tally for this tab, set in muted secondary text rather than folded into
   *  the label. "Products 12" reads as a heading with a number beside it;
   *  "Products (12)" reads as one long label, and at four tabs the bar becomes
   *  a row of parentheses. */
  count?: number;
  className?: string;
}) {
  return (
    <RTabs.Trigger
      value={value}
      className={cn(
        "relative -mb-px flex shrink-0 items-center gap-1.5 whitespace-nowrap",
        "rounded-t-sm border-b-2 border-transparent px-3 py-2 text-sm",
        "text-muted transition-colors duration-[var(--dur-fast)] ease-standard",
        "hover:text-fg",
        // The active tab is the one place on this control that takes the
        // accent. Everything else stays neutral, so the bar reads as one
        // selected thing rather than as several coloured ones.
        "data-[state=active]:border-accent data-[state=active]:font-medium",
        "data-[state=active]:text-accent-text",
        className
      )}
    >
      {children}
      {count !== undefined && (
        <span className="font-mono text-xs tabular-nums text-faint">{count}</span>
      )}
    </RTabs.Trigger>
  );
}

export function TabPanel({
  value, children, scroll, className,
}: {
  value: string;
  children: ReactNode;
  /** Panel owns its overflow. Only safe under a `fill` root - see the note on
   *  `Tabs.fill` for why that is not the default. */
  scroll?: boolean;
  className?: string;
}) {
  return (
    <RTabs.Content
      value={value}
      className={cn(
        "flex flex-col gap-3 outline-none",
        scroll && "min-h-0 flex-1 overflow-y-auto [&>*]:shrink-0",
        className
      )}
    >
      {children}
    </RTabs.Content>
  );
}
