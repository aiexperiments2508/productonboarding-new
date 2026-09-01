import type { ReactNode } from "react";
import type {
  Action, KPIs, ListingStatus, Provenance, ProvenanceKind, SourceRef, Violation,
} from "../api";
import { fmt } from "../api";
import { useCountUp } from "../hooks/useCountUp";
import { IconAlert, IconDoc } from "../icons";
import { useOpenDocument } from "../app/shell/DocumentViewer";
import { Badge, Code, Stat, Tooltip, cn } from "../ui";
import type { BadgeTone } from "../ui";

/* The shared vocabulary of the product intelligence factory.
 *
 * Everything here encodes a rule about this domain rather than a rule about how
 * things look - what makes a value a correction, why a provenance class is
 * distinct, which direction a KPI is supposed to move, what a reviewer must not
 * be allowed to miss. The purely presentational pieces live in ui/.
 *
 * One rule runs through all of it: never show a raw enum or identifier where a
 * name exists, and never lose the identifier, because a reviewer searches by
 * DOC-01 and VAR-01B rather than by "the Max variant".
 */

/* --- severity and provenance --------------------------------------------- */

const SEVERITY_TONE: Record<string, BadgeTone> = {
  CRITICAL: "danger", HIGH: "danger", MEDIUM: "warn", LOW: "neutral",
};

export function Severity({ level }: { level?: string }) {
  if (!level) return null;
  return <Badge tone={SEVERITY_TONE[level] ?? "neutral"}>{level}</Badge>;
}

const PROV_MEANING: Record<ProvenanceKind, string> = {
  RECORDED: "Read straight off a supplier feed or document, unaltered",
  INFERRED: "A model read this out of prose; the confidence says how sure",
  DECIDED: "Chosen by a person",
  SIMULATED: "Produced by the validator, never observed",
  COMMITTED: "Published to the channels",
};

const PROV_CLASS: Record<ProvenanceKind, string> = {
  RECORDED: "text-prov-recorded",
  INFERRED: "text-prov-inferred",
  DECIDED: "text-prov-decided",
  SIMULATED: "text-prov-simulated",
  COMMITTED: "text-prov-committed",
};

/** Provenance badge.
 *
 * The five kinds are the audit story made visible: a reviewer must be able to
 * tell a figure that arrived on a feed from one a model read out of a PDF at a
 * glance, without reading. INFERRED carries its confidence because that is the
 * first question anyone asks about a machine-read value, and because below the
 * safety threshold it is the difference between a listing publishing and a
 * listing being withheld.
 */
export function ProvBadge({ provenance, showConfidence = true }: {
  provenance?: Provenance | { kind: ProvenanceKind; confidence?: number | null };
  showConfidence?: boolean;
}) {
  if (!provenance?.kind) return null;
  const c = provenance.confidence;
  const inferred = provenance.kind === "INFERRED";
  return (
    <Tooltip content={PROV_MEANING[provenance.kind]}>
      <span
        className={cn(
          "inline-flex items-center gap-1 whitespace-nowrap rounded-full",
          "border border-current bg-sunken px-1.5 py-px text-xs",
          "font-semibold tracking-wide",
          PROV_CLASS[provenance.kind]
        )}
      >
        <span className="size-1.5 shrink-0 rounded-full bg-current" />
        {provenance.kind}
        {showConfidence && typeof c === "number" && (
          <span className="font-mono opacity-70">{(c * 100).toFixed(0)}%</span>
        )}
        {/* An inference with no confidence at all is worth seeing as a gap
            rather than as a badge that merely looks tidy. */}
        {showConfidence && inferred && typeof c !== "number" && (
          <span className="font-mono opacity-70">?</span>
        )}
      </span>
    </Tooltip>
  );
}

/* --- KPIs ----------------------------------------------------------------- */

