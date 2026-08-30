import type { CorrectionKind, KPIs, PlanDiff } from "../api";
import { IconCorrection, IconSpark, IconTrace } from "../icons";
import { Badge, Panel, Section, Tooltip, cn } from "../ui";
import type { BadgeTone } from "../ui";

/* What moved, and why.
 *
 * The finale of the demo lands here. DOC-01 v3 arrives, the run re-plans on the
 * same thread, and the recommendation moves - from "the 65 W correction applies
 * to both variants" to "it applies to the Max only". The brief asks the UI to
 * show *exactly* why a recommendation changes when new evidence arrives, and
 * exactly is the load-bearing word, so every figure on this panel is computed by
 * the validator: the reading that led before, the reading that leads now, the
 * movement in each figure, and the corrections that were not on the table when
 * the superseded recommendation was written.
 *
 * The reason is the point of the panel, not a footnote to it. A recommendation
 * that moves without naming what moved it is the thing a reviewer cannot check,
 * so `reason` is drawn first and loudest, and the corrections that arrived since
 * are listed underneath as the evidence for it. The model's prose sits at the
 * bottom as narrative; it is never the source of any number here.
 *
 * The panel reads left to right - superseded, then current - because that is the
 * direction the reviewer's question runs: I have approved nothing yet, what am I
 * looking at instead, and what made it move.
 */

const signedCount = (n: number) => `${n > 0 ? "+" : n < 0 ? "-" : ""}${Math.abs(n)}`;
const signedPoints = (n: number) =>
  `${n > 0 ? "+" : n < 0 ? "-" : ""}${Math.abs(n).toFixed(1)} pp`;

/** The figures worth showing movement on, in the order a reviewer reads them:
 *  can it publish, what is stuck, is anything unsafe, how much is stale, how
 *  complete is the record. `better` says which direction is an improvement,
 *  which is the only way a delta can be coloured honestly. */
const MOVED_FIELDS: {
  key: keyof KPIs;
  label: string;
  better: "up" | "down";
  format: (n: number) => string;
}[] = [
  { key: "listings_ready_pct", label: "Listings ready", better: "up",
    format: signedPoints },
  { key: "channels_blocked", label: "Channels blocked", better: "down",
    format: signedCount },
  { key: "safety_flags", label: "Safety flags", better: "down",
    format: signedCount },
  { key: "assets_stale", label: "Assets stale", better: "down",
    format: signedCount },
  { key: "completeness_pct", label: "Completeness", better: "up",
    format: signedPoints },
];

/** Correction kinds in the words a reviewer would use. The raw kind stays on
 *  the row, because that is what the engine logs and what they search by. */
const CORRECTION_WORDS: Record<CorrectionKind, string> = {
  SPEC_CORRECTION: "corrected specification",
  ALLERGEN_CHANGE: "allergen change",
  INGREDIENT_CHANGE: "ingredient change",
  SOURCE_CONFLICT: "sources disagree",
  CHANNEL_REJECTION: "channel rejected the listing",
  DOC_WITHDRAWN: "document withdrawn",
  DATA_GAP: "value missing",
};

const CORRECTION_TONE: Record<CorrectionKind, BadgeTone> = {
  SPEC_CORRECTION: "warn",
  ALLERGEN_CHANGE: "danger",
  INGREDIENT_CHANGE: "warn",
  SOURCE_CONFLICT: "warn",
  CHANNEL_REJECTION: "danger",
  DOC_WITHDRAWN: "warn",
  DATA_GAP: "neutral",
};

