import { useEffect, useMemo, useRef, useState } from "react";
import { UNSCOPED_CASE, api, fmt } from "../api";
import type {
  AffectedScope, AttributeDef, CatalogState, CorrectionKind, KPIs, OpenCase,
  RunSnapshot, SCEvent,
} from "../api";
import { applyEvents, emptyImpact, impactFrom, prunePulses } from "../liveImpact";
import type { LiveImpact } from "../liveImpact";
import { ArtAllClear, ArtNoRun, ArtQuietFeed } from "../art/illustrations";
import {
  IconAlert, IconCorrection, IconDoc, IconJump, IconSpark, IconTrace,
} from "../icons";
import { PageHeader } from "../app/shell/PageHeader";
import {
  Badge, Button, Code, EmptyState, Panel, Skeleton, Tooltip, cn,
} from "../ui";
import type { BadgeTone } from "../ui";
import {
  ChannelChip, Kpi, ProvBadge, RegulatedTag, SafetyFlag, Severity, SourceCite,
  ValueDiff, listingChannelState,
} from "./common";
import type { ChannelState } from "./common";
import { EstatePanel } from "./EstatePanel";
import { MapLegend, NetworkMap, listingStatusMap } from "./NetworkMap";

/* The ingest fabric.
 *
 * The standing view: what the catalog is, what is moving through it, and what
 * the system currently believes on whose authority. Everything a reviewer needs
 * before deciding whether anything should republish.
 *
 * Four claims are made here and each has one owner:
 *
 *   the map          structure and reach. Click a node and the API walks the
 *                    lineage; the highlight is the answer it gave, not one the
 *                    component worked out.
 *   the feed         what arrived, as a sentence rather than a payload. The
 *                    ids stay on the row because a reviewer searches by them.
 *   corrections      what is in force. The lines come from the overlay itself,
 *                    each already reading "document version supersedes version:
 *                    entity path old -> new".
 *   open cases       what there is to decide, one row per product, in the order
 *                    /api/cases returned - which is the order the loop itself
 *                    picks in. Each row starts a run scoped to that product.
 *
 * No figure below is computed here beyond counting rows the API returned.
 */

/* --- vocabulary ----------------------------------------------------------- */