/** A KPI whose figure counts to its new value when it changes. */
export function Kpi({
  label, value, tone, sub, animate = true, decimals = 0, suffix,
}: {
  label: ReactNode;
  value: number | string;
  tone?: "good" | "bad";
  sub?: ReactNode;
  /** Off for figures that are identifiers rather than quantities. */
  animate?: boolean;
  decimals?: number;
  /** Trails the figure - "%" and nothing else, so far. */
  suffix?: string;
}) {
  const numeric = typeof value === "number";
  const counted = useCountUp(numeric && animate ? value : 0);
  const shown = !numeric
    ? value
    : `${(animate ? counted : value).toFixed(decimals)}${suffix ?? ""}`;
  return <Stat label={label} value={shown} tone={tone} sub={sub} />;
}

/** Which way each figure is supposed to move.
 *
 * `up` and `down` are the good directions; `none` is for a figure that is a
 * magnitude rather than a score - the size of a correction is neither good nor
 * bad, it is just how much work there is.
 */
type Direction = "up" | "down" | "none";

const PIM_KPIS: {
  key: keyof KPIs; label: string; sub: string; dir: Direction;
  decimals: number; suffix?: string;
}[] = [
  { key: "fields_affected", label: "Fields affected",
    sub: "values the correction moves", dir: "none", decimals: 0 },
  { key: "assets_stale", label: "Assets stale",
    sub: "still built on the old value", dir: "down", decimals: 0 },
  { key: "channels_blocked", label: "Channels blocked",
    sub: "cannot publish as they stand", dir: "down", decimals: 0 },
  { key: "listings_ready_pct", label: "Listings ready",
    sub: "pass every channel rule", dir: "up", decimals: 1, suffix: "%" },
  { key: "completeness_pct", label: "Completeness",
    sub: "required fields present", dir: "up", decimals: 1, suffix: "%" },
  { key: "safety_flags", label: "Safety flags",
    sub: "allergen or safety value moved", dir: "down", decimals: 0 },
  { key: "republish_steps", label: "Republish steps",
    sub: "to put the correction live", dir: "down", decimals: 0 },
];

function movementTone(delta: number, dir: Direction): "good" | "bad" | undefined {
  if (dir === "none" || delta === 0) return undefined;
  const good = dir === "up" ? delta > 0 : delta < 0;
  return good ? "good" : "bad";
}

/** KPI strip.
 *
 * `compare` is whatever the reviewer is measuring against - the do-nothing
 * case, or the plan this one supersedes. Showing the movement against it is the
 * only way to read whether a resolution is actually an improvement; the figures
 * on their own say only how big the mess is.
 */
export function KpiStrip({ kpis, compare }: { kpis: KPIs; compare?: KPIs }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(124px,1fr))] gap-2">
      {PIM_KPIS.map((k) => {
        const value = Number(kpis[k.key] ?? 0);
        const before = compare ? Number(compare[k.key] ?? 0) : undefined;
        const delta = before === undefined ? undefined : value - before;
        const tone =
          // A safety flag is never neutral, with or without a baseline.
          k.key === "safety_flags" && value > 0
            ? "bad"
            : delta === undefined
            ? undefined
            : movementTone(delta, k.dir);
        const sub =
          delta === undefined || delta === 0
            ? k.sub
            : `${delta > 0 ? "+" : "-"}${Math.abs(delta).toFixed(k.decimals)}${
                k.suffix === "%" ? " pp" : ""
              } vs before`;
        return (
          <Kpi
            key={k.key}
            label={k.label}
            value={value}
            decimals={k.decimals}
            suffix={k.suffix}
            tone={tone}
            sub={sub}
          />
        );
      })}
    </div>
  );
}

/* --- value diffs ---------------------------------------------------------- */

type MemberChange = "same" | "added" | "removed" | "moved";

const MEMBER_TONE: Record<MemberChange, string> = {
  same: "border-subtle bg-sunken text-muted",
  added: "border-ok-border bg-ok-soft text-ok-text",
  removed: "border-danger-border bg-danger-soft text-danger-text line-through",
  moved: "border-warn-border bg-warn-soft text-warn-text",
};

interface Member { key: string; text: string; change: MemberChange }

