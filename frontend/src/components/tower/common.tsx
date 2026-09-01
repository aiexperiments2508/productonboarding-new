import type { ReactNode } from "react";
import type { TowerState } from "../../api";
import { Badge, Stat, Tooltip, cn } from "../../ui";
import type { BadgeTone } from "../../ui";

/* The pieces four tabs share.
 *
 * Held here rather than in whichever tab needed each one first, for the reason
 * `components/onboarding/common.tsx` exists: the second copy is where "All
 * clear" and "Cleared" start appearing on two screens for the same state.
 */

/** The seven states, in the order work moves through them, with the words the
 *  screen uses for each. Kept in step with `sc/tower/flow.py::STATES` - and the
 *  order is the flow, so a strip drawn from this reads left to right as the
 *  journey rather than as an alphabetised list. */
export const STATE_ORDER: TowerState[] = [
  "RECEIVED", "PROCESSING", "ON_HOLD", "BLOCKED",
  "ALL_CLEAR", "PUSHED_DOWNSTREAM", "ON_SALE",
];

export const STATE_LABEL: Record<TowerState, string> = {
  RECEIVED: "Received",
  PROCESSING: "Processing",
  ON_HOLD: "On hold",
  BLOCKED: "Blocked",
  ALL_CLEAR: "All clear",
  PUSHED_DOWNSTREAM: "Pushed downstream",
  ON_SALE: "On sale",
};

/** What each means, in one sentence somebody can act on. */
export const STATE_NOTE: Record<TowerState, string> = {
  RECEIVED: "Arrived and not yet taken into the record.",
  PROCESSING: "In the record with gaps still open. Nothing has stopped it; "
    + "nothing has cleared it either.",
  ON_HOLD: "Waiting on a person - a safety-class field, a single source, or a "
    + "proposal below the confidence threshold.",
  BLOCKED: "Stopped, and back with its supplier. A regulation, this "
    + "organisation's own policy, or a blocking finding.",
  ALL_CLEAR: "Fit to launch, and not pushed anywhere yet.",
  PUSHED_DOWNSTREAM: "Dispatched. Listings prepared, waiting on a launch date.",
  ON_SALE: "On the floor. What a shopper sees is what the record says.",
};

const STATE_TONE: Record<TowerState, BadgeTone> = {
  RECEIVED: "neutral",
  PROCESSING: "info",
  ON_HOLD: "warn",
  BLOCKED: "danger",
  ALL_CLEAR: "ok",
  PUSHED_DOWNSTREAM: "ok",
  ON_SALE: "ok",
};

export function StateChip({ state }: { state: TowerState }) {
  return (
    <Tooltip content={STATE_NOTE[state]}>
      <span>
        <Badge tone={STATE_TONE[state]}>{STATE_LABEL[state]}</Badge>
      </span>
    </Tooltip>
  );
}

/** A rate, as a percentage - or a dash.
 *
 * `null` is not zero and must never render as it. The server returns null when
 * a rate had nothing to take a proportion of, and "0% of feeds passed
 * compliance" for a week nothing arrived in is the figure that gets
 * screenshotted and quoted back.
 */
export function pct(rate: number | null | undefined, decimals = 1): string {
  return rate === null || rate === undefined
    ? "—"
    : `${(rate * 100).toFixed(decimals)}%`;
}

/** Money, at a precision that does not round a real figure away to nothing. */
export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value === 0) return "$0";
  return value >= 0.01 ? `$${value.toFixed(2)}` : `$${value.toFixed(5)}`;
}

export function tokens(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  return String(value);
}

/** Hours, as something readable at both ends of the range. */
export function hours(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value < 1) return `${Math.round(value * 60)} min`;
  if (value < 48) return `${value.toFixed(1)} h`;
  return `${(value / 24).toFixed(1)} d`;
}

/** A figure with its own note underneath. Thin wrapper over `Stat` so a tile
 *  can carry the sample size or the clock beside the number rather than in a
 *  legend somewhere else. */
export function Tile({ label, value, sub, tone, wide }: {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "good" | "bad";
  wide?: boolean;
}) {
  return (
    <Stat label={label} value={value} sub={sub} tone={tone}
          className={wide ? "col-span-2" : undefined} />
  );
}

/** What this screen did not do, said where the numbers are.
 *
 * Three different silences reach this: the window was truncated so every
 * figure is a sample, nothing in it was assessable, or the reading checks did
 * not run. All three are reasons to read the numbers differently, which is why
 * none of them is a footnote.
 */
export function Caveat({ text, className }: {
  text?: string | null;
  className?: string;
}) {
  if (!text) return null;
  return (
    <p
      role="note"
      className={cn(
        "rounded-sm border border-warn/40 bg-warn/5 px-2.5 py-2",
        "text-2xs leading-relaxed text-muted",
        className
      )}
    >
      {text}
    </p>
  );
}

/** The line that keeps the persona picker honest.
 *
 * Rendered wherever a persona is chosen, and deliberately not dismissible. A
 * control that looks like access control and is not is the kind of thing
 * somebody builds a process on top of.
 */
export function LensNote({ note }: { note: string }) {
  return (
    <p className="text-2xs leading-relaxed text-faint">
      <span className="font-medium text-muted">A lens, not a permission
        boundary. </span>
      {note}
    </p>
  );
}

/** The window a response actually applied, said out loud.
 *
 * `bounded` false means no dates were sent, so the figures are the whole
 * estate. Printing "1 July to 31 August" over that would be a caption that
 * happens to be true rather than a filter that was applied.
 */
export function WindowNote({ window, bounded }: {
  window: { start: string | null; end: string | null };
  bounded: boolean;
}) {
  return (
    <span className="font-mono text-2xs text-faint">
      {bounded
        ? `${window.start ?? "the beginning"} → ${window.end ?? "now"}`
        : "every feed on record — no date filter applied"}
    </span>
  );
}
