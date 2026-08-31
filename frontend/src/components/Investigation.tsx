import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { UNSCOPED_CASE, api, fmt } from "../api";
import type {
  Action, AffectedScope, AttributeDef, CaseSummary, CatalogState, CausalLink,
  ChangeScope, Channel, Citation, ClaimFlag, CorrectionSignal, Listing, Product,
  RunSnapshot, RunValues, Variant, Violation,
} from "../api";
import { ArtNoEvidence, ArtNoRun } from "../art/illustrations";
import { PublicationImpact } from "./PublicationImpact";
import { PageHeader } from "../app/shell/PageHeader";
import {
  IconAlert, IconClock, IconDoc, IconRobot, IconScenarios, IconTrace,
} from "../icons";
import {
  Badge, Code, EmptyState, Panel, ProgressBar, Section, Select, Skeleton, Table,
  Td, Th, Tooltip, Tr, cn,
} from "../ui";
import type { BadgeTone } from "../ui";
import { EvidenceLog } from "./EvidenceLog";
import { FactLineage } from "./FactLineage";
import { RevisionBadge } from "./PlanDiffPanel";
import {
  ChannelChip, CitationCard, Kpi, ProvBadge, RegulatedTag, SafetyFlag, Severity,
  SourceCite, ValueDiff, ViolationRow, describeAction, listingChannelState,
} from "./common";
import type { ChannelState, NameLookup } from "./common";

/* Blast radius.
 *
 * One question, answered completely: a correction arrived - what does it touch,
 * how do we know, and what is not safe to publish?
 *
 * The order down the page is the order a reviewer asks it in. What the document
 * says. Which product and which variant it applies to, with the evidence and
 * the readings that lost. Everything downstream of that field, as a hierarchy
 * rather than an edge list. What breaks per channel. Which claims stopped being
 * true. What the agent was allowed to look up. And the history of the corrected
 * value on both time axes.
 *
 * Nothing here originates a figure. Totals come from the lineage walk, breaches
 * from the validator, claim verdicts from the rule table; the component sums
 * ids and pluralises nouns and does nothing else with a number.
 *
 * Two rules run through the whole file. A generated change always shows
 * `source document -> old value -> new value -> impacted outputs`, and an
 * identifier is never hidden - a reviewer searches by DOC-01 and VAR-01B, so
 * every name carries its id somewhere on the row.
 */

/* ========================================================================== *
 * Reading the catalog
 * ========================================================================== */

interface Index {
  loaded: boolean;
  products: Map<string, Product>;
  variants: Map<string, Variant>;
  channels: Map<string, Channel>;
  listings: Map<string, Listing>;
  attributes: Map<string, AttributeDef>;
  /** Channel order as the catalog declares it, so every table agrees. */
  channelOrder: string[];
  name: NameLookup;
}

const EMPTY_INDEX: Index = {
  loaded: false,
  products: new Map(), variants: new Map(), channels: new Map(),
  listings: new Map(), attributes: new Map(), channelOrder: [],
  name: () => undefined,
};

function buildIndex(catalog: CatalogState | null): Index {
  if (!catalog) return EMPTY_INDEX;
  const products = new Map((catalog.products ?? []).map((p) => [p.id, p] as const));
  const variants = new Map((catalog.variants ?? []).map((v) => [v.id, v] as const));
  const channels = new Map((catalog.channels ?? []).map((c) => [c.id, c] as const));
  const listings = new Map((catalog.listings ?? []).map((l) => [l.id, l] as const));
  const attributes = new Map(
    (catalog.attributes ?? []).map((a) => [a.path, a] as const)
  );

  const name: NameLookup = (key) => {
    const listing = listings.get(key);
    if (listing) {
      const variant = variants.get(listing.variant_id)?.name ?? listing.variant_id;
      const channel = channels.get(listing.channel_id)?.name ?? listing.channel_id;
      return `${variant} on ${channel}`;
    }
    return (
      products.get(key)?.name ??
      variants.get(key)?.name ??
      channels.get(key)?.name ??
      attributes.get(key)?.label
    );
  };

  return {
    loaded: true, products, variants, channels, listings, attributes,
    channelOrder: (catalog.channels ?? []).map((c) => c.id),
    name,
  };
}

/** "Northaven AP300 Max" where the catalog is loaded, "VAR-01B" where it is not.
 *  Never a bare enum, never a lost id - the id rides alongside in the markup. */
const label = (index: Index, id: string) => index.name(id) ?? id;

/** Qualified references arrive as "VAR-01B:specs.power_w". */
function splitRef(ref: string): [string, string] {
  const at = ref.indexOf(":");
  return at === -1 ? [ref, ""] : [ref.slice(0, at), ref.slice(at + 1)];
}

const plural = (n: number, one: string, many = `${one}s`) =>
  `${fmt.count(n)} ${n === 1 ? one : many}`;

/* ========================================================================== *
 * Reading the run
 *
 * Three shapes on the wire differ from the ones api.ts declares. Rather than
 * edit the contract or cast at every use site, each is read once here, with
 * the divergence named. api.ts stays the compile-time authority; these
 * functions are what keep the page rendering against the running backend.
 * ========================================================================== */

const EMPTY_SCOPE: AffectedScope = {
  products: [], variants: [], attributes: [], assets: [], listings: [],
  channels: [],
};

function asScope(raw: Partial<AffectedScope> | undefined): AffectedScope {
  return {
    products: raw?.products ?? [],
    variants: raw?.variants ?? [],
    attributes: raw?.attributes ?? [],
    assets: raw?.assets ?? [],
    listings: raw?.listings ?? [],
    channels: raw?.channels ?? [],
  };
}

/** The scope a run recorded.
 *
 * api.ts declares `RunValues.affected` as the scope itself; the graph stores
 * the lineage analyst's whole answer, so on the wire the scope sits one level
 * down under `affected.affected`. Both readings are accepted.
 */
function runScope(affected: RunValues["affected"]): AffectedScope {
  if (!affected) return EMPTY_SCOPE;
  const nested = (affected as unknown as { affected?: Partial<AffectedScope> })
    .affected;
  return asScope((nested ?? affected) as Partial<AffectedScope>);
}

type Totals = Record<string, number | string[]>;

/** Totals are counts or the id lists behind them; either answers "how many". */
function total(totals: Totals | undefined, key: string): number {
  const value = totals?.[key];
  if (typeof value === "number") return value;
  return Array.isArray(value) ? value.length : 0;
}

/** One claim flag, however the scan phrased it.
 *
 * api.ts declares `{claim, entity_id, detail, upheld}`; the scan node emits
 * `{claim, asset_id, listing_id, excerpt, why, severity, status, confidence}`.
 * `upheld` and `status === "CONFIRMED"` are the same verdict - the rule table
 * agreed - and that verdict is the only thing that separates a finding from a
 * suggestion, so it is read from whichever field is present.
 */
interface ReadClaim {
  claim: string;
  entity: string;
  listing: string;
  detail: string;
  excerpt: string;
  upheld: boolean;
}

function readClaim(flag: ClaimFlag): ReadClaim {
  const raw = flag as unknown as Record<string, unknown>;
  const text = (key: string) =>
    typeof raw[key] === "string" ? (raw[key] as string) : "";
  return {
    claim: flag.claim ?? text("claim"),
    entity: flag.entity_id || text("asset_id"),
    listing: text("listing_id"),
    detail: flag.detail || text("why"),
    excerpt: text("excerpt"),
    upheld: flag.upheld ?? text("status") === "CONFIRMED",
  };
}

/** The deterministic verdict, from the last pass that produced one. */
function boundViolations(v: RunValues): Violation[] {
  return (
    v.final_validation?.violations ??
    v.recommendation?.violations ??
    v.ranked?.[0]?.violations ??
    []
  );
}

/** A correction that moves a value, as against a notice that reports a
 *  rejection or withdraws a document. Only the first kind has an old -> new. */
const movesAValue = (s: CorrectionSignal) =>
  (s.attribute_paths?.length ?? 0) > 0 && s.new_value !== undefined;

/* ========================================================================== *
 * 1 - the correction, stated plainly
 * ========================================================================== */

const CORRECTION_WORDS: Record<string, string> = {
  SPEC_CORRECTION: "corrected specification",
  ALLERGEN_CHANGE: "allergen change",
  INGREDIENT_CHANGE: "ingredient change",
  SOURCE_CONFLICT: "sources disagree",
  CHANNEL_REJECTION: "channel rejected the listing",
  DOC_WITHDRAWN: "document withdrawn",
  DATA_GAP: "value missing",
};