/** Occurrence-qualified keys, so a list that legitimately repeats a member
 *  ("sugar" twice) diffs by position rather than collapsing.
 *
 *  The separator is a NUL because an ingredient may contain any printable
 *  character, and a separator an ingredient can contain is one that collides
 *  eventually. Written as the escape and never as the raw byte: a literal
 *  control character in the source makes git, grep and `file` all classify
 *  this module as binary, so it drops out of the searches of whoever comes
 *  to change it. */
function keyed(list: string[]): { key: string; text: string }[] {
  const seen = new Map<string, number>();
  return list.map((raw) => {
    const text = String(raw);
    const n = (seen.get(text) ?? 0) + 1;
    seen.set(text, n);
    return { key: `${text}\u0000${n}`, text };
  });
}

interface ListDiff {
  before: Member[]; after: Member[];
  added: number; removed: number; moved: number;
}

/** Diff two string lists by membership *and* by order.
 *
 * Order is compared over the members the two lists have in common, so an
 * insertion near the front does not report every following member as moved -
 * only members whose rank relative to their surviving neighbours actually
 * changed are called moved.
 */
function diffLists(oldList: string[], newList: string[]): ListDiff {
  const a = keyed(oldList);
  const b = keyed(newList);
  const aKeys = new Set(a.map((x) => x.key));
  const bKeys = new Set(b.map((x) => x.key));

  const rankA = new Map(
    a.filter((x) => bKeys.has(x.key)).map((x, i) => [x.key, i] as const)
  );
  const rankB = new Map(
    b.filter((x) => aKeys.has(x.key)).map((x, i) => [x.key, i] as const)
  );

  const classify = (key: string, side: "before" | "after"): MemberChange => {
    if (side === "before" && !bKeys.has(key)) return "removed";
    if (side === "after" && !aKeys.has(key)) return "added";
    return rankA.get(key) === rankB.get(key) ? "same" : "moved";
  };

  const before = a.map((x) => ({ ...x, change: classify(x.key, "before") }));
  const after = b.map((x) => ({ ...x, change: classify(x.key, "after") }));

  return {
    before,
    after,
    removed: before.filter((m) => m.change === "removed").length,
    added: after.filter((m) => m.change === "added").length,
    moved: after.filter((m) => m.change === "moved").length,
  };
}

function MemberChip({ member, position }: { member: Member; position?: number }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-xs border px-1.5 py-px",
        "text-xs",
        MEMBER_TONE[member.change]
      )}
    >
      {position !== undefined && (
        <span className="font-mono text-2xs opacity-60 no-underline">
          {position}
        </span>
      )}
      {member.text}
    </span>
  );
}

function MemberRow({ label, members, numbered }: {
  label: string; members: Member[]; numbered: boolean;
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="w-11 shrink-0 text-2xs uppercase tracking-caps text-faint">
        {label}
      </span>
      <span className="flex flex-wrap items-center gap-1">
        {members.length === 0 ? (
          <span className="text-sm text-faint">nothing</span>
        ) : (
          members.map((m, i) => (
            <MemberChip
              key={m.key}
              member={m}
              position={numbered ? i + 1 : undefined}
            />
          ))
        )}
      </span>
    </div>
  );
}

function scalarText(v: unknown, unit?: string | null): string {
  if (v === null || v === undefined) return "not set";
  const text = fmt.value(v);
  return unit ? `${text} ${unit}` : text;
}

/** Old value, new value, and what actually differs between them.
 *
 * The single most reused thing on the screen: it is what a supplier correction
 * *is*. Scalars read `45 W → 65 W`. Lists get a real before/after, because in
 * this domain a list is not a set - an ingredient declaration is ordered by
 * law, so swapping two members is a change a reviewer has to approve, not a
 * no-op the diff can quietly swallow.
 *
 * `ordered` only softens the wording: a reorder is always drawn, because a
 * reorder that renders as nothing is the failure mode this component exists to
 * prevent.
 */
