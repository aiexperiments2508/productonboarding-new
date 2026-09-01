import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { UNSCOPED_CASE, api, fmt } from "../api";
import type {
  AffectedScope, CatalogState, CorrectionKind, KPIs, MapView, OpenCase,
  RunSnapshot, SCEvent,
} from "../api";
import { applyEvents, emptyImpact, impactFrom, prunePulses } from "../liveImpact";
import type { LiveImpact } from "../liveImpact";
import { ArtAllClear, ArtNoRun } from "../art/illustrations";
import {
  IconAlert, IconChevronLeft, IconChevronRight, IconCorrection, IconDoc,
  IconSpark, IconTrace,
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
import { DEFAULT_MAP_FILTERS, MapControls } from "./MapControls";
import type { MapFilters } from "./MapControls";
import { MapLegend, NetworkMap, listingStatusMap } from "./NetworkMap";
import { buildVocab } from "./vocab";
import type { Vocab } from "./vocab";

/* The ingest fabric.
 *
 * The graph, and what it is standing on. One claim, one owner:
 *
 *   the map          structure and reach. Click a node and the API walks the
 *                    lineage; the highlight is the answer it gave, not one the
 *                    component worked out. The tape's arrivals pulse over it
 *                    live, so the picture moves while the clock runs.
 *
 * Everything else this screen used to carry has gone to the section that owns
 * it. The estate and the live feed are System Control's - they are the
 * machinery under the map rather than the map - and the supplier bundle is
 * Supplier Intake's, which is the screen about a bundle. What is left is the
 * thing the section is named for, at the size a room can read.
 *
 * What is *in force* stays here, because it is a property of the picture rather
 * than of the plumbing: which corrections are live, which products have
 * something open, and the run working one of them. It sits in a rail that is
 * shut by default. A rail closed is not a rail hidden - the handle carries the
 * open-case count and takes the severity of the worst one, so a reader watching
 * only the graph still knows there is something to open.
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

/** Tied to the client rather than restated, so a change to the trace endpoint
 *  shows up here as a type error instead of as a quietly empty highlight. */
type TraceResult = Awaited<ReturnType<typeof api.trace>>;

/** Whether the rail is open. Shut on a first visit, and remembered after -
 *  the same treatment the nav rail gets, for the same reason: it is a working
 *  preference and re-collapsing it on every load would be a small daily tax. */
const RAIL_KEY = "sc.fabricRail";

export function IngestFabric({
  catalog, events, run, onStartRun, busy,
}: {
  catalog: CatalogState | null;
  events: SCEvent[];
  run: RunSnapshot | null;
  /** Work one case. Without an id the loop takes the worst one open. */
  onStartRun: (caseId?: string) => void;
  busy: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [live, setLive] = useState<LiveImpact>(emptyImpact);
  const seenRef = useRef<string>("");

  const [railOpen, setRailOpen] = useState(
    () => localStorage.getItem(RAIL_KEY) === "1"
  );
  const toggleRail = useCallback(() => {
    setRailOpen((open) => {
      localStorage.setItem(RAIL_KEY, open ? "0" : "1");
      return !open;
    });
  }, []);

  /* The map draws a page of the catalog rather than all of it.
   *
   * It used to draw `catalog`, which is the whole estate - correct at six
   * products and unreadable at a hundred and fifty, and refetched in full on
   * every event the replay released. This is its own scoped read: ten products
   * by default, chosen by the filters, and re-read only when those change or
   * when something material lands. */
  const [mapFilters, setMapFilters] = useState<MapFilters>(DEFAULT_MAP_FILTERS);
  const [mapView, setMapView] = useState<MapView | null>(null);
  const [mapBusy, setMapBusy] = useState(false);
  const mapTicket = useRef(0);

  const loadMap = useCallback(() => {
    const ticket = ++mapTicket.current;
    setMapBusy(true);
    api.networkMap({ ...mapFilters, focus: selected })
      .then((view) => { if (ticket === mapTicket.current) setMapView(view); })
      .catch(() => { if (ticket === mapTicket.current) setMapView(null); })
      .finally(() => { if (ticket === mapTicket.current) setMapBusy(false); });
  }, [mapFilters, selected]);

  // Debounced, so typing in the map search is one request rather than one per
  // character.
  useEffect(() => {
    const timer = setTimeout(loadMap, 220);
    return () => clearTimeout(timer);
  }, [loadMap]);

  // The catalog moving is what makes a drawn listing status stale. Coalesced
  // hard: the replay releases events continuously, and re-reading the map on
  // each one was the single most expensive thing this screen did.
  const catalogStamp = catalog?.as_of ?? "";
  useEffect(() => {
    if (!catalogStamp) return;
    const timer = setTimeout(loadMap, 800);
    return () => clearTimeout(timer);
  }, [catalogStamp, loadMap]);

  /* Fold newly-arrived events into the decaying highlight state.
   *
   * The feed itself moved to System Control; this did not, and the distinction
   * matters. The list of arrivals is a thing to read, and it belongs beside the
   * transport that releases it. The *pulse* is a property of the map - it is
   * how a reader sees the tape reaching the catalog - and it rides the same
   * `events` prop the shell already holds, so nothing had to be re-subscribed.
   *
   * The feed is prepend-ordered, so the newest event id is enough to tell
   * whether anything actually arrived - re-applying the whole list on every
   * render would keep every node permanently lit. */
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

  /* The page the map draws, in the shape the renderer expects.
   *
   * NetworkMap takes a CatalogState because that is what it has always taken,
   * and it reads five fields of it. Adapting here rather than reworking the
   * renderer keeps one drawing routine: the map does not need to know whether
   * it was handed the whole catalog or ten products of it, and a second
   * renderer for "the same picture but smaller" is a second thing to keep
   * right. Falls back to the full catalog until the first page lands, so the
   * screen never opens on an empty frame. */
  const mapCatalog = useMemo<CatalogState | null>(() => {
    if (!mapView) return catalog;
    if (!catalog) return null;
    return {
      ...catalog,
      nodes: mapView.nodes,
      edges: mapView.edges,
      products: mapView.products,
      variants: mapView.variants,
      channels: mapView.channels,
      listings: mapView.listings,
      correction: { ...catalog.correction, ...mapView.correction },
    };
  }, [mapView, catalog]);

  /* --- lookups ---------------------------------------------------------- */

  const vocab = useMemo<Vocab>(() => buildVocab(catalog), [catalog]);

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
        section="fabric"
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
                  ? `Works one case: ${worstOpen.title}. Open the rail and pick any other row to work that product instead.`
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

      <div className="flex min-h-0 flex-1 gap-3">
        <Panel
          className="min-h-0 min-w-0 flex-1"
          bodyClassName="flex min-h-0 flex-col"
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
          {catalog && mapCatalog ? (
            <>
              <MapControls
                filters={mapFilters}
                onChange={setMapFilters}
                facets={mapView?.facets}
                page={mapView?.page}
                busy={mapBusy}
              />
              {/* The scroller the map's own min-width scrolls against, and now
                  the tallest thing on the screen rather than half of it. Both
                  axes: sideways below the width its labels survive, downwards
                  when a dense estate outgrows the section. */}
              <div className="min-h-0 flex-1 overflow-auto">
                <NetworkMap
                  catalog={mapCatalog}
                  affected={traced}
                  live={live}
                  selected={selected}
                  onSelect={setSelected}
                />
              </div>
              <div className="shrink-0 border-t border-subtle px-3 py-2.5">
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

        <IssuesRail
          open={railOpen}
          onToggle={toggleRail}
          count={cases?.length ?? 0}
          safety={!!cases?.some((c) => c.safety)}
          awaiting={run?.awaiting_approval ?? false}
        >
          {/* The four figures a reviewer opens the rail for. */}
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
        </IssuesRail>
      </div>
    </>
  );
}

/* --- the rail --------------------------------------------------------------- */

/** What is in force, beside the graph rather than instead of it.
 *
 * Shut by default. The handle is the whole argument for that being acceptable:
 * it carries the number of open cases and takes the colour of the worst one, so
 * the state a reader is missing is legible from the state they can see. A
 * collapsed panel that showed nothing would be a way of losing the queue.
 */
function IssuesRail({ open, onToggle, count, safety, awaiting, children }: {
  open: boolean;
  onToggle: () => void;
  count: number;
  safety: boolean;
  awaiting: boolean;
  children: React.ReactNode;
}) {
  const tone: BadgeTone = safety ? "danger" : count ? "warn" : "neutral";
  const label = count
    ? `${count} open ${count === 1 ? "case" : "cases"}`
    : "nothing open";

  return (
    <aside
      aria-label="What is in force"
      style={{ width: open ? "clamp(320px, 27vw, 420px)" : "40px" }}
      className={cn(
        "flex shrink-0 flex-col gap-2 overflow-hidden",
        "transition-[width] duration-[var(--dur-base)] ease-standard"
      )}
    >
      <Tooltip content={open ? "Hide what is in force" : `Show what is in force — ${label}`}>
        <Button
          size="xs"
          tone="ghost"
          aria-expanded={open}
          onClick={onToggle}
          icon={open ? <IconChevronRight size={14} /> : <IconChevronLeft size={14} />}
          className={cn("shrink-0", open ? "self-end" : "self-center")}
        >
          {open ? "hide" : undefined}
        </Button>
      </Tooltip>

      {open ? (
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
          {children}
        </div>
      ) : (
        /* The shut state, and the reason shutting it is honest. Vertical so it
           fits 40px, and the badge sits above the words because the number is
           what a glance is for. */
        <button
          type="button"
          onClick={onToggle}
          aria-label={`Show what is in force — ${label}`}
          className={cn(
            "flex min-h-0 flex-1 flex-col items-center gap-2 rounded-md py-2",
            "border border-subtle bg-raised transition-colors hover:bg-hover"
          )}
        >
          {(count > 0 || awaiting) && (
            <Badge tone={tone} dot={safety || awaiting}>
              {count || "!"}
            </Badge>
          )}
          <span
            className="text-2xs uppercase tracking-caps text-faint"
            style={{ writingMode: "vertical-rl" }}
          >
            in force
          </span>
        </button>
      )}
    </aside>
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

/** The trace totals, as the API counted them. */
function traceLine(totals: Record<string, number | string[]>): string {
  const n = (k: string) => Number(totals[k] ?? 0);
  return `${n("fields")} fields · ${n("assets")} assets · ${
    n("listings")} listings · ${n("channels")} channels`;
}
