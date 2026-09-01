import type { BadgeTone } from "../ui";

/* How a verdict is allowed to be said out loud.
 *
 * There is one rule in this file and it is the reason the file exists: **the
 * word "ready" is reserved for a complete assessment.**
 *
 * Seven of the eleven checks are rules and run on every page load. The other
 * four read a regulation, the retailer's own policy, a piece of internal
 * documentation and the meaning of a sentence, and they need a model - so they
 * now run when somebody asks for them rather than on every click, which is what
 * makes this screen open instantly.
 *
 * That trade is only honest if the screen never launders the difference. A
 * product with no rule findings has not been found ready; it has been found
 * *not yet unready*, by seven checks out of eleven, and the four that did not
 * run are precisely the ones that catch a mandate the record breaches, a policy
 * it conflicts with, and a sentence that has quietly become untrue. Rendering that as a green "ready to
 * launch" would be the single most dangerous thing this interface could do,
 * and it is the thing `checks_complete` exists to prevent.
 *
 * So it lives here, once. Five surfaces render a verdict - the detail badge,
 * the list rows, the header tally, the summary strip and the staging dialog -
 * and a sixth will be added by somebody who has not read this comment. They
 * all call `verdictBadge`, and it cannot say "ready" without being handed a
 * complete assessment.
 *
 * Findings are not weakened the same way. A missing allergen declaration found
 * by a rule is a missing allergen declaration whether or not a model also
 * looked, so RETURN and BLOCKED read the same in both states.
 */

export const READY = "READY_TO_LAUNCH";
export const RETURN = "RETURN_TO_SOURCE";
export const BLOCKED = "BLOCKED";

export interface VerdictBadge {
  label: string;
  tone: BadgeTone;
  /** True when the word is being held back because the assessment is narrow.
   *  Surfaces use it to add an outline rather than a second sentence. */
  narrow: boolean;
}

export function verdictBadge(
  verdict: string | undefined,
  checksComplete: boolean | undefined,
): VerdictBadge {
  if (!verdict) return { label: "unassessed", tone: "neutral", narrow: false };

  if (verdict === BLOCKED) {
    return { label: "blocked", tone: "danger", narrow: false };
  }
  if (verdict === RETURN) {
    return { label: "back to source", tone: "warn", narrow: false };
  }
  if (verdict === READY) {
    // The whole point of the file.
    return checksComplete
      ? { label: "ready to launch", tone: "ok", narrow: false }
      : { label: "no rule findings", tone: "neutral", narrow: true };
  }
  return { label: verdict.toLowerCase(), tone: "neutral", narrow: false };
}

/** What the narrow state means, in a sentence a reviewer can act on.
 *
 *  The server's own caveat says the reading checks "did not run", which is
 *  true and reads as a failure. They have not been *asked* to run, and the
 *  button to do it is right there - so the client says that instead. */
export const NARROW_NOTE =
  "The seven rule checks ran. The four that read regulation, policy, internal "
  + "documentation and copy meaning have not been run for this product yet.";

/** The tally line above a product list, in the same vocabulary.
 *
 *  Grouped by the badge label rather than by the raw verdict, so a list of
 *  narrow assessments counts as "no rule findings" and never as "ready". */
export function tallyVerdicts(
  rows: { verdict?: string; checks_complete?: boolean }[],
): { label: string; tone: BadgeTone; n: number }[] {
  const counts = new Map<string, { label: string; tone: BadgeTone; n: number }>();
  for (const row of rows) {
    const badge = verdictBadge(row.verdict, row.checks_complete);
    const entry = counts.get(badge.label);
    if (entry) entry.n += 1;
    else counts.set(badge.label, { label: badge.label, tone: badge.tone, n: 1 });
  }
  // Worst first, so the thing holding a launch up is the thing read first.
  const order = ["blocked", "back to source", "no rule findings",
                 "ready to launch"];
  return [...counts.values()].sort(
    (a, b) => order.indexOf(a.label) - order.indexOf(b.label));
}