export function ValueDiff({
  oldValue, newValue, unit, ordered = true, className,
}: {
  oldValue?: unknown;
  newValue?: unknown;
  unit?: string | null;
  /** From `AttributeDef.ordered`. Defaults to treating order as meaningful. */
  ordered?: boolean;
  className?: string;
}) {
  const isList = Array.isArray(oldValue) || Array.isArray(newValue);

  if (!isList) {
    const from = scalarText(oldValue, unit);
    const to = scalarText(newValue, unit);
    if (from === to) {
      return (
        <span className={cn("text-sm text-faint", className)}>
          {to} <span className="text-2xs uppercase tracking-caps">unchanged</span>
        </span>
      );
    }
    return (
      <span className={cn("inline-flex flex-wrap items-center gap-1.5", className)}>
        <span
          className={cn(
            "rounded-xs border border-subtle bg-sunken px-1.5 py-px",
            "font-mono text-xs text-faint",
            oldValue !== null && oldValue !== undefined && "line-through"
          )}
        >
          {from}
        </span>
        <span aria-hidden="true" className="text-faint">→</span>
        <span className="sr-only">changed to</span>
        <span
          className={cn(
            "rounded-xs border border-accent-border bg-accent-soft px-1.5",
            "py-px font-mono text-xs font-semibold text-accent-text"
          )}
        >
          {to}
        </span>
      </span>
    );
  }

  const oldList = (Array.isArray(oldValue) ? oldValue : []).map((x) => String(x));
  const newList = (Array.isArray(newValue) ? newValue : []).map((x) => String(x));
  const d = diffLists(oldList, newList);
  const pureReorder = d.added === 0 && d.removed === 0 && d.moved > 0;
  const identical = d.added === 0 && d.removed === 0 && d.moved === 0;

  return (
    <div className={cn("flex min-w-0 flex-col gap-1", className)}>
      <div className="flex flex-wrap items-center gap-1.5">
        {d.removed > 0 && (
          <Badge tone="danger">{d.removed} removed</Badge>
        )}
        {d.added > 0 && <Badge tone="ok">{d.added} added</Badge>}
        {d.moved > 0 && (
          <Tooltip
            content={
              ordered
                ? "The order of this list is part of the declaration. Moving a member is a change that has to be approved."
                : "The same members, in a different order."
            }
          >
            <span>
              <Badge tone="warn" dot>
                {pureReorder ? "reordered" : `${d.moved} moved`}
              </Badge>
            </span>
          </Tooltip>
        )}
        {identical && (
          <span className="text-sm text-faint">no change</span>
        )}
      </div>
      <MemberRow label="before" members={d.before} numbered={ordered} />
      <MemberRow label="after" members={d.after} numbered={ordered} />
    </div>
  );
}

/* --- channels ------------------------------------------------------------- */

/** Display names for the six fixed channels.
 *
 * A fallback only - `Channel.name` off the catalog wins whenever the caller has
 * it. It exists so a chip rendered from a bare id in a violation or an action
 * still reads as a place rather than as a code.
 */
export const CHANNEL_NAMES: Record<string, string> = {
  "CH-WEB": "Own website",
  "CH-MKT-A": "Marketplace A",
  "CH-MKT-B": "Marketplace B",
  "CH-PRINT": "Print catalogue",
  "CH-SHELF": "Shelf labels",
  "CH-SEARCH": "Search facets",
};

export type ChannelState = "ready" | "blocked" | "withheld" | "rejected";

const CHANNEL_STATE: Record<ChannelState, {
  tone: BadgeTone; label: string; why: string;
}> = {
  ready: { tone: "ok", label: "ready",
    why: "Prepared and passing every rule this channel binds." },
  blocked: { tone: "danger", label: "blocked",
    why: "Cannot publish: a hard channel rule is failing." },
  withheld: { tone: "warn", label: "held",
    why: "Deliberately held back until a reviewer approves the correction." },
  rejected: { tone: "danger", label: "rejected",
    why: "The channel rejected the last submission and has not accepted a replacement." },
};

const DOT_CLASS: Record<BadgeTone, string> = {
  ok: "bg-ok", warn: "bg-warn", danger: "bg-danger",
  info: "bg-info", accent: "bg-accent", neutral: "bg-faint",
};

