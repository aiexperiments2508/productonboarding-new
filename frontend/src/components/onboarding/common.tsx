import type { ReactNode } from "react";
import type { SuggestionReason } from "../../api";
import { IconAlert, IconCheck, IconDoc } from "../../icons";
import { Badge, Code, Tooltip, cn } from "../../ui";

/* The pieces every onboarding tab draws the same way.
 *
 * Held here rather than in each tab because the confidence bar and the reason
 * list are the two things a category manager actually reads, and a second copy
 * of either is a second opinion about what the number means.
 */

/** What each class of evidence is, in the words the screen uses. */
export const REASON_LABEL: Record<SuggestionReason["kind"], string> = {
  PASSAGE: "read from a document",
  SIBLING: "another variant of this product",
  APPROVAL: "a decision you have made before",
  CATEGORY: "the rest of the category",
  SAFETY: "safety class",
};

/** The confidence, against the line it has to clear.
 *
 * The threshold is drawn *on* the bar rather than printed beside it. A number
 * next to a number is arithmetic a reader has to do; a mark on a bar is the
 * answer to "did this clear" before anything is read.
 */
export function ConfidenceBar({ value, threshold, safety }: {
  value: number;
  threshold: number;
  /** Scored zero by rule rather than by evidence, which is a different fact
   *  about the proposal and must not read as "the model was unsure". */
  safety?: boolean;
}) {
  const cleared = !safety && value >= threshold;
  return (
    <div className="flex min-w-[9rem] flex-col gap-1">
      <div className="flex items-baseline gap-1.5">
        <span
          className={cn(
            "font-mono text-sm tabular-nums",
            safety ? "text-faint" : cleared ? "text-ok-text" : "text-warn-text"
          )}
        >
          {safety ? "—" : `${Math.round(value * 100)}%`}
        </span>
        <span className="text-2xs uppercase tracking-caps text-faint">
          {safety ? "decided by a person" : cleared ? "autonomous" : "needs you"}
        </span>
      </div>
      <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-sunken">
        <div
          className={cn(
            "h-full transition-[width] duration-[var(--dur-base)]",
            cleared ? "bg-ok" : "bg-warn"
          )}
          style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
        />
        <span
          aria-hidden
          title={`the ${Math.round(threshold * 100)}% autonomy threshold`}
          className="absolute inset-y-0 w-px bg-strong"
          style={{ left: `${Math.max(0, Math.min(1, threshold)) * 100}%` }}
        />
      </div>
    </div>
  );
}

/** Why the score is what it is, one row per thing weighed.
 *
 * Signed, and the sign is the point: a sibling holding a different value is
 * evidence *against* the proposal, and a list that showed only what agreed
 * would be a case for the proposal rather than the reasoning behind it.
 */
export function ReasonList({ reasons }: { reasons: SuggestionReason[] }) {
  if (reasons.length === 0) {
    return (
      <p className="text-sm text-muted">
        Nothing on file bears on this value — which is why it is a question
        rather than a proposal.
      </p>
    );
  }
  return (
    <ul className="flex flex-col gap-1.5">
      {reasons.map((reason, i) => (
        <li key={i} className="flex items-start gap-2 text-sm">
          {reason.agrees ? (
            <IconCheck size={13} className="mt-1 shrink-0 text-ok-text" />
          ) : (
            <IconAlert size={13} className="mt-0.5 shrink-0 text-warn-text" />
          )}
          <span className="min-w-0 flex-1">
            <span className="text-2xs uppercase tracking-caps text-faint">
              {REASON_LABEL[reason.kind] ?? reason.kind}
            </span>
            <span className="block text-muted">{reason.detail}</span>
          </span>
          {reason.weight !== 0 && (
            <span
              className={cn(
                "shrink-0 font-mono text-xs tabular-nums",
                reason.weight > 0 ? "text-ok-text" : "text-warn-text"
              )}
            >
              {reason.weight > 0 ? "+" : ""}
              {Math.round(reason.weight * 100)}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Who refused a product, said as the thing a supplier can act on. */
export function AuthorityTag({ authority }: {
  authority: "REGULATION" | "POLICY" | null;
}) {
  if (!authority) return null;
  return (
    <Tooltip
      content={
        authority === "REGULATION"
          ? "A market authority forbids selling this as it stands. No amount of missing data explains it away."
          : "This organisation's own policy refuses it. A regulation has not been breached; a rule we set has."
      }
    >
      <span>
        <Badge tone={authority === "REGULATION" ? "danger" : "warn"}>
          {authority === "REGULATION" ? "regulation" : "our policy"}
        </Badge>
      </span>
    </Tooltip>
  );
}

/** A finding, with the clause it rests on. A finding nobody can open is a
 *  finding nobody can check. */
export function FindingLine({ detail, basis, system }: {
  detail: string;
  basis?: string | null;
  system?: string | null;
}) {
  return (
    <li className="flex items-start gap-2 text-sm">
      <IconDoc size={13} className="mt-0.5 shrink-0 text-faint" />
      <span className="min-w-0">
        {basis && <Code className="mr-1.5">{basis}</Code>}
        {detail}
        {system && (
          <span className="ml-1 text-muted">
            — <Code>{system}</Code> has to fix it
          </span>
        )}
      </span>
    </li>
  );
}

/** A value as a person reads it, with its unit. */
export function ValueChip({ value, unit, children }: {
  value: unknown;
  unit?: string | null;
  children?: ReactNode;
}) {
  const shown = Array.isArray(value)
    ? value.join(", ")
    : value === null || value === undefined
    ? "—"
    : String(value);
  return (
    <span className="inline-flex items-baseline gap-1">
      <Code>{shown}</Code>
      {unit && <span className="text-xs text-faint">{unit}</span>}
      {children}
    </span>
  );
}