const CORRECTION_TONE: Record<string, BadgeTone> = {
  SPEC_CORRECTION: "info",
  ALLERGEN_CHANGE: "danger",
  INGREDIENT_CHANGE: "warn",
  SOURCE_CONFLICT: "warn",
  CHANNEL_REJECTION: "danger",
  DOC_WITHDRAWN: "warn",
  DATA_GAP: "warn",
};

function CorrectionCard({ signal, index, isRoot }: {
  signal: CorrectionSignal;
  index: Index;
  isRoot: boolean;
}) {
  const path = signal.attribute_paths?.[0] ?? "";
  const def = index.attributes.get(path);
  const inferred = signal.provenance?.kind === "INFERRED";
  const unit = signal.unit ?? def?.unit ?? null;

  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-2.5 rounded-sm border p-3",
        isRoot
          ? "border-accent-border bg-accent-soft/30"
          : "border-subtle bg-sunken"
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={CORRECTION_TONE[signal.kind] ?? "neutral"} dot>
          {CORRECTION_WORDS[signal.kind] ?? signal.kind}
        </Badge>
        {isRoot && <Badge tone="accent">the correction</Badge>}
        {signal.provisional && (
          <Tooltip content="The supplier marked this provisional. Nothing publishes on a provisional value.">
            <span><Badge tone="warn">provisional</Badge></span>
          </Tooltip>
        )}
        {signal.resolves_issue && (
          <Tooltip content="This notice clears an earlier one rather than revising a value.">
            <span><Badge tone="ok">clears an earlier notice</Badge></span>
          </Tooltip>
        )}
        <span className="ml-auto font-mono text-2xs text-faint">{signal.id}</span>
      </div>

      <p className="text-sm leading-relaxed text-fg">{signal.summary}</p>

      <dl className="grid gap-x-4 gap-y-2 sm:grid-cols-[auto_minmax(0,1fr)]">
        <Row term="Field">
          <span className="text-sm text-fg">{def?.label ?? path ?? "—"}</span>
          {path && <Code>{path}</Code>}
          {def?.safety_class && (
            <Tooltip content="A safety-class value. Below the confidence threshold it withholds every listing of this entity rather than degrading them.">
              <span><Badge tone="danger" dot>safety</Badge></span>
            </Tooltip>
          )}
          {def?.ordered && (
            <Tooltip content="The order of this list is part of the declaration - reordering it is a change a reviewer must approve.">
              <span><Badge tone="warn">order matters</Badge></span>
            </Tooltip>
          )}
        </Row>

        <Row term="Change">
          <ValueDiff
            oldValue={signal.old_value}
            newValue={signal.new_value}
            unit={unit}
            ordered={def?.ordered ?? true}
          />
        </Row>

        <Row term="Named">
          {(signal.entities ?? []).length === 0 ? (
            <span className="text-sm text-faint">
              no entity named — the scope has to be resolved
            </span>
          ) : (
            signal.entities.map((id) => (
              <span key={id} className="inline-flex items-center gap-1 text-sm">
                {label(index, id)}
                <Code>{id}</Code>
              </span>
            ))
          )}
        </Row>

        <Row term="From">
          <SourceCite source={signal.source} />
          <ProvBadge provenance={signal.provenance} />
        </Row>

        <Row term="Effective">
          <span className="font-mono text-xs tabular-nums text-muted">
            {signal.window_start ? fmt.date(signal.window_start) : "immediately"}
            {signal.window_end && ` → ${fmt.date(signal.window_end)}`}
          </span>
          <Tooltip content="When the correction was detected on the tape">
            <span className="font-mono text-xs tabular-nums text-faint">
              detected {fmt.stamp(signal.detected_at)}
            </span>
          </Tooltip>
        </Row>
      </dl>

      {signal.source?.excerpt && (
        <blockquote
          className={cn(
            "rounded-r-sm border-l-2 border-accent bg-raised px-2.5 py-2",
            "text-sm leading-relaxed text-muted"
          )}
        >
          “{signal.source.excerpt}”
          <span className="mt-1 block font-mono text-2xs text-faint">
            {signal.source.doc_id} {signal.source.version}
            {signal.source.chunk_id ? ` · ${signal.source.chunk_id}` : ""}
          </span>
        </blockquote>
      )}

      {inferred && <InferredNotice signal={signal} />}
    </div>
  );
}

/** A machine read this off a document.
 *
 * The single most important qualifier on the page. A figure off a structured
 * feed and a figure a model lifted out of a PDF sentence are not the same
 * claim, and the second one is the one that has to be read before it is
 * approved - so it is stated in words, not left to a badge.
 */
function InferredNotice({ signal }: { signal: CorrectionSignal }) {
  const confidence = signal.provenance?.confidence;
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-sm border border-warn-border",
        "bg-warn-soft/60 px-2.5 py-2"
      )}
    >
      <IconRobot size={15} className="mt-0.5 shrink-0 text-warn-text" />
      <div className="min-w-0 text-sm leading-relaxed">
        <span className="font-medium text-warn-text">
          A model read this out of the document.
        </span>{" "}
        <span className="text-muted">
          Nothing on a feed states it. The excerpt above is the sentence it was
          read from, and the value below it is the model’s reading of that
          sentence
          {typeof confidence === "number"
            ? `, offered at ${(confidence * 100).toFixed(0)}% confidence`
            : ", with no confidence attached"}
          . Read the excerpt before approving anything built on it.
        </span>
      </div>
    </div>
  );
}

function Row({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-2xs uppercase tracking-caps text-faint sm:pt-0.5">
        {term}
      </dt>
      <dd className="flex min-w-0 flex-wrap items-center gap-1.5">{children}</dd>
    </>
  );
}

/* ========================================================================== *
 * 2 - scope resolution
 * ========================================================================== */

const SCOPE_WORDS: Record<string, string> = {
  BASE: "the base product only",
  VARIANT: "the named variant only",
  ALL: "every variant",
};

/** Evidence references arrive as "variant_diff:PRD-01" / "source:DOC-02". */
function evidenceWords(ref: string): { kind: string; body: string } {
  const [head, tail] = splitRef(ref);
  if (head === "source") return { kind: "document", body: tail };
  if (head === "variant_diff") return { kind: "variant table", body: tail };
  return { kind: head, body: tail || head };
}