/** The state a listing's status puts its channel in. One mapping, so four views
 *  do not each invent their own. */
export function listingChannelState(status?: ListingStatus | string | null):
  ChannelState | undefined {
  switch (status) {
    case "LIVE":
    case "PREPARED":
      return "ready";
    case "WITHHELD":
      return "withheld";
    case "REJECTED":
      return "rejected";
    default:
      return undefined;
  }
}

/** A channel, named, with its id kept and its state carried by colour.
 *
 * Channels are the unit the blast radius is counted in, so they appear in
 * violations, actions, asset rows and the map legend. One chip everywhere.
 */
export function ChannelChip({
  channelId, state, name, className,
}: {
  channelId: string;
  state?: ChannelState;
  /** `Channel.name` where the caller has the catalog. */
  name?: string;
  className?: string;
}) {
  const s = state ? CHANNEL_STATE[state] : undefined;
  const shown = name ?? CHANNEL_NAMES[channelId] ?? channelId;
  const chip = (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full",
        "border border-subtle bg-sunken py-px pl-1.5 pr-2 text-xs",
        className
      )}
    >
      {s && (
        <span className={cn("size-1.5 shrink-0 rounded-full", DOT_CLASS[s.tone])} />
      )}
      <span className="font-medium text-fg">{shown}</span>
      {shown !== channelId && (
        <span className="font-mono text-2xs text-faint">{channelId}</span>
      )}
      {s && <span className="text-2xs uppercase tracking-caps text-muted">{s.label}</span>}
    </span>
  );
  return s ? <Tooltip content={s.why}>{chip}</Tooltip> : chip;
}

/* --- the things that must never be missed ---------------------------------- */

/** Safety flags.
 *
 * An allergen or other safety-class value has moved. This is the one marker on
 * the screen that is allowed to shout: getting it wrong is a recall, not a bad
 * listing. Renders nothing at zero, so its presence always means something.
 */
export function SafetyFlag({ count, className }: {
  count?: number; className?: string;
}) {
  if (!count || count <= 0) return null;
  return (
    <Tooltip content="A safety-class value moved - an allergen, or a machine-read value the safety gate does not trust. Nothing republishes until a reviewer approves it.">
      <span
        className={cn(
          "inline-flex items-center gap-1 whitespace-nowrap rounded-full",
          "border border-danger-border bg-danger-soft px-1.5 py-px",
          "text-xs font-semibold tracking-wide text-danger-text",
          className
        )}
      >
        <IconAlert size={12} />
        {count} safety {count === 1 ? "flag" : "flags"}
      </span>
    </Tooltip>
  );
}

/** Regulated product marker. A statement of fact about the product, carried
 *  everywhere the product is named, because it changes what approval means. */
export function RegulatedTag({ className }: { className?: string }) {
  return (
    <Tooltip content="Regulated product. The ingredient and allergen declarations are legally binding, so no correction to them publishes without review.">
      <span
        className={cn(
          "inline-flex items-center gap-1 whitespace-nowrap rounded-full",
          "border border-warn-border bg-warn-soft px-1.5 py-px",
          "text-xs font-semibold tracking-wide text-warn-text",
          className
        )}
      >
        <span className="size-1.5 shrink-0 rounded-full bg-current" />
        Regulated
      </span>
    </Tooltip>
  );
}

/* --- sources -------------------------------------------------------------- */

const versionLabel = (v: string) =>
  !v ? "" : /^v/i.test(v) ? v : `v${v}`;

/** The document a change came from, with the sentence it came from behind it.
 *
 * Every generated change carries one, and a change that does not is a
 * violation rather than a tidy omission - so the missing case is drawn loudly
 * instead of rendering nothing.
 */