const CORRECTION_LABEL: Record<CorrectionKind, string> = {
  SPEC_CORRECTION: "spec corrected",
  ALLERGEN_CHANGE: "allergen changed",
  INGREDIENT_CHANGE: "ingredients changed",
  SOURCE_CONFLICT: "sources disagree",
  CHANNEL_REJECTION: "channel rejected the feed",
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

/** What each kind of event on the tape actually is, in a word. The raw enum
 *  stays in the row's tooltip - it is what the engine logs and filters on. */
const EVENT_LABEL: Record<string, string> = {
  SUPPLIER_FEED: "feed",
  SPEC_DOC: "document",
  CHANNEL_STATUS: "channel",
  CATALOG_UPDATE: "catalog",
  PUBLISH_TELEMETRY: "published",
  COMMS: "email",
};

/** Tied to the client rather than restated, so a change to the trace endpoint
 *  shows up here as a type error instead of as a quietly empty highlight. */
type TraceResult = Awaited<ReturnType<typeof api.trace>>;

/** Names an event and a value in one place, so a sentence anywhere in this
 *  file reads the same way. */
interface Vocab {
  /** The display name for an id, falling back to the id itself. */
  name: (id: unknown) => string;
  /** An attribute path as a label that reads mid-sentence. */
  attr: (path: unknown) => string;
  def: (path: string) => AttributeDef | undefined;
}

export function ControlTower({
  catalog, events, run, onStartRun, onReplay, busy,
}: {
  catalog: CatalogState | null;
  events: SCEvent[];
  run: RunSnapshot | null;
  /** Work one case. Without an id the loop takes the worst one open. */
  onStartRun: (caseId?: string) => void;
  /** Drive the tape. The feed uses it to land the clock on a named event. */
  onReplay: (body: { action: string; steps?: number; speed?: number;
                     to_seq?: number }) => void;
  busy: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [live, setLive] = useState<LiveImpact>(emptyImpact);
  const seenRef = useRef<string>("");

  // Fold newly-arrived events into the decaying highlight state. The feed is
  // prepend-ordered, so the newest event id is enough to tell whether anything
  // actually arrived - re-applying the whole list on every render would keep
  // every node permanently lit.
  useEffect(() => {
    if (!catalog || events.length === 0) return;
    const newest = events[0].id;
    if (newest === seenRef.current) return;
    const previousTop = seenRef.current;
    seenRef.current = newest;
    const fresh = previousTop
      ? events.slice(0, Math.max(1, events.findIndex((e) => e.id === previousTop)))
      : events.slice(0, 1);
    setLive((prev) => applyEvents(prev, fresh, catalog));
  }, [events, catalog]);

  // Fade the pulses out. Only ticks while something is lit, so an idle tab is
  // not re-rendering four times a second forever.
  useEffect(() => {
    if (live.pulses.size === 0) return;
    const timer = setInterval(() => setLive((prev) => prunePulses(prev)), 250);
    return () => clearInterval(timer);
  }, [live.pulses.size]);

  /* --- lookups ---------------------------------------------------------- */

  const vocab = useMemo<Vocab>(() => {
    const names = new Map<string, string>();
    for (const n of catalog?.nodes ?? []) names.set(n.id, n.name);
    for (const p of catalog?.products ?? []) names.set(p.id, p.name);
    for (const v of catalog?.variants ?? []) names.set(v.id, v.name);
    for (const c of catalog?.channels ?? []) names.set(c.id, c.name);
    const defs = new Map<string, AttributeDef>();
    for (const a of catalog?.attributes ?? []) defs.set(a.path, a);
    return {
      name: (id) => (typeof id === "string" && id ? names.get(id) ?? id : ""),
      attr: (path) => {
        if (typeof path !== "string" || !path) return "";
        const label = defs.get(path)?.label;
        // "Rated power" reads badly after a verb; "GTIN" must not become
        // "gTIN", so only a sentence-cased label is lowered.
        return label
          ? /^[A-Z][a-z]/.test(label)
            ? label[0].toLowerCase() + label.slice(1)
            : label
          : path;
      },
      def: (path) => defs.get(path),
    };
  }, [catalog]);

  /* --- what there is to decide ------------------------------------------- */

  // The tape moves the clock and a run writes facts; both change what is open,
  // and nothing else does - so this is not polled.
  const [cases, setCases] = useState<OpenCase[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    api.cases()
      .then((answer) => { if (!cancelled) setCases(answer.cases); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [catalog?.as_of, run?.status]);

  /* --- the blast radius on the map -------------------------------------- */

  const runAffected = run?.values.affected;
  const signalEntities = useMemo(
    () => (run?.values.signals ?? []).flatMap((s) => s.entities),
    [run]
  );

  // The walk depends on the node, not on the poll. The catalog is refetched
  // every time the tape releases an event, so tracing inside that effect would
  // put a request on the wire per event for as long as anything is selected.
  const [trace, setTrace] = useState<TraceResult | null>(null);

  useEffect(() => {
    if (!selected) {
      setTrace(null);
      return;
    }
    let cancelled = false;
    api.trace(selected)
      .then((t) => { if (!cancelled) setTrace(t); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [selected]);

  // Two sources, one meaning. With nothing selected the highlight is whatever
  // the run and the corrections in force put at risk; click a node and it is
  // the lineage walk the API did from there. Both are the API's answer, never
  // a reachability guess made here.
  const traced = useMemo(() => {
    const empty = { nodes: new Set<string>(), listings: new Set<string>() };
    if (!catalog) return empty;
    if (selected) {
      // Until the walk comes back, light the node the reviewer clicked - the
      // click has to acknowledge itself even on a slow answer.
      if (trace?.root !== selected) return { ...empty, nodes: new Set([selected]) };
      const scope: Partial<AffectedScope> = trace.affected ?? {};
      const { impacted } = impactFrom(catalog, scope, [selected]);
      return { nodes: impacted, listings: new Set(scope.listings ?? []) };
    }
    const { impacted } = impactFrom(catalog, runAffected, signalEntities);
    return { nodes: impacted, listings: new Set(runAffected?.listings ?? []) };
  }, [catalog, selected, trace, runAffected, signalEntities]);

  const traceTotals = selected && trace?.root === selected ? trace.totals : null;

  /* --- what the catalog says about itself -------------------------------- */

  // Counting rows the API returned, and nothing more: which listings the
  // overlay reports as stopped, and which channels they are on.
  const board = useMemo(() => {
    const held: string[] = [];
    const rejected: string[] = [];
    const blockedChannels = new Set<string>();
    if (catalog) {
      const statuses = listingStatusMap(catalog);
      for (const listing of catalog.listings) {
        const status = statuses.get(listing.id);
        if (status === "WITHHELD") held.push(listing.id);
        else if (status === "REJECTED") rejected.push(listing.id);
        else continue;
        blockedChannels.add(listing.channel_id);
      }
    }
    return { held, rejected, blockedChannels };
  }, [catalog]);

  // Where a case has to land: the channels carrying a listing for the product,
  // each in the state the overlay reports. A join over rows the API returned -
  // variant to product, listing to channel - and no reachability guess.
  const channelsOfProduct = useMemo(() => {
    const out = new Map<string, ChannelReach[]>();
    if (!catalog) return out;
    const statuses = listingStatusMap(catalog);
    const productOf = new Map(
      catalog.variants.map((v) => [v.id, v.product_id] as const)
    );
    const byProduct = new Map<string, Map<string, ChannelState | undefined>>();
    for (const listing of catalog.listings) {
      const product = productOf.get(listing.variant_id);
      if (!product) continue;
      const row =
        byProduct.get(product) ?? new Map<string, ChannelState | undefined>();
      byProduct.set(product, row);
      const state = listingChannelState(statuses.get(listing.id));
      row.set(listing.channel_id, worseOf(row.get(listing.channel_id), state));
    }
    for (const [product, row] of byProduct) {
      // Channel order is the catalog's own, so every view names them in the
      // same sequence.
      out.set(
        product,
        catalog.channels
          .filter((c) => row.has(c.id))
          .map((c) => ({ id: c.id, name: c.name, state: row.get(c.id) }))
      );
    }
    return out;
  }, [catalog]);

  // Order is the API's - safety, then regulated, then oldest. The unattributed
  // case is lifted out of the list because it is not a queue item: nobody owns
  // a correction that names no product.
  const unscoped = cases?.find((c) => c.case_id === UNSCOPED_CASE);
  const scoped = (cases ?? []).filter((c) => c.case_id !== UNSCOPED_CASE);
  const worstOpen = cases?.[0];

  const correction = catalog?.correction;
  const summary = correction?.summary ?? [];
  const supersededDocs = correction?.docs ?? [];
  const correctedFields = Object.keys(correction?.attributes ?? {}).length;

  // The validator's figures where a run has produced them; the catalog's own
  // state before it has. Neither is guessed.
  const kpis: Partial<KPIs> | undefined =
    run?.values.final_validation?.kpis ?? run?.values.recommendation?.kpis;
  const runTotals = runAffected?.totals as Record<string, number> | undefined;

  const fieldsAffected =
    kpis?.fields_affected ?? Number(runTotals?.fields ?? correctedFields);
  const channelsBlocked = kpis?.channels_blocked ?? board.blockedChannels.size;
  const safetyFlags = kpis?.safety_flags ?? Number(runTotals?.safety_flags ?? 0);
  const awaitingReview = board.held.length;

  const signals = run?.values.signals ?? [];
  const quiet = summary.length === 0 && signals.length === 0;

  return (
    <>
      <PageHeader
        section="tower"
        actions={
          <div className="flex items-center gap-2">
            {worstOpen && (
              <span className="hidden text-right text-xs leading-tight text-faint lg:block">
                worst open case
                <br />
                <span className="text-muted">{worstOpen.title}</span>
              </span>
            )}
            <Tooltip
              content={
                worstOpen
                  ? `Works one case: ${worstOpen.title}. Pick any other row in Open corrections to work that product instead.`
                  : "Nothing is open. The loop would find no case to work."
              }
            >
              <span>
                <Button
                  tone="primary"
                  size="md"
                  onClick={() => onStartRun()}
                  loading={busy}
                  icon={<IconSpark size={15} />}
                >
                  {busy
                    ? "Working…"
                    : worstOpen
                    ? "Run the worst open case"
                    : "Run the correction loop"}
                </Button>
              </span>
            </Tooltip>
          </div>
        }
      />

      <div className="grid gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(340px,1fr)]">
        <div className="flex min-w-0 flex-col gap-3">
          <Panel
            title="Product catalog"
            flush
            actions={
              <div className="flex items-center gap-2 text-sm">
                {catalog && (
                  <span className="font-mono text-xs text-faint">
                    as of {fmt.stamp(catalog.as_of)}
                  </span>
                )}
                {selected && (
                  <Button size="xs" onClick={() => setSelected(null)}>
                    clear trace
                  </Button>
                )}
              </div>
            }
          >
            {catalog ? (
              <>
                <div className="overflow-x-auto">
                  <div className="min-w-[720px]">
                    <NetworkMap
                      catalog={catalog}
                      affected={traced}
                      live={live}
                      selected={selected}
                      onSelect={setSelected}
                    />
                  </div>
                </div>
                <div className="border-t border-subtle px-3 py-2.5">
                  <MapLegend live={live.pulses.size > 0} />
                  <div className="mt-2 flex items-start gap-2 text-sm text-muted">
                    <IconTrace size={14} className="mt-0.5 shrink-0 text-accent-text" />
                    {selected ? (
                      <span>
                        Everything built on <Code>{selected}</Code> is
                        highlighted — the fields that carry its value, the copy
                        derived from them and the channels those listings feed.
                        {traceTotals && (
                          <span className="ml-1 font-mono text-xs text-faint">
                            {traceLine(traceTotals)}
                          </span>
                        )}
                      </span>
                    ) : (
                      <span>
                        Click any product, variant or channel to trace what a
                        correction there would reach.
                      </span>
                    )}
                  </div>
                </div>
              </>
            ) : (
              <div className="p-3">
                <Skeleton className="h-[320px] w-full" rounded="md" />
              </div>
            )}
          </Panel>

          {/* Who is feeding the catalog, above what they fed it. The map shows
              the shape of the estate; this shows it moving. */}
          <EstatePanel />

          <Panel
            title="Live event feed"
            flush
            subtitle={events.length ? `${events.length} released` : undefined}
          >
            {events.length === 0 ? (
              <EmptyState art={<ArtQuietFeed />} title="Nothing has arrived yet">
                Start or step the replay from the transport in the status bar
                below — the tape releases one supplier document at a time, which
                is how the correction gets narrated.
              </EmptyState>
            ) : (
              <div className="max-h-[280px] overflow-y-auto">
                {events.map((e, i) => {
                  const sentence = describe(e, vocab);
                  const subject = subjectId(e);
                  return (
                    <div
                      key={e.id}
                      // Only the newest few animate in. Animating all 200 on
                      // every arrival would restart the whole list.
                      className={cn(
                        "flex items-baseline gap-2 border-b border-subtle px-3 py-1.5",
                        "transition-colors hover:bg-hover",
                        i < 3 && "animate-slide-in"
                      )}
                    >
                      <span className="shrink-0 font-mono text-xs text-faint tabular-nums">
                        {fmt.stamp(e.ts)}
                      </span>
                      <Badge tone={eventTone(e)}>
                        {EVENT_LABEL[e.type] ?? e.type}
                      </Badge>
                      <Tooltip
                        content={
                          <span className="block">
                            <span className="block">{sentence}</span>
                            <span className="mt-1 block font-mono text-2xs text-faint">
                              {idLine(e)}
                            </span>
                          </span>
                        }
                      >
                        <span className="min-w-0 flex-1 truncate text-sm">
                          {sentence}
                        </span>
                      </Tooltip>
                      {subject && (
                        <span className="shrink-0 font-mono text-2xs text-faint">
                          {subject}
                        </span>
                      )}
                      {/* The tape's only precise control. JUMP with a target
                          seq rewinds the cursor, so the clock, the catalog and
                          this feed all return to the instant that document
                          landed - the same beat, twice, identically. */}
                      <Tooltip
                        content={`Land the tape on this event (seq ${e.seq}). The clock returns to this instant and everything after it goes back to unreleased.`}
                      >
                        <Button
                          tone="ghost"
                          size="xs"
                          iconOnly
                          disabled={busy}
                          aria-label={`Land the tape on ${e.id}`}
                          onClick={() => onReplay({ action: "JUMP", to_seq: e.seq })}
                          icon={<IconJump size={12} />}
                          className="shrink-0 self-center text-faint hover:text-accent-text"
                        />
                      </Tooltip>
                    </div>
                  );
                })}
              </div>
            )}
            {events.length > 0 && (
              <p className="border-t border-subtle px-3 py-2 text-xs leading-relaxed text-faint">
                The control at the end of a row lands the tape on that document
                rather than on the generic inject — the clock returns to that
                instant, and everything after it goes back to unreleased. It is
                how the same beat gets narrated twice off exactly the same
                evidence.
              </p>
            )}
          </Panel>
        </div>

        <div className="flex min-w-0 flex-col gap-3">
          {/* The four figures a reviewer opens this page for. */}
          <div className="grid grid-cols-2 gap-2">
            <Kpi
              label="Fields affected"
              value={fieldsAffected}
              sub="values a correction has moved"
            />
            <Kpi
              label="Channels blocked"
              value={channelsBlocked}
              tone={channelsBlocked > 0 ? "bad" : undefined}
              sub={
                board.rejected.length
                  ? `${board.rejected.length} listings rejected outright`
                  : "cannot publish as they stand"
              }
            />
            <Kpi
              label="Safety flags"
              value={safetyFlags}
              tone={safetyFlags > 0 ? "bad" : undefined}
              sub="allergen or safety value moved"
            />
            <Kpi
              label="Waiting on review"
              value={awaitingReview}
              tone={awaitingReview > 0 ? "bad" : undefined}
              sub={
                run?.awaiting_approval
                  ? "run suspended at approval"
                  : "listings held until approved"
              }
            />
          </div>

          <Panel
            title="Corrections in force"
            icon={<IconCorrection size={14} />}
            tone={summary.length ? "warn" : undefined}
            subtitle={
              correction?.assets_stale
                ? `${fmt.count(correction.assets_stale)} assets on the old value`
                : undefined
            }
          >
            {summary.length > 0 ? (
              <div className="flex flex-col gap-2.5">
                <ul className="flex list-disc flex-col gap-1.5 pl-4 text-sm leading-relaxed">
                  {summary.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
                {supersededDocs.length > 0 && (
                  <div className="flex flex-wrap items-center gap-1.5 border-t border-subtle pt-2">
                    <IconDoc size={13} className="shrink-0 text-faint" />
                    <span className="text-xs text-faint">
                      no longer in force:
                    </span>
                    {supersededDocs.map((id) => (
                      <Code key={id}>{id}</Code>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <EmptyState compact art={<ArtAllClear />} title="The catalog is clean">
                No supplier correction is in force. Every listing is still
                standing on the value its content was written against.
              </EmptyState>
            )}
          </Panel>

          {/* One row per product with something open, in the order the API
              returned - which is the order the loop itself picks in. */}
          <Panel
            title="Open corrections"
            icon={<IconCorrection size={14} />}
            flush
            tone={
              cases?.some((c) => c.safety)
                ? "danger"
                : cases?.length
                ? "warn"
                : undefined
            }
            subtitle={
              cases === null
                ? "reading…"
                : cases.length
                ? `${cases.length} ${cases.length === 1 ? "case" : "cases"} · worst first`
                : undefined
            }
          >
            {cases === null ? (
              <div className="p-3">
                <Skeleton className="h-24 w-full" rounded="md" />
              </div>
            ) : cases.length === 0 ? (
              <EmptyState art={<ArtAllClear />} title="No case is open">
                The catalog is clean — every product is standing on the value
                its content was written against.{" "}
                {quiet
                  ? "The feed is routine traffic: prices, stock and unchanged confirmations. A case appears the moment a document contradicts what the copy was written against."
                  : "A case appears here as soon as a correction is attributed to a product."}
              </EmptyState>
            ) : (
              <>
                {unscoped && (
                  <UnscopedCase c={unscoped} busy={busy} onWork={onStartRun} />
                )}
                <div className="sc-stagger max-h-[420px] overflow-y-auto">
                  {scoped.map((c, i) => (
                    <CaseRow
                      key={c.case_id}
                      c={c}
                      index={i}
                      vocab={vocab}
                      channels={channelsOfProduct.get(c.product) ?? []}
                      busy={busy}
                      onWork={onStartRun}
                    />
                  ))}
                </div>
                <p className="border-t border-subtle px-3 py-2 text-xs leading-relaxed text-faint">
                  A case is one product — the unit the publish lock is taken on
                  and the unit a reviewer commits. Running the loop without
                  picking a row works the top case, {" "}
                  <Code>{worstOpen?.case_id}</Code>, and nothing else.
                </p>
              </>
            )}
          </Panel>

          <Panel
            title="Correction run"
            tone={run?.awaiting_approval ? "warn" : undefined}
          >
            {run ? (
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Severity level={run.values.severity} />
                  <Badge tone="neutral" mono>{run.status}</Badge>
                  {/* Which case this run is about. A run is one product. */}
                  {run.values.case_id && (
                    <Tooltip content={run.values.case?.title ?? "the case this run is scoped to"}>
                      <span><Code>{run.values.case_id}</Code></span>
                    </Tooltip>
                  )}
                  {run.awaiting_approval && (
                    <Badge tone="warn" dot>waiting on a reviewer</Badge>
                  )}
                  {run.values.material === false && (
                    <Badge tone="neutral">nothing material</Badge>
                  )}
                </div>
                {run.values.triage_reason && (
                  <p className="text-sm leading-relaxed text-muted">
                    {run.values.triage_reason}
                  </p>
                )}
                {runTotals && (
                  <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted">
                    <span>{fmt.count(Number(runTotals.fields ?? 0))} fields</span>
                    <span>{fmt.count(Number(runTotals.assets ?? 0))} assets</span>
                    <span>{fmt.count(Number(runTotals.listings ?? 0))} listings</span>
                    <span>{fmt.count(Number(runTotals.channels ?? 0))} channels</span>
                  </div>
                )}
              </div>
            ) : (
              <EmptyState
                art={<ArtNoRun />}
                title="No run yet"
                action={
                  <Button
                    tone="primary"
                    onClick={() => onStartRun()}
                    loading={busy}
                    icon={<IconSpark size={14} />}
                  >
                    {worstOpen ? "Run the worst open case" : "Run the correction loop"}
                  </Button>
                }
              >
                Advance the replay to the supplier correction, then work a case
                — pick one from Open corrections, or start here and the loop
                takes the worst one open. It reads what the document says, works
                out which variant it applies to, traces every field and channel
                built on the old value, and stops for your approval.
              </EmptyState>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}

/* --- open correction cases -------------------------------------------------- */

/** A channel the case has to land on, in the state it is in today. */
interface ChannelReach { id: string; name: string; state?: ChannelState }

const STATE_RANK: Record<ChannelState, number> = {
  ready: 1, blocked: 2, withheld: 3, rejected: 4,
};

/** A product on six channels is presented by the worst thing true of it: one
 *  rejection must not be averaged away by five healthy listings. */
function worseOf(a?: ChannelState, b?: ChannelState): ChannelState | undefined {
  if (!a) return b;
  if (!b) return a;
  return STATE_RANK[a] >= STATE_RANK[b] ? a : b;
}

/** One open case: one product, everything in force on it, and the run that
 *  would resolve it.
 *
 * The whole row is the control, because the answer to "what is it about to work
 * on?" and the act of working it are the same thing. The lead signal is the
 * first the API listed - a case is presented by what it says, not by a count of
 * how many rows it has - and the rest are counted rather than dropped.
 */
function CaseRow({ c, index, vocab, channels, busy, onWork }: {
  c: OpenCase;
  index: number;
  vocab: Vocab;
  channels: ChannelReach[];
  busy: boolean;
  onWork: (caseId: string) => void;
}) {
  const lead = c.signals[0];
  const rest = c.signals.slice(1);
  const path = lead?.attribute_paths?.[0] ?? "";
  const def = path ? vocab.def(path) : undefined;
  const moves = lead?.old_value !== undefined || lead?.new_value !== undefined;

  // The catalog says which of the corrected paths are safety-class; the API
  // already said whether any is, so a catalog that has not loaded still flags.
  const safetyPaths = c.attribute_paths.filter((p) => vocab.def(p)?.safety_class);
  const safetyCount = c.safety ? Math.max(safetyPaths.length, 1) : 0;

  const named = vocab.name(c.product);
  const productName = named && named !== c.case_id ? named : c.title;
  const fields = c.attribute_paths.length;

  return (
    <button
      type="button"
      onClick={() => onWork(c.case_id)}
      disabled={busy}
      style={{ ["--i" as string]: index }}
      className={cn(
        "group flex w-full flex-col gap-1.5 border-b border-subtle px-3 py-2.5",
        "text-left transition-colors hover:bg-hover",
        "focus-visible:bg-hover disabled:pointer-events-none disabled:opacity-60"
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Severity level={c.severity_hint} />
        <span className="text-sm font-medium text-fg">{productName}</span>
        <Code>{c.case_id}</Code>
        {c.regulated && <RegulatedTag />}
        <SafetyFlag count={safetyCount} />
        <span className="ml-auto whitespace-nowrap text-2xs uppercase tracking-caps text-faint group-hover:text-accent-text">
          work this case →
        </span>
      </div>

      {lead && (
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone={CORRECTION_TONE[lead.kind] ?? "neutral"}>
            {CORRECTION_LABEL[lead.kind] ?? lead.kind}
          </Badge>
          {lead.provisional && <Badge tone="warn" dot>provisional</Badge>}
          <ProvBadge provenance={lead.provenance} />
          {rest.length > 0 && (
            <Tooltip content={rest.map((s) => s.summary).join("\n")}>
              <span>
                <Badge tone="neutral">
                  +{rest.length} more on this product
                </Badge>
              </span>
            </Tooltip>
          )}
        </div>
      )}

      <p className="text-sm leading-relaxed">
        {lead?.summary ?? "Nothing in force on this product."}
      </p>

      {lead && moves && (
        <ValueDiff
          oldValue={lead.old_value}
          newValue={lead.new_value}
          unit={lead.unit ?? def?.unit}
          ordered={def?.ordered ?? true}
        />
      )}

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        {/* Every document the case stands on, both sides of a disagreement
            included - the version comes from the signal that cited it. */}
        {c.documents.map((doc) => (
          <SourceCite
            key={doc}
            source={{
              doc_id: doc,
              version: versionOf(c, doc),
              excerpt: "",
            }}
          />
        ))}
        <Tooltip
          content={
            fields
              ? c.attribute_paths.map((p) => `${vocab.attr(p)} (${p})`).join("\n")
              : "No value moved. What is open here is a channel refusing the listing."
          }
        >
          <span className="whitespace-nowrap text-xs text-muted">
            {fields ? `${fields} ${fields === 1 ? "field" : "fields"}` : "no field"}
            {" · "}
            {channels.length} {channels.length === 1 ? "channel" : "channels"}
          </span>
        </Tooltip>
      </div>

      {channels.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          {channels.map((ch) => (
            <ChannelChip
              key={ch.id}
              channelId={ch.id}
              name={ch.name}
              state={ch.state}
            />
          ))}
        </div>
      )}
    </button>
  );
}

/** The version a case's signals cited a document at, where one did. */
function versionOf(c: OpenCase, docId: string): string {
  for (const signal of c.signals) {
    if (signal.source?.doc_id === docId) return signal.source.version;
  }
  return "";
}

/** A correction the system could not attribute to a product.
 *
 * Not a row in the queue: no publish lock covers it, so no reviewer owns it,
 * and it cannot be decided the way the rest of the list can. It is drawn as the
 * governance signal it is, above the cases that can actually be worked.
 */
function UnscopedCase({ c, busy, onWork }: {
  c: OpenCase;
  busy: boolean;
  onWork: (caseId: string) => void;
}) {
  const n = c.signals.length;
  return (
    <div className="border-b border-danger-border bg-danger-soft/40 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <IconAlert size={14} className="shrink-0 text-danger-text" />
        <span className="text-sm font-medium text-danger-text">
          {n} {n === 1 ? "correction names" : "corrections name"} no product
        </span>
        <Code>{c.case_id}</Code>
      </div>
      <p className="mt-1 text-sm leading-relaxed text-muted">
        The publish lock is taken per product, so a correction that cannot be
        attributed to one has no owner and no lock — it cannot be committed the
        way the cases below can. Read it before anything else is approved.
      </p>
      <ul className="mt-1.5 flex list-disc flex-col gap-1 pl-4 text-sm leading-relaxed">
        {c.signals.slice(0, 3).map((s) => (
          <li key={s.id}>{s.summary}</li>
        ))}
      </ul>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {c.documents.map((doc) => (
          <SourceCite
            key={doc}
            source={{ doc_id: doc, version: versionOf(c, doc), excerpt: "" }}
          />
        ))}
        <Button
          size="xs"
          className="ml-auto"
          disabled={busy}
          onClick={() => onWork(c.case_id)}
        >
          Work the unattributed corrections
        </Button>
      </div>
    </div>
  );
}

/* --- the feed, in sentences ------------------------------------------------ */

/** "45 W", "peanuts", "38". */
function withUnit(value: unknown, unit: unknown): string {
  const text = fmt.value(value);
  return typeof unit === "string" && unit ? `${text} ${unit}` : text;
}

/** "rated power 45 → 65 W" out of a change row or a flat payload. */
function changeClause(row: Record<string, unknown>, v: Vocab): string {
  const label = v.attr(row.attribute_path ?? row.path) || "the value";
  const to = withUnit(row.new_value, row.unit);
  if (row.old_value === undefined || row.old_value === null) {
    return `${label} now ${to}`;
  }
  return `${label} ${withUnit(row.old_value, row.unit)} → ${to}`;
}

/** Who the document says it is about - and, in the case that drives the whole
 *  demo, that it does not say. */
function scopeClause(p: Record<string, unknown>, v: Vocab): string {
  const entities = (Array.isArray(p.entities) ? p.entities : [])
    .filter((x): x is string => typeof x === "string")
    .map((id) => v.name(id));
  const product = v.name(p.product);
  switch (String(p.applies_to ?? "")) {
    case "UNCLEAR":
      return product
        ? `on ${product}, without saying which variant`
        : "without saying which variant";
    case "VARIANT":
      return entities.length ? `for ${entities.join(" and ")}` : "for one variant";
    case "PRODUCT":
      return product ? `at product level on ${product}` : "at product level";
    case "ALL":
      return product ? `for every variant of ${product}` : "for every variant";
    default:
      return entities.length ? `on ${entities.join(" and ")}` : "";
  }
}

const join = (head: string, parts: string[]) => {
  const tail = parts.filter(Boolean).join(", ");
  return tail ? `${head} — ${tail}.` : `${head}.`;
};

/** One line of the feed, as a sentence a person would say.
 *
 * The tape carries six kinds of event and each is a different sort of news: a
 * routine price row and a spec sheet that moves an allergen must not read the
 * same way, and neither should read as a dumped payload.
 */
function describe(e: SCEvent, v: Vocab): string {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  const str = (k: string) => (typeof p[k] === "string" ? (p[k] as string) : "");

  switch (e.type) {
    case "SUPPLIER_FEED": {
      const who = v.name(p.supplier) || "A supplier";
      const what = v.name(p.entity_id) || "the catalog";
      switch (str("kind")) {
        case "STOCK":
          return `${who} reported ${fmt.count(Number(p.on_hand ?? 0))} in stock for ${what}.`;
        case "PRICE":
          return `${who} repriced ${what} at ${fmt.value(p.price)} ${str("currency")}`.trim() + ".";
        case "ATTRIBUTE_CONFIRM":
          return `${who} ${p.certified ? "certified" : "confirmed"} ${
            v.attr(p.path)} unchanged on ${what} — ${withUnit(p.value, p.unit)}.`;
        case "ATTRIBUTE":
          return p.is_correction
            ? `${who} corrected ${v.attr(p.path)} on ${what} to ${withUnit(p.value, p.unit)}.`
            : `${who} sent ${v.attr(p.path)} for ${what} — ${withUnit(p.value, p.unit)}.`;
        default:
          return `${who} sent a feed row for ${what}.`;
      }
    }

    case "SPEC_DOC": {
      const who = v.name(p.supplier) || "A supplier";
      const version = str("doc_version");
      const head = `${who} sent ${version ? `revision ${version} of ` : ""}${
        str("doc_id") || "a document"}`;
      const changes = (Array.isArray(p.changes) ? p.changes : [])
        .filter((c): c is Record<string, unknown> => Boolean(c) && typeof c === "object");
      const parts: string[] = [];
      if (changes.length === 1) parts.push(changeClause(changes[0], v));
      else if (changes.length > 1) parts.push(`${changes.length} values move`);
      else if (p.new_value !== undefined) parts.push(changeClause(p, v));
      else if (p.zero_delta) parts.push("republished with nothing changed");
      if (str("summary")) parts.push(str("summary"));
      if (p.provisional) parts.push("treat as provisional");
      parts.push(scopeClause(p, v));
      return join(head, parts);
    }

    case "CHANNEL_STATUS": {
      const channel = v.name(p.channel_id) || "A channel";
      const what = v.name(p.variant_id) || v.name(p.product) || "a listing";
      const code = str("code");
      switch (str("status")) {
        case "REJECTED":
          return join(
            `${channel} rejected the ${what} feed${code ? ` (${code})` : ""}`,
            [str("detail")]
          );
        case "ACCEPTED":
          return `${channel} accepted the ${what} feed.`;
        default:
          return join(
            `${channel} reported ${str("status").toLowerCase()} on ${what}`,
            [code, str("detail")]
          );
      }
    }

    case "PUBLISH_TELEMETRY": {
      const channel = v.name(p.channel_id) || "A channel";
      const what = v.name(p.variant_id) || "a listing";
      if (str("status") && str("status") !== "OK") {
        return `${channel} reported ${str("status").toLowerCase()} serving ${what}.`;
      }
      return `${channel} served ${fmt.count(Number(p.impressions ?? 0))} views of ${what}.`;
    }

    case "CATALOG_UPDATE": {
      const doc = `${str("doc_id")}${str("doc_version") ? ` ${str("doc_version")}` : ""}`;
      const status = str("status").toLowerCase();
      const reason = str("reason").replace(/_/g, " ");
      return join(`${doc || "A document"} is now ${status || "changed"}`, [reason]);
    }

    case "COMMS": {
      const who = v.name(p.supplier) || str("from") || "Someone";
      const parts: string[] = [];
      if (p.resolves_issue) parts.push("this clears the earlier notice");
      else if (p.provisional) parts.push("treat as provisional");
      else if (str("summary")) parts.push(str("summary"));
      return join(`${who} wrote: “${str("subject") || "no subject"}”`, parts);
    }

    default:
      return JSON.stringify(p).slice(0, 140);
  }
}

/** The tone of the news, not the tone of the type. A rejection is red whatever
 *  carried it; a stock row is grey whatever it says. */
function eventTone(e: SCEvent): BadgeTone {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  switch (e.type) {
    case "CHANNEL_STATUS":
      return p.status === "REJECTED" ? "danger" : "neutral";
    case "SPEC_DOC":
      return p.is_correction ? "warn" : "info";
    case "CATALOG_UPDATE":
      return "warn";
    case "COMMS":
      return p.material_hint ? "info" : "neutral";
    case "SUPPLIER_FEED":
      return p.is_correction ? "warn" : "neutral";
    default:
      return "neutral";
  }
}

const SUBJECT_KEYS = [
  "listing_id", "entity_id", "variant_id", "product", "doc_id", "channel_id",
];

/** The one id worth keeping on the row. A reviewer searching for LST-11 has to
 *  be able to find it without opening anything. */
function subjectId(e: SCEvent): string {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  for (const key of SUBJECT_KEYS) {
    const value = p[key];
    if (typeof value === "string" && value) return value;
  }
  const entities = Array.isArray(p.entities) ? p.entities : [];
  const first = entities.find((x) => typeof x === "string");
  return typeof first === "string" ? first : "";
}

const ID_KEYS = [
  "doc_id", "doc_version", "supplier", "product", "entity_id", "variant_id",
  "listing_id", "channel_id", "path", "attribute_path", "code", "field",
];

/** Every identifier on the event, for the tooltip. The sentence is for reading;
 *  this is for looking something up afterwards. */
function idLine(e: SCEvent): string {
  const p = (e.payload ?? {}) as Record<string, unknown>;
  const bits = [e.type, e.id];
  for (const key of ID_KEYS) {
    const value = p[key];
    if (typeof value === "string" && value) bits.push(value);
  }
  for (const entity of Array.isArray(p.entities) ? p.entities : []) {
    if (typeof entity === "string") bits.push(entity);
  }
  return Array.from(new Set(bits)).join(" · ");
}

/** The trace totals, as the API counted them. */
function traceLine(totals: Record<string, number | string[]>): string {
  const n = (k: string) => Number(totals[k] ?? 0);
  return `${n("fields")} fields · ${n("assets")} assets · ${
    n("listings")} listings · ${n("channels")} channels`;
}