function ScopeCandidate({ scope, chosen, index }: {
  scope: ChangeScope;
  chosen: boolean;
  index: Index;
}) {
  const pct = Math.round((scope.confidence ?? 0) * 100);
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-2 rounded-sm border p-2.5",
        chosen
          ? "border-ok-border bg-ok-soft/40"
          : "border-subtle bg-sunken opacity-90"
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={chosen ? "ok" : "neutral"} dot={chosen}>
          {chosen ? "chosen" : "not taken"}
        </Badge>
        <span className="text-sm font-medium text-fg">
          {SCOPE_WORDS[scope.level] ?? scope.level}
        </span>
        <Code>{scope.level}</Code>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {(scope.entities ?? []).map((id) => (
          <span
            key={id}
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-1.5 py-px",
              "text-xs",
              chosen
                ? "border-ok-border bg-raised text-fg"
                : "border-subtle bg-raised text-muted"
            )}
          >
            {label(index, id)}
            <span className="font-mono text-2xs text-faint">{id}</span>
          </span>
        ))}
      </div>

      {scope.rationale && (
        <p className="text-sm leading-relaxed text-muted">{scope.rationale}</p>
      )}

      <div className="flex items-center gap-2">
        <span className="w-20 shrink-0 text-2xs uppercase tracking-caps text-faint">
          support
        </span>
        <ProgressBar
          value={pct}
          tone={chosen ? "ok" : "accent"}
          className="max-w-[160px] flex-1"
          ariaLabel={`Support for ${scope.level}`}
        />
        <span className="font-mono text-xs tabular-nums text-muted">{pct}%</span>
      </div>

      {(scope.evidence ?? []).length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-2xs uppercase tracking-caps text-faint">
            stands on
          </span>
          {scope.evidence.map((ref) => {
            const e = evidenceWords(ref);
            return (
              <Tooltip key={ref} content={ref} mono>
                <span className="inline-flex items-center gap-1 text-xs text-muted">
                  <IconDoc size={11} className="text-faint" />
                  {e.kind} <Code>{e.body}</Code>
                </span>
              </Tooltip>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* --- the variant attribute table ----------------------------------------- */

interface Cell {
  value: unknown;
  doc: string;
  version: string;
  provenance: string;
  confidence: number | null;
}

interface VariantRow {
  path: string;
  label: string;
  unit: string | null;
  safety: boolean;
  differs: boolean;
  cells: Record<string, Cell | undefined>;
}

interface VariantTable {
  variants: Variant[];
  rows: VariantRow[];
}

/** One cell of the variant table.
 *
 * api.ts types a cell as `unknown`, which is exactly right: the endpoint
 * answers with the value *and* the document version it stands on, and that
 * pairing is the whole of the scope argument - the base model's wattage
 * carries the portal feed that certified it, not the spec sheet that was later
 * corrected. A bare scalar is accepted too.
 */
function readCell(raw: unknown): Cell | undefined {
  if (raw === undefined || raw === null) return undefined;
  if (typeof raw === "object" && !Array.isArray(raw) && "value" in raw) {
    const o = raw as Record<string, unknown>;
    return {
      value: o.value,
      doc: typeof o.doc === "string" ? o.doc : "",
      version: typeof o.version === "string" ? o.version : "",
      provenance: typeof o.provenance === "string" ? o.provenance : "",
      confidence: typeof o.confidence === "number" ? o.confidence : null,
    };
  }
  return { value: raw, doc: "", version: "", provenance: "", confidence: null };
}

/** The variant table, from either shape the endpoint answers with.
 *
 * api.ts declares `attributes` as `path -> variant -> value` with a separate
 * `differs` list; the running `variant_diff` answers with a row per attribute
 * carrying its own label, unit, safety class and `differs` flag. Both are read,
 * because the table is the deciding evidence in the scope story and an empty
 * panel here loses the argument.
 */
function readVariantTable(
  answer: Awaited<ReturnType<typeof api.variants>> | null,
  index: Index,
): VariantTable | null {
  if (!answer) return null;
  const raw = answer as unknown as Record<string, unknown>;

  const variants: Variant[] = Array.isArray(answer.variants)
    ? (answer.variants as Variant[])
    : [];

  const rows: VariantRow[] = [];
  const attributes = raw.attributes;

  if (Array.isArray(attributes)) {
    for (const entry of attributes as Record<string, unknown>[]) {
      const path = String(entry.path ?? "");
      const values = (entry.values ?? {}) as Record<string, unknown>;
      const cells: Record<string, Cell | undefined> = {};
      for (const variant of variants) cells[variant.id] = readCell(values[variant.id]);
      rows.push({
        path,
        label: String(entry.label ?? index.attributes.get(path)?.label ?? path),
        unit: typeof entry.unit === "string" ? entry.unit : null,
        safety: Boolean(entry.safety_class ?? index.attributes.get(path)?.safety_class),
        differs: Boolean(entry.differs),
        cells,
      });
    }
  } else if (attributes && typeof attributes === "object") {
    const differs = new Set(
      Array.isArray(answer.differs) ? (answer.differs as string[]) : []
    );
    for (const [path, byVariant] of Object.entries(
      attributes as Record<string, Record<string, unknown>>
    )) {
      const cells: Record<string, Cell | undefined> = {};
      for (const variant of variants) cells[variant.id] = readCell(byVariant?.[variant.id]);
      const def = index.attributes.get(path);
      rows.push({
        path,
        label: def?.label ?? path,
        unit: def?.unit ?? null,
        safety: Boolean(def?.safety_class),
        differs: differs.has(path),
        cells,
      });
    }
  }

  rows.sort((a, b) => a.path.localeCompare(b.path));
  return { variants, rows };
}

function VariantMatrix({ table, highlight, index }: {
  table: VariantTable;
  /** The corrected attribute. Its row is the one the argument turns on. */
  highlight: string;
  index: Index;
}) {
  const { variants, rows } = table;
  if (!variants.length || !rows.length) {
    return (
      <EmptyState compact title="No variant table">
        The catalog holds no attribute table for this product.
      </EmptyState>
    );
  }
  return (
    <Table scroll>
      <thead>
        <tr>
          <Th>Field</Th>
          {variants.map((v) => (
            <Th key={v.id}>
              <span className="flex flex-col gap-0.5">
                <span className="normal-case tracking-normal text-fg">
                  {v.name}
                </span>
                <span className="font-mono text-2xs lowercase tracking-normal text-faint">
                  {v.id} {v.is_base ? "· base" : "· variant"}
                </span>
              </span>
            </Th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const isSubject = row.path === highlight;
          return (
            <Tr
              key={row.path}
              className={cn(isSubject && "bg-accent-soft/40")}
            >
              <Td>
                <div className="flex flex-col gap-0.5">
                  <span className="flex flex-wrap items-center gap-1.5 text-sm">
                    {row.label}
                    {isSubject && <Badge tone="accent">corrected</Badge>}
                    {row.safety && <Badge tone="danger" dot>safety</Badge>}
                    {row.differs && !isSubject && (
                      <Tooltip content="The variants disagree on this field already - it is not the correction that split them.">
                        <span><Badge tone="warn">differs</Badge></span>
                      </Tooltip>
                    )}
                  </span>
                  <Code>{row.path}</Code>
                </div>
              </Td>
              {variants.map((v) => {
                const cell = row.cells[v.id];
                return (
                  <Td key={v.id}>
                    {!cell ? (
                      <span className="text-sm text-faint">not set</span>
                    ) : (
                      <div className="flex flex-col gap-0.5">
                        <span className="font-mono text-sm tabular-nums text-fg">
                          {fmt.value(cell.value)}
                          {row.unit ? ` ${row.unit}` : ""}
                        </span>
                        {cell.doc && (
                          <Tooltip
                            content={
                              `Stands on ${cell.doc} ${cell.version}`.trim() +
                              (cell.provenance ? ` · ${cell.provenance}` : "")
                            }
                          >
                            <span className="font-mono text-2xs text-faint">
                              {cell.doc} {cell.version}
                            </span>
                          </Tooltip>
                        )}
                      </div>
                    )}
                  </Td>
                );
              })}
            </Tr>
          );
        })}
      </tbody>
    </Table>
  );
}

/* ========================================================================== *
 * 3 - the blast radius
 * ========================================================================== */

/** The words each relation carries. The walk is structural, so these are
 *  labels rather than an argument, and they are the vocabulary the hierarchy
 *  is read with. */
const RELATION_WORDS: Record<string, string> = {
  supersedes: "replaces the version the copy was written against",
  defines: "is the document that asserts this value",
  contains: "is a sellable form of this product",
  derives: "was written from this value",
  lists_on: "is published through this listing",
  feeds: "sends this listing to the channel",
};

interface AssetHop {
  id: string;
  listing: string;
  channel: string;
  owner: string;
  /** The asset sits on a listing for a *different* variant than the one whose
   *  value it quotes. The comparison table on the base model's page. */
  cross: boolean;
}

interface AttrHop {
  ref: string;
  entity: string;
  path: string;
  assets: AssetHop[];
  /** Listings reached through the variant itself rather than through a quote. */
  listings: string[];
}

interface DocHop {
  ref: string;
  doc: string;
  version: string;
  replaces: string;
  attributes: AttrHop[];
}

interface Propagation {
  docs: DocHop[];
  unsourced: AttrHop[];
  /** Every asset the walk reached, flat - the per-channel table counts from
   *  this rather than waiting for a plan to propose the rewrites. */
  assets: AssetHop[];
  cross: AssetHop[];
}

/** The hops that lead to one corrected field.
 *
 * The run records the walk over every correction it read at once; this panel
 * shows one field at a time, so the tree is narrowed to what that field
 * reaches, plus the document edge leading into it and the version that
 * document replaced. Nothing is recomputed - rows are only dropped.
 */
function chainFrom(chain: CausalLink[], ref: string): CausalLink[] {
  const [entity] = splitRef(ref);
  if (!ref || !chain.some((l) => l.from_ref === ref || l.to_ref === ref)) {
    return chain;
  }

  const keep = new Set<string>([ref, entity]);
  for (let grew = true; grew; ) {
    grew = false;
    for (const link of chain) {
      if (link.relation === "supersedes") continue;
      if (keep.has(link.from_ref) && !keep.has(link.to_ref)) {
        keep.add(link.to_ref);
        grew = true;
      }
    }
  }

  const docs = chain
    .filter((l) => l.relation === "defines" && l.to_ref === ref)
    .map((l) => l.from_ref);
  for (const doc of docs) keep.add(doc);
  for (const link of chain) {
    if (link.relation === "supersedes" && keep.has(link.from_ref)) {
      keep.add(link.to_ref);
    }
  }

  return chain.filter((l) => keep.has(l.from_ref) && keep.has(l.to_ref));
}

function push<T>(map: Map<string, T[]>, key: string, value: T) {
  const list = map.get(key);
  if (list) list.push(value);
  else map.set(key, [value]);
}

/** The lineage walk, folded into the hierarchy a reviewer reads:
 *
 *    source document -> attribute -> variants -> assets -> listings -> channels
 *
 * Every edge below is one the catalog already holds. Assets are the targets of
 * `derives`, which is what lets an asset be told from a variant on the
 * `lists_on` edges without needing the catalog to have loaded.
 */
function propagate(chain: CausalLink[], index: Index): Propagation {
  const assetIds = new Set(
    chain.filter((l) => l.relation === "derives").map((l) => l.to_ref)
  );

  const definedBy = new Map<string, string>();
  const replaces = new Map<string, string>();
  const derives = new Map<string, string[]>();
  const assetListing = new Map<string, string>();
  const variantListings = new Map<string, string[]>();
  const listingChannel = new Map<string, string>();

  for (const link of chain) {
    switch (link.relation) {
      case "supersedes":
        replaces.set(link.from_ref, link.to_ref);
        break;
      case "defines":
        definedBy.set(link.to_ref, link.from_ref);
        break;
      case "derives":
        push(derives, link.from_ref, link.to_ref);
        break;
      case "lists_on":
        if (assetIds.has(link.from_ref)) assetListing.set(link.from_ref, link.to_ref);
        else push(variantListings, link.from_ref, link.to_ref);
        break;
      case "feeds":
        listingChannel.set(link.from_ref, link.to_ref);
        break;
      default:
        break;
    }
  }

  const variantOfListing = (listing: string): string => {
    const known = index.listings.get(listing)?.variant_id;
    if (known) return known;
    for (const [variant, listings] of variantListings) {
      if (listings.includes(listing)) return variant;
    }
    return "";
  };

  const attrRefs = new Set<string>([...definedBy.keys(), ...derives.keys()]);
  const cross: AssetHop[] = [];
  const reached: AssetHop[] = [];

  const hopFor = (ref: string): AttrHop => {
    const [entity, path] = splitRef(ref);
    const assets = (derives.get(ref) ?? []).sort().map((id) => {
      const listing = assetListing.get(id) ?? "";
      const onto = variantOfListing(listing);
      const hop: AssetHop = {
        id,
        listing,
        channel: listingChannel.get(listing) ?? index.listings.get(listing)?.channel_id ?? "",
        owner: onto,
        cross: Boolean(entity && onto && onto !== entity),
      };
      if (hop.cross) cross.push(hop);
      reached.push(hop);
      return hop;
    });
    const direct = (variantListings.get(entity) ?? [])
      .filter((l) => !assets.some((a) => a.listing === l))
      .sort();
    return { ref, entity, path, assets, listings: direct };
  };

  const byDoc = new Map<string, AttrHop[]>();
  const unsourced: AttrHop[] = [];
  for (const ref of [...attrRefs].sort()) {
    const hop = hopFor(ref);
    const doc = definedBy.get(ref);
    if (doc) push(byDoc, doc, hop);
    else unsourced.push(hop);
  }

  const docs: DocHop[] = [...byDoc.keys()].sort().map((ref) => {
    const [doc, version] = splitRef(ref);
    return {
      ref, doc, version,
      replaces: splitRef(replaces.get(ref) ?? "")[1],
      attributes: byDoc.get(ref) ?? [],
    };
  });

  return { docs, unsourced, assets: reached, cross };
}

/** The sentence a reviewer would say out loud. */
function blastSentence(subject: string, totals: Totals | undefined): string {
  const assets = total(totals, "assets");
  const listings = total(totals, "listings");
  const channels = total(totals, "channels");
  if (!assets && !listings && !channels) {
    return `${subject} reaches nothing that has been published.`;
  }
  return (
    `${subject} reaches ${plural(assets, "asset")} across ` +
    `${plural(listings, "listing")} on ${plural(channels, "channel")}.`
  );
}

function PropagationTree({ tree, index }: { tree: Propagation; index: Index }) {
  if (tree.docs.length === 0 && tree.unsourced.length === 0) {
    return (
      <EmptyState compact title="No propagation drawn">
        The lineage walk returned no edges for this field. The counts above
        still stand — they are the walk’s own totals.
      </EmptyState>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {tree.docs.map((doc) => (
        <div key={doc.ref} className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <IconDoc size={14} className="shrink-0 text-faint" />
            <span className="text-sm font-medium text-fg">{doc.doc}</span>
            <Badge tone="neutral" mono>{doc.version || "current"}</Badge>
            {doc.replaces && (
              <Tooltip content={RELATION_WORDS.supersedes}>
                <span>
                  <Badge tone="warn">replaces {doc.replaces}</Badge>
                </span>
              </Tooltip>
            )}
            <span className="text-xs text-faint">source document</span>
          </div>
          <div className="ml-[7px] flex flex-col gap-2 border-l border-dashed border-strong pl-3.5">
            {doc.attributes.map((attr) => (
              <AttrBranch key={attr.ref} attr={attr} index={index} />
            ))}
          </div>
        </div>
      ))}

      {tree.unsourced.length > 0 && (
        <div className="flex min-w-0 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <IconAlert size={14} className="shrink-0 text-danger-text" />
            <span className="text-sm font-medium text-danger-text">
              No source document named
            </span>
            <span className="text-xs text-faint">
              nothing may publish on a value with no citation
            </span>
          </div>
          <div className="ml-[7px] flex flex-col gap-2 border-l border-dashed border-danger-border pl-3.5">
            {tree.unsourced.map((attr) => (
              <AttrBranch key={attr.ref} attr={attr} index={index} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function AttrBranch({ attr, index }: { attr: AttrHop; index: Index }) {
  const def = index.attributes.get(attr.path);
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex flex-wrap items-baseline gap-1.5">
        <Tooltip content={RELATION_WORDS.defines}>
          <span className="text-2xs uppercase tracking-caps text-faint">
            defines
          </span>
        </Tooltip>
        <span className="text-sm font-medium text-fg">
          {def?.label ?? attr.path}
        </span>
        <span className="text-xs text-muted">
          on {label(index, attr.entity)}
        </span>
        <Code>{attr.ref}</Code>
        {def?.safety_class && <Badge tone="danger" dot>safety</Badge>}
      </div>

      {attr.assets.length === 0 && attr.listings.length === 0 ? (
        <p className="pl-3.5 text-sm text-faint">
          No prepared content was built from this field.
        </p>
      ) : (
        <div className="ml-[7px] flex flex-col gap-1 border-l border-dashed border-subtle pl-3.5">
          {attr.assets.map((asset) => (
            <AssetLine key={asset.id} asset={asset} index={index} />
          ))}
          {attr.listings.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
              <Tooltip content={RELATION_WORDS.lists_on}>
                <span className="text-2xs uppercase tracking-caps text-faint">
                  also lists on
                </span>
              </Tooltip>
              {attr.listings.map((id) => (
                <Tooltip key={id} content={label(index, id)}>
                  <span><Code>{id}</Code></span>
                </Tooltip>
              ))}
              <span className="text-xs text-faint">
                — carried by the variant, not quoted in the copy
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AssetLine({ asset, index }: { asset: AssetHop; index: Index }) {
  const listing = index.listings.get(asset.listing);
  const state = listingChannelState(listing?.status);
  return (
    <div
      className={cn(
        "flex min-w-0 flex-wrap items-center gap-1.5 rounded-xs px-1.5 py-1",
        asset.cross && "border border-warn-border bg-warn-soft/50"
      )}
    >
      <Tooltip content={RELATION_WORDS.derives}>
        <span className="text-2xs uppercase tracking-caps text-faint">
          derives
        </span>
      </Tooltip>
      <Code>{asset.id}</Code>
      <span aria-hidden="true" className="text-faint">→</span>
      <Tooltip content={label(index, asset.listing)}>
        <span className="font-mono text-xs text-muted">{asset.listing}</span>
      </Tooltip>
      <span aria-hidden="true" className="text-faint">→</span>
      {asset.channel ? (
        <ChannelChip
          channelId={asset.channel}
          name={index.channels.get(asset.channel)?.name}
          state={state}
        />
      ) : (
        <span className="text-xs text-faint">no channel</span>
      )}
      {asset.cross && (
        <Tooltip content="This copy quotes another variant's value. Correcting that variant drags this page into scope even though the correction never named it.">
          <span>
            <Badge tone="warn" dot>
              on {label(index, asset.owner)}
            </Badge>
          </span>
        </Tooltip>
      )}
    </div>
  );
}

function CrossVariantNotice({ hits, index }: {
  hits: AssetHop[];
  index: Index;
}) {
  if (hits.length === 0) return null;
  const pages = [...new Set(hits.map((h) => h.owner).filter(Boolean))];
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-sm border border-warn-border",
        "bg-warn-soft/60 px-3 py-2.5"
      )}
    >
      <IconTrace size={16} className="mt-0.5 shrink-0 text-warn-text" />
      <div className="min-w-0 text-sm leading-relaxed">
        <span className="font-medium text-warn-text">
          The correction reaches a page it never named.
        </span>{" "}
        <span className="text-muted">
          {plural(hits.length, "content asset")} on{" "}
          {pages.map((id, i) => (
            <span key={id}>
              {i > 0 && ", "}
              <strong className="font-medium text-fg">{label(index, id)}</strong>
              <span className="font-mono text-xs text-faint"> ({id})</span>
            </span>
          ))}{" "}
          {hits.length === 1 ? "quotes" : "quote"} the corrected variant’s value —
          a shared comparison table is built from both variants at once, so the
          base product’s page goes stale too. Nothing in the supplier’s notice
          says so; the derivation record does.
        </span>
      </div>
    </div>
  );
}

/* ========================================================================== *
 * 4 - per-channel impact
 * ========================================================================== */

interface ChannelRow {
  id: string;
  name: string;
  listings: string[];
  assets: number;
  violations: Violation[];
  hard: number;
  soft: number;
  ruleFields: string[];
  freezeDays: number;
  chipState?: ChannelState;
  state: { label: string; tone: BadgeTone; why: string };
  steps: string[];
}

const STATE_HELP = {
  blocked: "A hard channel rule is failing. Nothing publishes here until it passes.",
  held: "Held back deliberately until a reviewer approves the correction.",
  rejected: "The channel rejected the last submission and has not accepted a replacement.",
  stale: "Publishable as it stands, but the copy is still built on the old value.",
  ready: "Prepared, consistent, and passing every rule this channel binds.",
};

/** One row per affected channel: what is on it, what breaks, and what has to
 *  happen before it republishes. Every clause names something the API said. */
function channelRows(
  scope: AffectedScope,
  violations: Violation[],
  actions: Action[],
  index: Index,
  requiresReview: boolean,
  reached: AssetHop[],
): ChannelRow[] {
  const listingsOn = new Map<string, string[]>();
  for (const id of scope.listings) {
    const channel = index.listings.get(id)?.channel_id;
    if (channel) push(listingsOn, channel, id);
  }

  const order = index.channelOrder.length ? index.channelOrder : scope.channels;
  const ids = order.filter((id) => scope.channels.includes(id));
  for (const id of scope.channels) if (!ids.includes(id)) ids.push(id);

  return ids.map((id) => {
    const listings = listingsOn.get(id) ?? [];
    const onChannel = violations.filter(
      (x) =>
        x.channel_id === id ||
        (!x.channel_id && listings.some((l) => x.entity_id.startsWith(l)))
    );
    const hard = onChannel.filter((x) => x.severity === "HARD").length;
    const soft = onChannel.length - hard;

    const held = listings.some(
      (l) => index.listings.get(l)?.status === "WITHHELD"
    ) || actions.some(
      (a) => a.kind === "WITHHOLD_CHANNEL" &&
        (a.channel_id === id || listings.includes(a.listing_id))
    );
    const rejected = listings.some(
      (l) => index.listings.get(l)?.status === "REJECTED"
    );

    // Two different facts, and the difference matters before a plan exists:
    // `assets` is what the lineage walk found sitting on the old value, and
    // `rewrites` is what a resolution has actually proposed rewriting.
    const assets = reached.filter((hop) => hop.channel === id).length;
    const rewrites = actions.filter(
      (a) => a.kind === "REGENERATE_COPY" && listings.includes(a.listing_id)
    ).length;

    const channel = index.channels.get(id);
    const freezeDays = channel?.freeze_days ?? 0;
    const ruleFields = [
      ...new Set(onChannel.map((x) => splitRef(x.entity_id)[1]).filter(Boolean)),
    ];

    const state = rejected
      ? { label: "rejected", tone: "danger" as BadgeTone, why: STATE_HELP.rejected }
      : hard > 0
      ? { label: "blocked", tone: "danger" as BadgeTone, why: STATE_HELP.blocked }
      : held
      ? { label: "held", tone: "warn" as BadgeTone, why: STATE_HELP.held }
      : rewrites > 0 || assets > 0 || soft > 0
      ? { label: "stale", tone: "warn" as BadgeTone, why: STATE_HELP.stale }
      : { label: "ready", tone: "ok" as BadgeTone, why: STATE_HELP.ready };

    const steps: string[] = [];
    if (hard > 0) steps.push(`fix ${plural(hard, "rule failure")}`);
    if (rewrites > 0) steps.push(`rewrite ${plural(rewrites, "asset")}`);
    else if (assets > 0) steps.push(`rebuild ${plural(assets, "asset")}`);
    if (rejected) steps.push("resubmit and get an acceptance back");
    if (held) steps.push("lift the hold");
    if (freezeDays > 0) {
      steps.push(`reprint decision — ${freezeDays}-day print freeze`);
    }
    if (requiresReview) steps.push("reviewer approval");
    if (steps.length === 0) steps.push("republish at the corrected version");

    return {
      id,
      name: channel?.name ?? id,
      listings,
      assets,
      violations: onChannel,
      hard,
      soft,
      ruleFields,
      freezeDays,
      chipState: rejected
        ? "rejected"
        : hard > 0
        ? "blocked"
        : held
        ? "withheld"
        : undefined,
      state,
      steps,
    };
  });
}

function ChannelImpact({ rows, index }: { rows: ChannelRow[]; index: Index }) {
  const [open, setOpen] = useState<string | null>(null);
  if (rows.length === 0) {
    return (
      <EmptyState compact title="No channel is affected">
        The corrected field feeds no listing that is currently prepared.
      </EmptyState>
    );
  }
  return (
    <Table scroll className="[--table-min-w:820px]">
      <thead>
        <tr>
          <Th>Channel</Th>
          <Th num>Listings</Th>
          <Th>What breaks</Th>
          <Th>State</Th>
          <Th>Before it can republish</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const expanded = open === row.id;
          return [
            <Tr
              key={row.id}
              selected={expanded}
              onClick={
                row.violations.length
                  ? () => setOpen(expanded ? null : row.id)
                  : undefined
              }
            >
              <Td>
                <ChannelChip
                  channelId={row.id}
                  name={row.name}
                  state={row.chipState}
                />
              </Td>
              <Td num>
                <Tooltip
                  content={row.listings.join("\n") || "none in scope"}
                  mono
                >
                  <span className="inline-flex flex-col items-end">
                    <span>{fmt.count(row.listings.length)}</span>
                    {row.assets > 0 && (
                      <span className="text-2xs text-faint">
                        {plural(row.assets, "asset")}
                      </span>
                    )}
                  </span>
                </Tooltip>
              </Td>
              <Td>
                {row.violations.length === 0 ? (
                  <span className="text-sm text-faint">no rule breached</span>
                ) : (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {row.hard > 0 && (
                      <Badge tone="danger" dot>
                        {plural(row.hard, "rule")} blocking
                      </Badge>
                    )}
                    {row.soft > 0 && (
                      <Badge tone="warn">{plural(row.soft, "advisory")}</Badge>
                    )}
                    {row.ruleFields.slice(0, 3).map((field) => (
                      <Code key={field}>{field}</Code>
                    ))}
                    <span className="text-2xs uppercase tracking-caps text-faint">
                      {expanded ? "hide" : "show"}
                    </span>
                  </div>
                )}
              </Td>
              <Td>
                <Tooltip content={row.state.why}>
                  <span>
                    <Badge tone={row.state.tone} dot>{row.state.label}</Badge>
                  </span>
                </Tooltip>
              </Td>
              <Td>
                <ul className="flex flex-col gap-0.5 text-sm text-muted">
                  {row.steps.map((step) => (
                    <li key={step} className="flex gap-1.5">
                      <span aria-hidden="true" className="text-faint">→</span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ul>
              </Td>
            </Tr>,
            expanded ? (
              <tr key={`${row.id}-detail`}>
                <Td colSpan={5} className="bg-sunken">
                  <div className="flex flex-col gap-2 py-1">
                    <span className="text-2xs uppercase tracking-caps text-faint">
                      the rules that bound on {label(index, row.id)}
                    </span>
                    {row.violations.map((violation, i) => (
                      <ViolationRow
                        key={`${violation.constraint}-${violation.entity_id}-${i}`}
                        violation={violation}
                      />
                    ))}
                  </div>
                </Td>
              </tr>
            ) : null,
          ];
        })}
      </tbody>
    </Table>
  );
}

/* ========================================================================== *
 * 5 - claims and contradictions
 * ========================================================================== */

function ClaimRow({ claim, index, confirmed }: {
  claim: ReadClaim;
  index: Index;
  confirmed: boolean;
}) {
  return (
    <div
      className={cn(
        "flex min-w-0 flex-col gap-1 rounded-sm border p-2",
        confirmed
          ? "border-danger-border bg-danger-soft/40"
          : "border-subtle bg-sunken"
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={confirmed ? "danger" : "neutral"} dot={confirmed}>
          {claim.claim || "unnamed claim"}
        </Badge>
        {claim.entity && <Code>{claim.entity}</Code>}
        {claim.listing && (
          <Tooltip content={label(index, claim.listing)}>
            <span className="font-mono text-2xs text-faint">{claim.listing}</span>
          </Tooltip>
        )}
      </div>
      {claim.detail && (
        <p className="text-sm leading-relaxed text-muted">{claim.detail}</p>
      )}
      {claim.excerpt && (
        <p className="text-sm italic leading-relaxed text-faint">
          “{claim.excerpt}”
        </p>
      )}
    </div>
  );
}

/* ========================================================================== *
 * The view
 * ========================================================================== */

interface Root {
  id: string;
  entity: string;
  path: string;
  label: string;
}

/** What the blast radius is walked from.
 *
 * The qualified attribute reference wherever the resolution settled on a
 * variant: walking "VAR-01B:specs.power_w" answers "what does this corrected
 * field reach", where walking the bare product id would seed every attribute
 * of every variant and drown the finding in the catalog.
 */
function rootsFor(
  corrections: CorrectionSignal[],
  chosen: ChangeScope | undefined,
  index: Index,
): Root[] {
  const paths = [...new Set(corrections.flatMap((s) => s.attribute_paths ?? []))];
  const named = [...new Set(corrections.flatMap((s) => s.entities ?? []))];
  const entities = (chosen?.entities?.length ? chosen.entities : named).filter(
    Boolean
  );

  const out: Root[] = [];
  const seen = new Set<string>();
  const add = (entity: string, path: string) => {
    const id = path && index.variants.has(entity) ? `${entity}:${path}` : entity;
    if (seen.has(id)) return;
    seen.add(id);
    const field = index.attributes.get(path)?.label ?? path;
    out.push({
      id,
      entity,
      path,
      label: field ? `${field} on ${label(index, entity)}` : label(index, entity),
    });
  };

  for (const entity of entities) {
    if (paths.length === 0) add(entity, "");
    for (const path of paths) {
      // Only pair a field with an entity that can carry it - a food path on an
      // appliance variant is not a reading anyone offered.
      const def = index.attributes.get(path);
      const product = index.products.get(
        index.variants.get(entity)?.product_id ?? ""
      );
      const applies =
        !def || !product ||
        def.applies_to.length === 0 ||
        def.applies_to.some((prefix) => product.category.startsWith(prefix));
      if (applies) add(entity, path);
    }
  }
  return out.slice(0, 12);
}

/** Which case this run is about.
 *
 * A run is scoped to one product - that is the unit the publish lock is taken
 * on and the unit a reviewer commits - so every answer below is an answer about
 * that product. Naming it first is what stops the page reading as a verdict on
 * the catalog. What is still open elsewhere is named too, because a decision
 * here is deliberately not a decision about any of it.
 */
function CaseHeading({ summary, caseId, others, fallback, index }: {
  summary?: CaseSummary;
  caseId?: string;
  others?: CaseSummary[];
  /** The product read off the correction, for a run checkpointed before the
   *  case was recorded on it. */
  fallback?: Product;
  index: Index;
}) {
  const id = summary?.case_id || caseId || fallback?.id || "";
  if (!id) return null;

  const unscoped = id === UNSCOPED_CASE;
  const name = unscoped
    ? "corrections not attributed to a product"
    : label(index, summary?.product || fallback?.id || id);
  const fields = summary?.attribute_paths ?? [];
  const documents = summary?.documents ?? [];
  const open = others ?? [];

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-x-2.5 gap-y-1.5 rounded-md border",
        "bg-raised px-3 py-2 shadow-e1",
        unscoped ? "border-danger-border" : "border-subtle"
      )}
    >
      <span className="text-2xs uppercase tracking-caps text-faint">
        this run is about
      </span>
      <span
        className={cn(
          "text-sm font-semibold",
          unscoped ? "text-danger-text" : "text-fg"
        )}
      >
        {name}
      </span>
      {!unscoped && <Code>{id}</Code>}

      {fields.length > 0 && (
        <Tooltip content={fields.join("\n")} mono>
          <span className="text-xs text-muted">
            {plural(fields.length, "field")} corrected
          </span>
        </Tooltip>
      )}
      {documents.map((doc) => (
        <span key={doc} className="inline-flex items-center gap-1 text-xs text-muted">
          <IconDoc size={11} className="text-faint" />
          <Code>{doc}</Code>
        </span>
      ))}

      {open.length > 0 && (
        <Tooltip content={open.map((o) => o.title).join("\n")}>
          <span className="ml-auto text-xs text-faint">
            {plural(open.length, "other case")} open — not decided here
          </span>
        </Tooltip>
      )}
    </div>
  );
}

export function Investigation({ run, catalog, onOpenCitation }: {
  run: RunSnapshot | null;
  /** The catalog, where the shell already holds it. Fetched here when it does
   *  not: every panel names variants, channels and listings, and a page of
   *  bare identifiers is unreadable. */
  catalog?: CatalogState | null;
  onOpenCitation?: (citation: Citation) => void;
}) {
  const v = run?.values;

  /* --- the catalog, for names ------------------------------------------- */
  const [fetched, setFetched] = useState<CatalogState | null>(null);
  useEffect(() => {
    if (catalog) return;
    let live = true;
    api.network()
      .then((state) => { if (live) setFetched(state); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [catalog]);
  const index = useMemo(() => buildIndex(catalog ?? fetched), [catalog, fetched]);

  /* --- what the run says ------------------------------------------------- */
  const signals = useMemo(() => v?.signals ?? [], [v]);
  const corrections = useMemo(() => signals.filter(movesAValue), [signals]);
  const notices = useMemo(() => signals.filter((s) => !movesAValue(s)), [signals]);
  const chosenScope = v?.chosen_scope;
  const candidates = useMemo(() => v?.scope_candidates ?? [], [v]);
  const chain = useMemo(() => v?.causal_chain ?? [], [v]);
  const violations = useMemo(() => (v ? boundViolations(v) : []), [v]);
  const actions = useMemo(
    () => v?.recommendation?.delta?.actions ?? v?.ranked?.[0]?.delta?.actions ?? [],
    [v]
  );
  const claims = useMemo(
    () => (v?.claim_flags ?? []).map(readClaim),
    [v]
  );
  const roots = useMemo(
    () => rootsFor(corrections, chosenScope, index),
    [corrections, chosenScope, index]
  );

  /* --- the walk ---------------------------------------------------------- */
  const [rootId, setRootId] = useState<string>("");
  const active = roots.find((r) => r.id === rootId) ?? roots[0];
  const [blast, setBlast] = useState<
    { root: string; scope: AffectedScope; totals: Totals } | null
  >(null);
  const [walking, setWalking] = useState(false);

  useEffect(() => {
    const entity = active?.id;
    if (!entity) { setBlast(null); return; }
    let live = true;
    setWalking(true);
    api.trace(entity)
      .then((answer) => {
        if (!live) return;
        setBlast({
          root: answer.root ?? entity,
          scope: asScope(answer.affected as Partial<AffectedScope>),
          totals: answer.totals ?? {},
        });
      })
      .catch(() => { if (live) setBlast(null); })
      .finally(() => { if (live) setWalking(false); });
    return () => { live = false; };
  }, [active?.id]);

  /* --- the variant table ------------------------------------------------- */
  const productId = useMemo(() => {
    const fromScope = (chosenScope?.entities ?? [])
      .map((id) => index.variants.get(id)?.product_id)
      .find(Boolean);
    if (fromScope) return fromScope;
    for (const signal of corrections) {
      for (const id of signal.entities ?? []) {
        if (index.products.has(id)) return id;
        const product = index.variants.get(id)?.product_id;
        if (product) return product;
      }
    }
    return "";
  }, [chosenScope, corrections, index]);

  const [variantAnswer, setVariantAnswer] = useState<
    Awaited<ReturnType<typeof api.variants>> | null
  >(null);
  useEffect(() => {
    if (!productId) { setVariantAnswer(null); return; }
    let live = true;
    api.variants(productId)
      .then((answer) => { if (live) setVariantAnswer(answer); })
      .catch(() => { if (live) setVariantAnswer(null); });
    return () => { live = false; };
  }, [productId]);
  const variantTable = useMemo(
    () => readVariantTable(variantAnswer, index),
    [variantAnswer, index]
  );

  /* --- derived views ----------------------------------------------------- */
  const runWide = useMemo(() => runScope(v?.affected), [v]);
  const runTotals = (v?.affected as { totals?: Totals } | undefined)?.totals;
  const scope = blast?.scope ?? runWide;
  const tree = useMemo(
    () => propagate(chainFrom(chain, active?.id ?? ""), index),
    [chain, active?.id, index]
  );
  const rows = useMemo(
    () =>
      channelRows(
        scope, violations, actions, index,
        Boolean(v?.recommendation?.requires_review), tree.assets
      ),
    [scope, violations, actions, index, v, tree]
  );

  const confirmedClaims = claims.filter((c) => c.upheld);
  const advisoryClaims = claims.filter((c) => !c.upheld);
  const product = index.products.get(productId);
  const safetyFlags = total(blast?.totals ?? runTotals, "safety_flags");

  if (!run || !v) {
    return (
      <>
        <PageHeader section="investigation" />
        <Panel>
          <EmptyState art={<ArtNoRun />} title="No correction has been worked yet">
            Advance the replay to a supplier document, then start the loop from
            the Ingest Fabric — or press <Code>⌘K</Code> and run it from
            anywhere. The blast radius is produced on the way to a resolution.
          </EmptyState>
        </Panel>
      </>
    );
  }

  return (
    <>
      <PageHeader
        section="investigation"
        actions={
          <div className="flex items-center gap-1.5">
            <RevisionBadge revision={v.revision} />
            <Severity level={v.severity} />
            {product?.regulated && <RegulatedTag />}
            <SafetyFlag count={safetyFlags} />
            {v.material !== undefined && (
              <Badge tone={v.material ? "danger" : "neutral"}>
                {v.material ? "material" : "immaterial"}
              </Badge>
            )}
          </div>
        }
      />

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto">
        {/* --- 0 - the case ------------------------------------------------ */}
        <CaseHeading
          summary={v.case}
          caseId={v.case_id}
          others={v.other_open_cases}
          fallback={product}
          index={index}
        />

        {/* --- 1 - the correction ------------------------------------------ */}
        <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,2.2fr)_minmax(300px,1fr)]">
          <Panel
            title="The correction"
            icon={<IconDoc size={14} />}
            subtitle={
              corrections.length
                ? `${plural(corrections.length, "field")} corrected`
                : undefined
            }
          >
            {corrections.length === 0 ? (
              <EmptyState compact title="No value has moved">
                Nothing in the traffic read so far changes a value on file.
              </EmptyState>
            ) : (
              <div className="flex flex-col gap-2.5">
                {corrections.map((signal) => (
                  <CorrectionCard
                    key={signal.id}
                    signal={signal}
                    index={index}
                    isRoot={(v.root_causes ?? []).includes(signal.id)}
                  />
                ))}
              </div>
            )}
          </Panel>

          <div className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
            <Panel title="Assessment">
              <div className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Severity level={v.severity} />
                  {v.material !== undefined && (
                    <Badge tone={v.material ? "danger" : "neutral"}>
                      {v.material ? "material" : "immaterial"}
                    </Badge>
                  )}
                  {v.status && <Badge tone="neutral" mono>{v.status}</Badge>}
                </div>
                {v.triage_reason && (
                  <p className="text-sm leading-relaxed">{v.triage_reason}</p>
                )}
              </div>
            </Panel>

            {notices.length > 0 && (
              <Panel title={`Other notices (${notices.length})`}>
                <div className="flex flex-col gap-2">
                  {notices.map((signal) => (
                    <div key={signal.id} className="flex items-start gap-2">
                      <Badge
                        tone={CORRECTION_TONE[signal.kind] ?? "neutral"}
                      >
                        {CORRECTION_WORDS[signal.kind] ?? signal.kind}
                      </Badge>
                      <div className="min-w-0">
                        <div className="text-sm">{signal.summary}</div>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5">
                          <ProvBadge provenance={signal.provenance} />
                          {(signal.entities ?? []).slice(0, 4).map((id) => (
                            <Code key={id}>{id}</Code>
                          ))}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </Panel>
            )}
          </div>
        </div>

        {/* Who has to be told, in the words they use. The blast radius below
            is complete and expressed in identifiers only this system reads; a
            buyer asked which products are affected cannot answer from VAR-01B.
            Same truth, second vocabulary. */}
        <PublicationImpact
          entityId={(chosenScope?.entities ?? [])[0] ?? productId ?? null}
        />

        {/* --- 2 - scope resolution ---------------------------------------- */}
        <Panel
          title="Which product, and which variant"
          icon={<IconScenarios size={14} />}
          subtitle={
            candidates.length
              ? `${plural(candidates.length, "reading")} considered`
              : undefined
          }
        >
          <div className="flex flex-col gap-3">
            <p className="max-w-3xl text-sm leading-relaxed text-muted">
              A correction that names a product but not a variant is the thing
              that goes wrong in this catalog. The readings below are the
              answers the record supports; the deterministic validator picked
              between them, and the attribute table underneath is the evidence
              it used.
            </p>

            {chosenScope && (
              <div className="flex flex-wrap items-center gap-2 rounded-sm border border-ok-border bg-ok-soft/40 px-3 py-2">
                <span className="text-sm text-muted">Applied to</span>
                <span className="text-sm font-medium text-fg">
                  {(chosenScope.entities ?? []).map((id) => label(index, id))
                    .join(", ") || "nothing"}
                </span>
                {(chosenScope.entities ?? []).map((id) => (
                  <Code key={id}>{id}</Code>
                ))}
                <span className="text-sm text-muted">
                  — {SCOPE_WORDS[chosenScope.level] ?? chosenScope.level}
                </span>
              </div>
            )}

            {candidates.length === 0 ? (
              <EmptyState compact title="No competing readings">
                The correction named its subject outright, so there was nothing
                to resolve.
              </EmptyState>
            ) : (
              <Section label="The readings considered">
                <div className="grid gap-2 lg:grid-cols-2 xl:grid-cols-3">
                  {candidates.map((candidate, i) => (
                    <ScopeCandidate
                      key={`${candidate.level}-${i}`}
                      scope={candidate}
                      index={index}
                      chosen={
                        !!chosenScope &&
                        candidate.level === chosenScope.level &&
                        (candidate.entities ?? []).join() ===
                          (chosenScope.entities ?? []).join()
                      }
                    />
                  ))}
                </div>
              </Section>
            )}

            <Section
              label="The attribute table the decision was read from"
              actions={
                productId ? (
                  <span className="flex items-center gap-1.5 text-xs text-faint">
                    {label(index, productId)}
                    <Code>{productId}</Code>
                  </span>
                ) : undefined
              }
            >
              {!productId ? (
                <p className="text-sm text-muted">
                  No product in scope, so there is no table to read against.
                </p>
              ) : !variantTable ? (
                <div className="flex flex-col gap-2">
                  {Array.from({ length: 3 }, (_, i) => (
                    <Skeleton key={i} className="h-8 w-full" />
                  ))}
                </div>
              ) : (
                <VariantMatrix
                  table={variantTable}
                  highlight={active?.path ?? ""}
                  index={index}
                />
              )}
            </Section>
          </div>
        </Panel>

        {/* --- 3 - the blast radius ---------------------------------------- */}
        <Panel
          title="Blast radius"
          icon={<IconTrace size={14} />}
          subtitle={blast ? blast.root : undefined}
          actions={
            roots.length > 1 ? (
              <Select
                ariaLabel="Corrected field to trace"
                value={active?.id}
                onValueChange={setRootId}
                options={roots.map((r) => ({
                  value: r.id, label: r.label, hint: r.id,
                }))}
                className="min-w-[220px]"
              />
            ) : undefined
          }
        >
          <div className="flex flex-col gap-3">
            {/* The sentence and the figures move together. Showing a fresh
                label over the previous walk's totals is the one wrong thing
                this panel could do, so both wait for the same answer. */}
            {walking ? (
              <>
                <Skeleton className="h-5 w-2/3" />
                <div className="grid grid-cols-[repeat(auto-fit,minmax(124px,1fr))] gap-2">
                  {Array.from({ length: 6 }, (_, i) => (
                    <Skeleton key={i} className="h-[58px] w-full" />
                  ))}
                </div>
              </>
            ) : (
              <>
                <p className="text-base leading-relaxed text-fg">
                  {blastSentence(
                    active ? active.label : "This correction",
                    blast?.totals ?? runTotals
                  )}
                </p>

                <div className="grid grid-cols-[repeat(auto-fit,minmax(124px,1fr))] gap-2">
                  <Kpi
                    label="Fields corrected"
                    value={total(blast?.totals ?? runTotals, "fields")}
                    sub="values the notice moves"
                  />
                  <Kpi
                    label="Assets to rebuild"
                    value={total(blast?.totals ?? runTotals, "assets")}
                    sub="copy built on the old value"
                  />
                  <Kpi
                    label="Listings touched"
                    value={total(blast?.totals ?? runTotals, "listings")}
                    sub="variant × channel"
                  />
                  <Kpi
                    label="Channels reached"
                    value={total(blast?.totals ?? runTotals, "channels")}
                    sub="places it is published"
                  />
                  <Kpi
                    label="Safety flags"
                    value={safetyFlags}
                    tone={safetyFlags > 0 ? "bad" : undefined}
                    sub="allergen or safety values"
                  />
                  <Kpi
                    label="Regulated"
                    value={total(blast?.totals ?? runTotals, "regulated")}
                    sub="products needing review"
                  />
                </div>
              </>
            )}

            {runTotals && blast && roots.length > 1 && (
              <p className="text-sm text-muted">
                Across every field in this correction:{" "}
                {plural(total(runTotals, "fields"), "field")},{" "}
                {plural(total(runTotals, "assets"), "asset")},{" "}
                {plural(total(runTotals, "listings"), "listing")},{" "}
                {plural(total(runTotals, "channels"), "channel")}.
              </p>
            )}

            <CrossVariantNotice hits={tree.cross} index={index} />

            <Section
              label={active ? `How ${active.label} propagates` : "How it propagates"}
            >
              <PropagationTree tree={tree} index={index} />
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1">
                {Object.entries(RELATION_WORDS).map(([relation, words]) => (
                  <Tooltip key={relation} content={words}>
                    <span className="text-2xs uppercase tracking-caps text-faint">
                      {relation}
                    </span>
                  </Tooltip>
                ))}
              </div>
            </Section>
          </div>
        </Panel>

        {/* --- 4 - per-channel impact -------------------------------------- */}
        <Panel
          title="What it does to each channel"
          flush
          subtitle={
            rows.length
              ? `${plural(rows.filter((r) => r.state.label !== "ready").length,
                  "channel")} not publishable as it stands`
              : undefined
          }
        >
          <div className="p-[var(--panel-pad)] pb-0">
            <p className="max-w-3xl text-sm leading-relaxed text-muted">
              One row per channel the correction reaches. Open a row to read the
              rules that bound — they are catalog rows the validator evaluated,
              not a description of code.
            </p>
          </div>
          <ChannelImpact rows={rows} index={index} />
        </Panel>

        {/* --- 5 - claims and contradictions -------------------------------- */}
        <Panel
          title="Claims and contradictions"
          icon={<IconAlert size={14} />}
          tone={violations.some((x) => x.severity === "HARD") ? "danger" : undefined}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <Section
              label={`Findings — the rule table bound (${
                violations.length + confirmedClaims.length
              })`}
            >
              <p className="text-sm leading-relaxed text-muted">
                Deterministic. Each of these is a rule in the catalog evaluated
                against the corrected values, and a hard one blocks the
                republish on its own.
              </p>
              {violations.length === 0 && confirmedClaims.length === 0 ? (
                <EmptyState compact title="Nothing breached">
                  Every rule the affected channels bind still passes.
                </EmptyState>
              ) : (
                <div className="flex flex-col gap-2">
                  {violations.map((violation, i) => (
                    <ViolationRow
                      key={`${violation.constraint}-${violation.entity_id}-${i}`}
                      violation={violation}
                    />
                  ))}
                  {confirmedClaims.map((claim, i) => (
                    <ClaimRow
                      key={`${claim.claim}-${claim.entity}-${i}`}
                      claim={claim}
                      index={index}
                      confirmed
                    />
                  ))}
                </div>
              )}
            </Section>

            <Section label={`Suggestions — the model’s reading (${advisoryClaims.length})`}>
              <p className="text-sm leading-relaxed text-muted">
                Advisory. A model read the prepared copy and believes the
                corrected value makes these claims untrue. The rule table did
                not confirm them, so nothing is blocked by them — they are here
                for a reviewer to read, not to act on automatically.
              </p>
              {advisoryClaims.length === 0 ? (
                <EmptyState compact title="Nothing suggested">
                  The scan found no wording the rule table had not already
                  caught.
                </EmptyState>
              ) : (
                <div className="flex flex-col gap-2">
                  {advisoryClaims.map((claim, i) => (
                    <ClaimRow
                      key={`${claim.claim}-${claim.entity}-${i}`}
                      claim={claim}
                      index={index}
                      confirmed={false}
                    />
                  ))}
                </div>
              )}
            </Section>
          </div>
        </Panel>

        {/* --- 6 - evidence, guidance, refusals ----------------------------- */}
        <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(330px,1fr)]">
          <div className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
            <EvidenceLog records={v.evidence_log ?? []} />

            {chain.length > 0 && (
              <Panel
                title="The chain, hop by hop"
                icon={<IconTrace size={14} />}
                subtitle={`${plural(chain.length, "edge")} — every field in this correction`}
              >
                <ol className="sc-stagger flex flex-col">
                  {chain.map((link, i) => (
                    <ChainStep key={i} link={link} step={i} last={i === chain.length - 1} />
                  ))}
                </ol>
              </Panel>
            )}

            {(v.rejected_actions ?? []).length > 0 && (
              <Panel
                title={`Proposals rejected as unpublishable (${
                  (v.rejected_actions ?? []).length
                })`}
              >
                <p className="mb-2.5 text-sm leading-relaxed text-muted">
                  A model proposed these; the channel rules do not permit them.
                  They are shown rather than hidden — a reviewer should see what
                  was considered and why it was ruled out.
                </p>
                <div className="flex flex-col gap-2">
                  {(v.rejected_actions ?? []).map((rejected, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm">
                      <Tooltip content={describeAction(rejected.action, index.name)}>
                        <span>
                          <Badge tone="neutral">{String(rejected.action.kind)}</Badge>
                        </span>
                      </Tooltip>
                      <span className="text-muted">{rejected.why}</span>
                    </div>
                  ))}
                </div>
              </Panel>
            )}
          </div>

          <div className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
            {(v.prior_incidents ?? []).length > 0 && (
              <Panel title="Has this happened before?">
                <div className="flex flex-col gap-2">
                  {(v.prior_incidents ?? []).map((id) => (
                    <div key={id} className="flex items-center gap-2 text-sm">
                      <Badge tone="warn">RECURRENCE</Badge>
                      <Code>{id}</Code>
                    </div>
                  ))}
                  <p className="text-sm leading-relaxed text-muted">
                    Earlier corrections that matched this one. Their lessons are
                    in the retrieved guidance below.
                  </p>
                </div>
              </Panel>
            )}

            <Panel
              title={`Retrieved guidance (${(v.citations ?? []).length})`}
              flush
            >
              {(v.citations ?? []).length === 0 ? (
                <EmptyState art={<ArtNoEvidence />} title="Nothing retrieved">
                  The scope resolution ran without matching policy or standard.
                </EmptyState>
              ) : (
                <div className="flex max-h-[460px] flex-col gap-2 overflow-y-auto p-3">
                  {(v.citations ?? []).slice(0, 10).map((citation) => (
                    <CitationCard
                      key={citation.chunk_id}
                      c={citation}
                      onOpen={
                        onOpenCitation ? () => onOpenCitation(citation) : undefined
                      }
                    />
                  ))}
                </div>
              )}
            </Panel>
          </div>
        </div>

        {/* --- 7 - the attribute's own history ------------------------------ */}
        <FactLineage
          attr={active?.path}
          title="History of the corrected value"
          icon={<IconClock size={14} />}
          note={
            active?.path ? (
              <>
                Every version of{" "}
                <Code>{active.path}</Code> the store holds, on both time axes.
                The chain is what makes “45 W, then 65 W, then 65 W on the Max
                only” a record rather than three overwrites.
              </>
            ) : undefined
          }
        />
      </div>
    </>
  );
}

function ChainStep({ link, step, last }: {
  link: CausalLink;
  step: number;
  last: boolean;
}) {
  return (
    <li
      style={{ ["--i" as string]: step }}
      className={cn(
        "flex gap-3 py-2.5",
        !last && "border-b border-dashed border-subtle"
      )}
    >
      <span
        className={cn(
          "flex size-6 shrink-0 items-center justify-center rounded-full",
          "border border-accent-border bg-accent-soft font-mono",
          "text-xs font-semibold text-accent-text tabular-nums"
        )}
      >
        {String(step + 1).padStart(2, "0")}
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5 text-sm">
          <Code>{link.from_ref}</Code>
          <Tooltip content={RELATION_WORDS[link.relation] ?? link.relation}>
            <span className="text-2xs uppercase tracking-caps text-faint">
              {link.relation}
            </span>
          </Tooltip>
          <Code>{link.to_ref}</Code>
        </div>
        {link.explanation && (
          <p className="mt-1 text-sm leading-relaxed text-muted">
            {link.explanation}
          </p>
        )}
        {(link.evidence ?? []).length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {link.evidence.map((id) => (
              <Badge key={id} tone="neutral" mono>{id}</Badge>
            ))}
          </div>
        )}
      </div>
    </li>
  );
}