export function SourceCite({ source, onOpen, className }: {
  source?: SourceRef | null;
  onOpen?: () => void;
  className?: string;
}) {
  const openDocument = useOpenDocument();
  if (!source?.doc_id) {
    return (
      <Tooltip content="This change names no source document. Nothing may publish on it.">
        <span>
          <Badge tone="danger" dot>no source</Badge>
        </span>
      </Tooltip>
    );
  }
  const label = `${source.doc_id} ${versionLabel(source.version)}`.trim();
  const body = (
    <>
      <IconDoc size={12} className="shrink-0 text-faint" />
      <span className="font-mono">{label}</span>
    </>
  );
  // `chunk_id` is set only when the source IS the corpus (sc/contracts.py:80).
  // Most of these chips name a *supplier* document - DOC-03, DOC-06 - which
  // lives on the event tape and has no file in the library. Linking those
  // would put a dead control on the busiest screens in the app, so the
  // discriminator the contract already carries is what decides.
  const followable = !onOpen && !!source.chunk_id;
  const act = onOpen
    ?? (followable
        ? () => openDocument(source.doc_id, source.chunk_id ?? undefined)
        : undefined);
  const chip = cn(
    "inline-flex items-center gap-1 whitespace-nowrap rounded-xs border",
    "border-subtle bg-sunken px-1.5 py-px text-xs text-muted",
    act && "cursor-pointer hover:bg-hover hover:text-fg",
    className
  );
  return (
    <Tooltip
      content={
        <span className="block">
          <span className="block text-xs text-faint">
            {label}
            {source.chunk_id ? ` · ${source.chunk_id}` : ""}
          </span>
          <span className="mt-1 block italic">“{source.excerpt}”</span>
        </span>
      }
    >
      {act ? (
        <button type="button" onClick={act} className={chip}>{body}</button>
      ) : (
        <span className={chip}>{body}</span>
      )}
    </Tooltip>
  );
}

/** The far end of the change diff: what is still carrying the old value.
 *  Assets are counted rather than listed - a reviewer wants the number and the
 *  channels; the ids belong in the table underneath. */
export function ImpactedOutputs({ assets, channels, className }: {
  assets?: string[];
  channels?: string[];
  className?: string;
}) {
  const a = assets ?? [];
  const c = channels ?? [];
  if (!a.length && !c.length) {
    return <span className={cn("text-sm text-faint", className)}>nothing downstream</span>;
  }
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1.5", className)}>
      {a.length > 0 && (
        <Tooltip content={a.join("\n")} mono>
          <span className="whitespace-nowrap text-sm text-muted">
            {a.length} {a.length === 1 ? "asset" : "assets"}
          </span>
        </Tooltip>
      )}
      {c.map((id) => <ChannelChip key={id} channelId={id} />)}
    </span>
  );
}

/* --- violations ----------------------------------------------------------- */

/** The validator's constraint names, in the words a reviewer would use.
 *  The raw name stays on the row - it is what the engine logs. */
const VIOLATION_LABEL: Record<string, string> = {
  stale_asset: "content still built on the old value",
  stale_literal: "old value still written into the text",
  channel_schema: "channel schema not satisfied",
  claim_consistency: "claim no longer holds",
  allergen_declaration: "allergen declaration wrong",
  safety_confidence: "safety value not certain enough",
  stale_version: "published version out of date",
  citation_missing: "change cites no source",
  publish_conflict: "another republish holds this channel",
};

const readableConstraint = (c: string) =>
  VIOLATION_LABEL[c] ?? c.replace(/_/g, " ");

/** One rule breach, always naming what bound.
 *
 * A block is shown with its reason rather than hidden: a reviewer needs to know
 * why an obvious-looking resolution is not available, and HARD versus SOFT is
 * the difference between "this cannot publish" and "someone should look".
 *
 * A block element, not a `<tr>` - it drops into a list or a cell unchanged.
 */