export function PlanDiffPanel({ diff, narrative }: {
  diff: PlanDiff;
  /** The recommender's account of the change. Optional: the panel is complete
   *  without it, because every figure on it was computed. */
  narrative?: string;
}) {
  // A revision clears the diff and only `rank` fills it back in, so there is a
  // window in which the run carries an empty one. There is nothing to show
  // about a change that has not been computed yet - and the superseded reading
  // is what the whole panel is written around, so its absence is the test.
  if (!diff?.previous) return null;

  const moved = MOVED_FIELDS.filter(
    (f) => Math.abs(diff.moved?.[f.key] ?? 0) > 1e-9
  );
  const signals = diff.new_signals ?? [];

  return (
    <Panel
      title={`Revision ${diff.revision} — what changed`}
      subtitle={diff.headline}
      tone={diff.held ? "accent" : "warn"}
      icon={<IconTrace size={14} />}
      actions={
        <Badge tone={diff.held ? "ok" : "warn"} dot>
          {diff.held ? "recommendation holds" : "recommendation moved"}
        </Badge>
      }
      className="animate-rise-in"
    >
      <div className="flex flex-col gap-3.5">
        {/* --- why ------------------------------------------------------- */}
        {diff.reason && (
          <div
            className={cn(
              "flex items-start gap-2 rounded-sm border px-2.5 py-2",
              diff.held
                ? "border-accent-border bg-accent-soft"
                : "border-warn-border bg-warn-soft"
            )}
          >
            <IconCorrection
              size={15}
              className={cn(
                "mt-0.5 shrink-0",
                diff.held ? "text-accent-text" : "text-warn-text"
              )}
            />
            <div className="min-w-0">
              <div
                className={cn(
                  "text-2xs uppercase tracking-caps",
                  diff.held ? "text-accent-text" : "text-warn-text"
                )}
              >
                {diff.held ? "re-checked because" : "the recommendation moved because"}
              </div>
              <p className="mt-0.5 text-sm leading-relaxed text-fg">
                {diff.reason}
              </p>
            </div>
          </div>
        )}

        {/* --- before / after ------------------------------------------- */}
        <div className="grid items-stretch gap-2 sm:grid-cols-[1fr_auto_1fr]">
          <OptionCard
            label="Superseded"
            name={diff.previous.name}
            id={diff.previous.scenario_id}
            kpis={diff.previous.kpis ?? {}}
            muted
          />
          <div className="flex items-center justify-center px-1">
            <span
              aria-hidden="true"
              className={cn(
                "font-mono text-lg",
                diff.held ? "text-accent-text" : "text-warn-text"
              )}
            >
              →
            </span>
          </div>
          <OptionCard
            label={diff.held ? "Still recommended" : "Now recommended"}
            name={diff.current?.name}
            id={diff.current?.scenario_id}
            kpis={diff.current?.kpis ?? {}}
            highlight={!diff.held}
          />
        </div>

        {/* --- movement -------------------------------------------------- */}
        {moved.length > 0 ? (
          <Section label="Movement against the superseded recommendation">
            <div className="flex flex-wrap gap-1.5">
              {moved.map((field) => {
                const value = diff.moved?.[field.key] ?? 0;
                const improved =
                  field.better === "up" ? value > 0 : value < 0;
                return (
                  <Tooltip
                    key={field.key}
                    content={`${field.label}: ${
                      improved ? "better" : "worse"
                    } than the recommendation this replaces`}
                  >
                    <span>
                      <Badge tone={improved ? "ok" : "danger"}>
                        {field.label} {field.format(value)}
                      </Badge>
                    </span>
                  </Tooltip>
                );
              })}
            </div>
          </Section>
        ) : (
          <p className="text-sm leading-relaxed text-muted">
            Nothing moved in listings ready, channels blocked or safety flags.
            The new evidence changed which reading of the correction is right
            without changing the arithmetic.
          </p>
        )}

        {/* --- where the old reading went -------------------------------- */}
        {diff.previous_now_ranked != null && !diff.held && (
          <div className="flex flex-wrap items-center gap-2 rounded-sm border border-subtle bg-sunken px-2.5 py-2 text-sm">
            <span className="text-muted">
              The superseded reading was validated again against the new
              evidence and now ranks
            </span>
            <Badge tone="neutral" mono>#{diff.previous_now_ranked}</Badge>
            {diff.previous_still_feasible === false && (
              <Badge tone="danger">cannot publish</Badge>
            )}
          </div>
        )}
        {diff.previous_now_ranked == null && !diff.held && (
          <p className="text-sm leading-relaxed text-muted">
            The superseded reading is no longer on the table — the newer source
            ruled out the values it was built on.
          </p>
        )}

        {/* --- what caused it -------------------------------------------- */}
        {signals.length > 0 && (
          <Section
            label={`New corrections since the superseded recommendation (${signals.length})`}
          >
            <div className="flex flex-col gap-1.5">
              {signals.map((signal) => (
                <div key={signal.id} className="flex items-start gap-2 text-sm">
                  <Badge tone={CORRECTION_TONE[signal.kind] ?? "warn"}>
                    {CORRECTION_WORDS[signal.kind] ?? signal.kind}
                  </Badge>
                  <span className="min-w-0 flex-1 text-muted">
                    {signal.summary}
                  </span>
                  <span className="shrink-0 font-mono text-2xs text-faint">
                    {signal.id}
                  </span>
                </div>
              ))}
            </div>
            <p className="text-xs leading-relaxed text-faint">
              Each of these landed after the superseded recommendation was
              written. A later version of a source document supersedes the
              earlier one, so a correction that replaces the version the old
              reading was built on is what moves the recommendation.
            </p>
          </Section>
        )}

        {narrative && (
          <Section label="The recommender's account">
            <p className="flex items-start gap-2 text-sm leading-relaxed text-muted">
              <IconSpark size={14} className="mt-0.5 shrink-0 text-accent-text" />
              <span>{narrative}</span>
            </p>
          </Section>
        )}
      </div>
    </Panel>
  );
}

function OptionCard({ label, name, id, kpis, muted, highlight }: {
  label: string;
  name?: string;
  id?: string;
  kpis: Partial<KPIs>;
  muted?: boolean;
  highlight?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-1.5 rounded-sm border p-2.5",
        highlight
          ? "border-accent-border bg-accent-soft"
          : "border-subtle bg-sunken",
        muted && "opacity-75"
      )}
    >
      <span className="text-2xs uppercase tracking-caps text-faint">{label}</span>
      <span
        className={cn(
          "truncate font-medium",
          muted ? "text-muted line-through decoration-1" : "text-fg"
        )}
      >
        {name ?? "—"}
      </span>
      {id && <span className="truncate font-mono text-2xs text-faint">{id}</span>}
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-xs text-muted tabular-nums">
        {kpis.listings_ready_pct != null && (
          <span>{kpis.listings_ready_pct.toFixed(1)}% ready</span>
        )}
        {kpis.channels_blocked != null && (
          <span>{kpis.channels_blocked} blocked</span>
        )}
        {kpis.assets_stale != null && <span>{kpis.assets_stale} stale</span>}
        {kpis.safety_flags != null && kpis.safety_flags > 0 && (
          <span className="text-danger-text">
            {kpis.safety_flags} safety
          </span>
        )}
      </div>
    </div>
  );
}

/** Compact revision marker for headers. */
export function RevisionBadge({ revision }: { revision?: number }) {
  if (!revision) return null;
  return (
    <Tooltip content="This recommendation has been revised against evidence that arrived after the first version">
      <span>
        <Badge tone="accent" mono>rev {revision}</Badge>
      </span>
    </Tooltip>
  );
}