export function ViolationRow({ violation, className }: {
  violation: Violation; className?: string;
}) {
  const v = violation;
  const hard = v.severity === "HARD";
  const hasNumbers = Boolean(v.required || v.available);
  return (
    <div className={cn("flex items-start gap-2", className)}>
      <Badge tone={hard ? "danger" : "warn"} dot>
        {hard ? "blocks publish" : "advisory"}
      </Badge>
      <div className="min-w-0 text-sm">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-medium text-fg">
            {readableConstraint(v.constraint)}
          </span>
          <span className="font-mono text-xs text-faint">{v.entity_id}</span>
          {v.channel_id && <ChannelChip channelId={v.channel_id} />}
          {v.bucket_date && (
            <span className="text-xs text-faint">{v.bucket_date}</span>
          )}
        </div>
        {v.detail && <div className="mt-0.5 text-muted">{v.detail}</div>}
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-faint">
          <Code>{v.constraint}</Code>
          {hasNumbers && (
            <span className="font-mono tabular-nums">
              required {v.required.toLocaleString()} · actual{" "}
              {v.available.toLocaleString()}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export function Violations({ violations }: { violations: Violation[] }) {
  if (!violations.length) {
    return <div className="text-sm text-muted">No channel rules broken.</div>;
  }
  return (
    <div className="flex flex-col gap-2">
      {violations.map((v, i) => (
        <ViolationRow key={`${v.constraint}-${v.entity_id}-${i}`} violation={v} />
      ))}
    </div>
  );
}

/* --- actions -------------------------------------------------------------- */

const ACTION_LABEL: Record<string, string> = {
  SET_ATTRIBUTE: "set value",
  REGENERATE_COPY: "rewrite copy",
  REMAP_TAXONOMY: "re-map category",
  SET_FACET: "set facet",
  WITHHOLD_CHANNEL: "hold channel",
  REQUEST_SUPPLIER_INPUT: "ask supplier",
};

const ACTION_TONE: Record<string, BadgeTone> = {
  SET_ATTRIBUTE: "info",
  REGENERATE_COPY: "info",
  REMAP_TAXONOMY: "info",
  SET_FACET: "info",
  WITHHOLD_CHANNEL: "warn",
  REQUEST_SUPPLIER_INPUT: "neutral",
};

export const actionLabel = (kind: string) => ACTION_LABEL[kind] ?? kind;

/** Resolve an id or an attribute path to a name, where the caller has the
 *  catalog to resolve it against. Returning undefined leaves the id on its
 *  own, which is correct - it is never hidden, only ever accompanied. */
export type NameLookup = (key: string) => string | undefined;

/** Either a typed action off the wire or the loose record a table row happens
 *  to be holding. Both are accepted so no caller has to cast. */
export type AnyAction = Action | Record<string, unknown>;

/** One readable sentence per action.
 *
 * The reviewer is deciding whether to republish, so each sentence says what
 * will happen to the catalog rather than naming a verb from the schema.
 * WITHHOLD_CHANNEL reads as a deliberate act, because it is one: the system
 * chose to hold a channel back, and that choice needs approving like any other.
 */
export function describeAction(action: AnyAction, name?: NameLookup): string {
  const p = action as unknown as Record<string, unknown>;
  const raw = (k: string) => (p[k] === undefined || p[k] === null ? "" : String(p[k]));

  /** "Northaven AP300 Max (VAR-01B)" where a name is known, "VAR-01B" where not. */
  const named = (k: string) => {
    const id = raw(k);
    if (!id) return "";
    const n = name?.(id);
    return n && n !== id ? `${n} (${id})` : id;
  };
  const namedValue = (id: string) => {
    if (!id) return "";
    const n = name?.(id);
    return n && n !== id ? `${n} (${id})` : id;
  };
  const attr = (k: string) => {
    const path = raw(k);
    if (!path) return "";
    const n = name?.(path);
    return n && n !== path ? `${n} (${path})` : path;
  };
  const val = (k: string, unitKey = "unit") => {
    const v = p[k];
    if (v === undefined || v === null) return "";
    const unit = raw(unitKey);
    return unit ? `${fmt.value(v)} ${unit}` : fmt.value(v);
  };

  switch (raw("kind")) {
    case "SET_ATTRIBUTE": {
      const to = val("new_value");
      const from = val("old_value");
      const head = `Set ${attr("attribute_path")} on ${named("entity_id")} to ${
        to || "no value"
      }`;
      return from ? `${head}, correcting ${from}.` : `${head}.`;
    }
    case "REGENERATE_COPY": {
      const field = raw("field") || "the copy";
      const asset = raw("asset_id");
      const why = raw("reason");
      const head = `Rewrite the ${field}${asset ? ` (${asset})` : ""} on ${
        namedValue(raw("listing_id")) || "this listing"
      }`;
      return why ? `${head} — ${why}.` : `${head} so it matches the corrected value.`;
    }
    case "REMAP_TAXONOMY":
      return `Move ${namedValue(raw("listing_id"))} out of ${
        raw("from_node")} and into ${raw("to_node")} so the channel accepts it.`;
    case "SET_FACET": {
      const op = raw("op") === "REMOVE" ? "Drop" : "Add";
      const why = raw("reason");
      const head = `${op} the ${raw("facet")} facet on ${
        namedValue(raw("channel_id"))}`;
      return why ? `${head} — ${why}.` : `${head}.`;
    }
    case "WITHHOLD_CHANNEL": {
      // Deliberately an act, not an absence: it is proposed, approved and
      // audited exactly like a value change.
      const channel = namedValue(raw("channel_id")) || "this channel";
      const listing = raw("listing_id");
      const why = raw("reason");
      const head = `Hold ${channel}${listing ? ` for ${listing}` : ""} until a reviewer approves`;
      return why ? `${head}: ${why}.` : `${head}.`;
    }
    case "REQUEST_SUPPLIER_INPUT": {
      const supplier = namedValue(raw("supplier")) || "the supplier";
      const doc = raw("doc_ref");
      const q = raw("question");
      const head = `Ask ${supplier} to clarify${doc ? ` ${doc}` : ""}`;
      return q ? `${head}: ${q}` : `${head}.`;
    }
    default:
      return `${actionLabel(raw("kind"))} — ${JSON.stringify(p)}`;
  }
}

/** The actions in a change set, as chips. The sentence lives in the tooltip so
 *  a dense table can still be read one row at a time. */
export function ActionList({ actions, name }: {
  actions: AnyAction[];
  name?: NameLookup;
}) {
  if (!actions.length) {
    return <Badge tone="neutral">no change — republish nothing</Badge>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {actions.map((a, i) => (
        <Tooltip key={i} content={describeAction(a, name)}>
          <span>
            <Badge tone={ACTION_TONE[String(a.kind)] ?? "info"}>
              {actionLabel(String(a.kind))}
            </Badge>
          </span>
        </Tooltip>
      ))}
    </div>
  );
}

/* --- retrieval and errors -------------------------------------------------- */

export function CitationCard({ c, onOpen }: {
  c: { chunk_id?: string; doc_id: string; title: string; heading: string;
       excerpt: string; doc_type: string };
  onOpen?: () => void;
}) {
  return (
    <div
      onClick={onOpen}
      className={cn(
        "rounded-r-sm border-l-2 border-accent bg-sunken px-2.5 py-2",
        "transition-colors duration-[var(--dur-fast)]",
        onOpen && "cursor-pointer hover:bg-hover"
      )}
    >
      <div className="flex items-center gap-1.5 text-sm">
        <Badge tone="neutral">{c.doc_type}</Badge>
        <span className="font-mono text-xs">{c.doc_id}</span>
        <span className="truncate text-muted">{c.heading || c.title}</span>
      </div>
      <div className="mt-1 text-sm leading-relaxed text-muted">{c.excerpt}</div>
    </div>
  );
}

export function ErrorList({ errors }: { errors?: string[] }) {
  if (!errors?.length) return null;
  return (
    <div className="mb-2.5 flex flex-col gap-1.5">
      {errors.slice(0, 3).map((e, i) => (
        <div key={i} className="flex items-start gap-2 text-sm text-warn-text">
          <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-warn" />
          <span>{e}</span>
        </div>
      ))}
      {errors.length > 3 && (
        <div className="text-sm text-faint">…and {errors.length - 3} more</div>
      )}
    </div>
  );
}
