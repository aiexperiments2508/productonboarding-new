import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { UNSCOPED_CASE, api, fmt, streamBatchAssess } from "../api";
import type {
  AffectedScope, BatchProduct, BatchRow, BatchTotals, CatalogState,
  CorrectionKind, KPIs, MapView, OpenCase, RunSnapshot, SCEvent,
} from "../api";
import {
  applyEvents, clearSweep, emptyImpact, impactFrom, prunePulses, withWorking,
} from "../liveImpact";
import type { LiveImpact } from "../liveImpact";
import { ArtAllClear, ArtNoRun, ArtQuietFeed } from "../art/illustrations";
import {
  IconAlert, IconChevronLeft, IconChevronRight, IconCorrection, IconDoc,
  IconIntake, IconPause, IconSpark, IconTrace,
} from "../icons";
import { PageHeader } from "../app/shell/PageHeader";
import {
  Badge, Button, Code, EmptyState, Panel, ProgressBar, Skeleton, Spinner,
  Tooltip, cn, useToast,
} from "../ui";
import type { BadgeTone } from "../ui";
import {
  ChannelChip, Kpi, ProvBadge, RegulatedTag, SafetyFlag, Severity, SourceCite,
  ValueDiff, listingChannelState,
} from "./common";
import type { ChannelState } from "./common";
import { EventFeed } from "./EventFeed";
import { DEFAULT_MAP_FILTERS, MapControls } from "./MapControls";
import type { MapFilters } from "./MapControls";
import { MapLegend, NetworkMap, listingStatusMap } from "./NetworkMap";
import { verdictBadge } from "./verdict";
import { buildVocab } from "./vocab";
import type { Vocab } from "./vocab";

/* The ingest fabric.
 *
 * The graph, and the two questions it sits between. Read left to right, which
 * is the direction the map itself reads:
 *
 *   incoming   what suppliers have sent and what the tape has released. The
 *              queue of bundles waiting to be processed, and the live feed
 *              underneath it. This is the arrivals side.
 *
 *   the map    structure and reach. Click a node and the API walks the
 *              lineage; the highlight is the answer it gave, not one the
 *              component worked out. Arrivals pulse over it live, and the
 *              sequential pass lights one product at a time as it walks a
 *              bundle - so the picture moves while the work happens.
 *
 *   in force   which corrections are live, which products have something
 *              open, and the run working one of them. Shut by default; the
 *              handle carries the open-case count and takes the severity of
 *              the worst one, so a reader watching only the graph still knows
 *              there is something to open.
 *
 * **The two sweeps, and why they are different things.** Both walk a queue one
 * item at a time; they are not the same queue and they do not do the same
 * work.
 *
 *   process the queue    the onboarding pass over a supplier bundle. Is this
 *                        record fit to sell? Runs per product, decides
 *                        nothing a person has to approve, and leaves a
 *                        verdict ring on the map behind it.
 *   work every open case the correction loop over what is in force. One run
 *                        per product, each stopping at its own approval gate,
 *                        because a reviewer approves a decision about a
 *                        product. It used to work exactly one case per click
 *                        and leave the rest of the queue where it was.
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

/** Whether each rail is open, remembered. The nav rail gets the same
 *  treatment for the same reason: it is a working preference, and
 *  re-collapsing it on every load would be a small daily tax.
 *
 *  Incoming opens by default and In force does not, which is a claim about
 *  what a reader arrives wanting: what has just landed, before what is still
 *  outstanding. */
const RAIL_KEY = "sc.fabricRail";
const INCOMING_KEY = "sc.fabricIncoming";
const SYSTEMS_KEY = "sc.fabricSystems";

/** How long the map holds on one product before moving to the next.
 *
 *  Presentation only: the report is identical whatever it is set to, and no
 *  figure on screen depends on it. It exists because a pass that decided forty
 *  products in nine hundred milliseconds would light the map in a way nobody
 *  can follow, and the point of walking one at a time is that it can be
 *  followed.
 *
 *  **Paced here rather than on the server, and that is not a preference.**
 *  `assess/stream` takes a `pace_ms` and will sleep between products, which
 *  works right up until something between the two buffers the response - a
 *  reverse proxy without `proxy_buffering off`, a dev server's proxy, an
 *  embedded webview. Then every frame lands in one chunk, React batches the
 *  four state updates into one render, and the walk the whole feature exists
 *  to show is skipped silently. Buffering cannot reorder or drop frames, so a
 *  client that paces its own reading is correct on every transport. The server
 *  is asked for the work as fast as it can do it. */
const PACE_MS = 420;

const wait = (ms: number) => new Promise((done) => setTimeout(done, ms));

/** How many products the map draws while a bundle is being processed.
 *
 *  Larger than the reading default: the map draws a page of the catalog, so a
 *  product being assessed outside that page would light nothing at all. Pinned
 *  once per bundle rather than per product - one extra read, not forty. */
const SWEEP_LIMIT = 25;

/** A ceiling on the case sweep, so a record that keeps opening cases cannot
 *  spin. Never reached in practice; it is here so that "walks until the queue
 *  is empty" has a bound somebody wrote down. */
const MAX_SWEEP_RUNS = 50;

/** Where one bundle in the queue has got to, in this browser.
 *
 *  Deliberately not read back from the server. The durable answer to "how did
 *  this bundle do" is the report, and computing it means assessing every
 *  product in it - which is the work the queue exists to schedule, not
 *  something to do for every row on a page load. So a row says `queued` until
 *  something has actually walked it, and then says what that walk found. */
interface QueueState {
  state: "queued" | "processing" | "done" | "failed";
  totals?: BatchTotals;
  error?: string;
}

export function IngestFabric({
  catalog, events, run, onStartRun, busy, onReplay, arrivals, onOpenBatch,
}: {
  catalog: CatalogState | null;
  events: SCEvent[];
  run: RunSnapshot | null;
  /** Work one case. Without an id the loop takes the worst one open.
   *  `navigate: false` keeps the reader here, which is what a sweep needs. */
  onStartRun: (caseId?: string,
               options?: { navigate?: boolean }) => Promise<unknown> | void;
  busy: boolean;
  /** Drive the tape, for the feed's jump control. */
  onReplay: (body: { action: string; steps?: number; speed?: number;
                     to_seq?: number }) => void;
  /** Bumped by the shell whenever a portal pushes something. Not the
   *  submission itself - just a reason to read the queue again. */
  arrivals: number;
  /** Hand a bundle to Supplier Intake, which is the screen about one bundle. */
  onOpenBatch?: (batchId: string) => void;
}) {
  const toast = useToast();
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

  const [incomingOpen, setIncomingOpen] = useState(
    () => localStorage.getItem(INCOMING_KEY) !== "0"
  );
  const toggleIncoming = useCallback(() => {
    setIncomingOpen((open) => {
      localStorage.setItem(INCOMING_KEY, open ? "0" : "1");
      return !open;
    });
  }, []);

  const [showSystems, setShowSystems] = useState(
    () => localStorage.getItem(SYSTEMS_KEY) === "1"
  );
  const toggleSystems = useCallback(() => {
    setShowSystems((on) => {
      localStorage.setItem(SYSTEMS_KEY, on ? "0" : "1");
      return !on;
    });
  }, []);

  /* The map draws a page of the catalog rather than all of it.
   *
   * It used to draw `catalog`, which is the whole estate - correct at six
   * products and unreadable at a hundred and fifty, and refetched in full on
   * every event the replay released. This is its own scoped read: a handful of
   * products by default, chosen by the filters, and re-read only when those
   * change or when something material lands. */
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
   * renderer keeps one drawing routine. Falls back to the full catalog until
   * the first page lands, so the screen never opens on an empty frame. */
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

  const readCases = useCallback(async () => {
    try {
      const answer = await api.cases();
      setCases(answer.cases);
      return answer.cases;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => { void readCases(); }, [readCases, catalog?.as_of, run?.status]);

  /* --- what suppliers have sent ------------------------------------------ */

  const [queue, setQueue] = useState<BatchRow[] | null>(null);
  const [progress, setProgress] = useState<Record<string, QueueState>>({});
  // Which product the pass is on, for the line above the queue.
  const [walk, setWalk] = useState<
    { batch: string; ordinal: number; total: number; name: string } | null
  >(null);
  // "queue" walks supplier bundles; "cases" walks the correction loop. One at
  // a time: both drive the same map, and two passes lighting it at once would
  // be two claims about where the work is.
  const [sweeping, setSweeping] = useState<"queue" | "cases" | null>(null);
  const [swept, setSwept] = useState<{ done: number; total: number } | null>(null);
  const stopRef = useRef(false);
  // The reader's own map filters, restored when a sweep gives the map back.
  const filtersBeforeRef = useRef<MapFilters | null>(null);

  const readQueue = useCallback(() => {
    api.batches()
      .then((answer) => setQueue(answer.batches))
      .catch(() => setQueue([]));
  }, []);

  // Read on arrival at the section, and again whenever a portal pushes
  // something. `arrivals` is a counter the shell bumps off the live lane, so a
  // supplier's upload appears here without anybody polling for it.
  useEffect(readQueue, [readQueue, arrivals]);

  const pending = useMemo(
    () => (queue ?? []).filter(
      (b) => (progress[b.batch_id]?.state ?? "queued") === "queued"),
    [queue, progress]
  );

  /* Walk one bundle, one product at a time, lighting the map as it goes.
   *
   * Every message the server sends is used as it arrives: `entities` on each
   * product is the path the map lights - variant, product, supplier - resolved
   * server-side, so the browser does not rediscover the catalog's own shape.
   * The previous product keeps a verdict-coloured ring, which is what stops a
   * finished pass reverting the map to how it looked before.
   */
  const processBatch = useCallback(async (batch: BatchRow) => {
    setProgress((p) => ({ ...p, [batch.batch_id]: { state: "processing" } }));
    setLive((prev) => clearSweep(prev));

    // Pin the map to this supplier for the length of the pass. Without it a
    // product outside the drawn page is assessed invisibly.
    if (filtersBeforeRef.current === null) filtersBeforeRef.current = mapFilters;
    setMapFilters({
      q: "", categories: [], offset: 0,
      suppliers: [batch.supplier], limit: SWEEP_LIMIT,
    });
    setSelected(null);

    /* Two halves, running together: the stream fills the inbox as fast as the
       server answers, and the walk below empties it one product per beat.
       Decoupling them is what makes the narration independent of how the
       frames happened to arrive. */
    const inbox: BatchProduct[] = [];
    let arrived = false;
    let previous: { id: string; verdict: string } | null = null;

    const narrate = (async () => {
      for (;;) {
        const next = inbox.shift();
        if (!next) {
          if (arrived) break;
          await wait(40);
          continue;
        }
        setWalk({ batch: batch.batch_id, ordinal: next.ordinal,
                  total: next.total, name: next.name });
        // The path the map lights, resolved server-side: the variant, its
        // product and its supplier. The one before it keeps a
        // verdict-coloured ring, which is what stops a finished pass
        // reverting the map to how it looked before.
        setLive((prev) => withWorking(prev, next.entities,
                                      previous ?? undefined));
        previous = { id: next.entity_id, verdict: next.verdict };
        await wait(PACE_MS);
      }
      // Off the end of the bundle: nothing is being worked, and what the pass
      // decided stays on the map.
      setLive((prev) => withWorking(prev, [], previous ?? undefined));
    })();

    try {
      await streamBatchAssess(batch.batch_id, (event) => {
        if (event.kind === "batch_started") {
          setWalk({ batch: batch.batch_id, ordinal: 0,
                    total: event.total, name: "" });
        } else if (event.kind === "product") {
          inbox.push(event);
        } else if (event.kind === "batch_finished") {
          setProgress((p) => ({
            ...p,
            [batch.batch_id]: { state: "done", totals: event.totals },
          }));
        } else if (event.kind === "error") {
          throw new Error(event.detail);
        }
      });
      arrived = true;
      await narrate;
    } catch (e) {
      arrived = true;
      await narrate;
      setProgress((p) => ({
        ...p,
        [batch.batch_id]: { state: "failed", error: String(e) },
      }));
      throw e;
    } finally {
      setWalk(null);
    }
  }, [mapFilters]);

  const giveTheMapBack = useCallback(() => {
    if (filtersBeforeRef.current) setMapFilters(filtersBeforeRef.current);
    filtersBeforeRef.current = null;
  }, []);

  /** Walk the queue. One bundle at a time, in the order they were sent. */
  const processQueue = useCallback(async (only?: BatchRow) => {
    const work = only ? [only] : pending;
    if (work.length === 0) return;
    stopRef.current = false;
    setSweeping("queue");
    setSwept({ done: 0, total: work.length });
    let done = 0;
    try {
      for (const batch of work) {
        if (stopRef.current) break;
        await processBatch(batch);
        done += 1;
        setSwept({ done, total: work.length });
      }
      toast.push({
        tone: "ok",
        title: stopRef.current
          ? `Stopped after ${done} of ${work.length}`
          : `${done} ${done === 1 ? "bundle" : "bundles"} processed`,
        detail: "Open one in Supplier Intake for the findings behind the tally.",
      });
    } catch (e) {
      toast.error("The onboarding pass failed", String(e));
    } finally {
      setSweeping(null);
      giveTheMapBack();
    }
  }, [pending, processBatch, giveTheMapBack, toast]);

  /* Work every open case.
   *
   * One run per case, awaited, each stopping at its own approval gate - which
   * is a success for the sweep rather than a reason to stop, because that is
   * the normal terminal state and the queue of decisions is the point.
   *
   * The list is re-read between runs, and that is the half worth explaining. A
   * run reads every unexamined document, so it can *open* cases that did not
   * exist when the sweep started - `scope_case` reports them and expects a
   * human to come back and start a second run. Picking them up here is what
   * closes that gap. `visited` and the ceiling are what stop it being a loop.
   */
  const sweepCases = useCallback(async () => {
    const first = cases ?? (await readCases()) ?? [];
    if (first.length === 0) return;
    stopRef.current = false;
    setSweeping("cases");

    const visited = new Set<string>();
    let queueOfCases = first.map((c) => c.case_id);
    let done = 0;
    let failed = 0;
    setSwept({ done: 0, total: queueOfCases.length });

    try {
      while (queueOfCases.length > 0 && done + failed < MAX_SWEEP_RUNS) {
        if (stopRef.current) break;
        const caseId = queueOfCases.shift() as string;
        if (visited.has(caseId)) continue;
        visited.add(caseId);

        // One case failing is not the queue failing. `startRun` has already
        // said so in a toast of its own; the sweep carries on to the cases
        // that can still be worked, and counts what it could not.
        try {
          await onStartRun(caseId, { navigate: false });
          done += 1;
        } catch {
          failed += 1;
        }

        const now = await readCases();
        const discovered = (now ?? [])
          .map((c) => c.case_id)
          .filter((id) => !visited.has(id) && !queueOfCases.includes(id));
        queueOfCases = [...queueOfCases, ...discovered];
        setSwept({ done: done + failed, total: done + failed + queueOfCases.length });
      }
      toast.push({
        tone: failed ? "warn" : "ok",
        title: stopRef.current
          ? `Stopped after ${done} ${done === 1 ? "case" : "cases"}`
          : `${done} ${done === 1 ? "case" : "cases"} worked`,
        detail: failed
          ? `${failed} could not be worked. Anything that reached its approval `
            + "gate is in Review & Audit."
          : "Anything that reached its approval gate is in Review & Audit.",
      });
    } finally {
      setSweeping(null);
      setSwept(null);
      void readCases();
    }
  }, [cases, readCases, onStartRun, toast]);

  const stopSweep = useCallback(() => { stopRef.current = true; }, []);

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
  const openCount = cases?.length ?? 0;

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

  const sweepingCases = sweeping === "cases";
  const anySweep = sweeping !== null;

  return (
    <>
      <PageHeader
        section="fabric"
        actions={
          <div className="flex items-center gap-2">
            {sweepingCases && swept ? (
              <>
                <span className="hidden text-right text-xs leading-tight text-faint lg:block">
                  working case {swept.done + 1} of {swept.total}
                  <br />
                  <span className="text-muted">
                    each one stops at its own approval gate
                  </span>
                </span>
                <Button
                  tone="danger"
                  size="md"
                  onClick={stopSweep}
                  icon={<IconPause size={15} />}
                >
                  Stop after this case
                </Button>
              </>
            ) : (
              <>
                {worstOpen && (
                  <span className="hidden text-right text-xs leading-tight text-faint lg:block">
                    worst open case
                    <br />
                    <span className="text-muted">{worstOpen.title}</span>
                  </span>
                )}
                <Tooltip
                  content={
                    openCount
                      ? `Works all ${openCount} open ${openCount === 1 ? "case" : "cases"} in turn, worst first, each as its own run stopping at its own approval gate. Cases a run opens by reading a document are picked up too. Pick a single row from the rail to work just that one.`
                      : "Nothing is open. The loop would find no case to work — advance the replay, or send something through a portal."
                  }
                >
                  <span>
                    <Button
                      tone="primary"
                      size="md"
                      onClick={() => (openCount ? void sweepCases() : onStartRun())}
                      loading={busy || anySweep}
                      icon={<IconSpark size={15} />}
                    >
                      {busy || anySweep
                        ? "Working…"
                        : openCount
                        ? `Work every open case (${openCount})`
                        : "Run the correction loop"}
                    </Button>
                  </span>
                </Tooltip>
              </>
            )}
          </div>
        }
      />

      <div className="flex min-h-0 flex-1 gap-3">
        <IncomingRail
          open={incomingOpen}
          onToggle={toggleIncoming}
          count={pending.length}
          working={sweeping === "queue"}
        >
          <IncomingQueue
            queue={queue}
            progress={progress}
            pending={pending}
            walk={walk}
            sweeping={sweeping}
            swept={swept}
            onProcessAll={() => void processQueue()}
            onProcessOne={(b) => void processQueue(b)}
            onStop={stopSweep}
            onOpenBatch={onOpenBatch}
          />

          <EventFeed
            events={events}
            catalog={catalog}
            busy={busy}
            onReplay={onReplay}
            onTrace={setSelected}
            selected={selected}
            maxHeight="46vh"
          />
        </IncomingRail>

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
                systems={showSystems}
                onToggleSystems={toggleSystems}
              />
              {/* The scroller the map's own min-width scrolls against. Both
                  axes: sideways below the width its labels survive, downwards
                  when a dense estate outgrows the section. */}
              <div className="min-h-0 flex-1 overflow-auto">
                <NetworkMap
                  catalog={mapCatalog}
                  affected={traced}
                  live={live}
                  selected={selected}
                  onSelect={setSelected}
                  showSystems={showSystems}
                />
              </div>
              <div className="shrink-0 border-t border-subtle px-3 py-2.5">
                <MapLegend live={live.pulses.size > 0} />
                <div className="mt-2 flex items-start gap-2 text-sm text-muted">
                  <IconTrace size={14} className="mt-0.5 shrink-0 text-accent-text" />
                  {walk ? (
                    <span>
                      Assessing <Code>{walk.name || "…"}</Code> — product{" "}
                      {walk.ordinal} of {walk.total} in this bundle. The ring
                      that stays behind is the verdict the pass reached.
                    </span>
                  ) : selected ? (
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
                      correction there would reach. Listings are drawn in full
                      where something has asked for them; elsewhere the count
                      rides on the variant.
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
          count={openCount}
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
                      busy={busy || anySweep}
                      working={sweepingCases && run?.values.case_id === c.case_id}
                      onWork={onStartRun}
                    />
                  ))}
                </div>
                <p className="border-t border-subtle px-3 py-2 text-xs leading-relaxed text-faint">
                  A case is one product — the unit the publish lock is taken on
                  and the unit a reviewer commits. A row works that product
                  alone; the button above works all {cases.length} of them in
                  turn, starting with <Code>{worstOpen?.case_id}</Code>.
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
                    onClick={() => (openCount ? void sweepCases() : onStartRun())}
                    loading={busy || anySweep}
                    icon={<IconSpark size={14} />}
                  >
                    {openCount
                      ? `Work every open case (${openCount})`
                      : "Run the correction loop"}
                  </Button>
                }
              >
                Advance the replay to the supplier correction, then work the
                cases — each run reads what the document says, works out which
                variant it applies to, traces every field and channel built on
                the old value, and stops for your approval.
              </EmptyState>
            )}
          </Panel>
        </IssuesRail>
      </div>
    </>
  );
}

/* --- incoming --------------------------------------------------------------- */

/** What is arriving, to the left of the graph it arrives into.
 *
 * The same collapse the issues rail has, mirrored, and open by default rather
 * than shut: this is the side of the screen a reader arrives at, and a queue
 * nobody can see is a queue nobody works.
 */
function IncomingRail({ open, onToggle, count, working, children }: {
  open: boolean;
  onToggle: () => void;
  count: number;
  working: boolean;
  children: React.ReactNode;
}) {
  const label = count
    ? `${count} ${count === 1 ? "bundle" : "bundles"} waiting`
    : "nothing waiting";

  return (
    <aside
      aria-label="Incoming"
      style={{ width: open ? "clamp(300px, 24vw, 380px)" : "40px" }}
      className={cn(
        "flex shrink-0 flex-col gap-2 overflow-hidden",
        "transition-[width] duration-[var(--dur-base)] ease-standard"
      )}
    >
      <Tooltip content={open ? "Hide what is arriving" : `Show what is arriving — ${label}`}>
        <Button
          size="xs"
          tone="ghost"
          aria-expanded={open}
          onClick={onToggle}
          icon={open ? <IconChevronLeft size={14} /> : <IconChevronRight size={14} />}
          className={cn("shrink-0", open ? "self-start" : "self-center")}
        >
          {open ? "hide" : undefined}
        </Button>
      </Tooltip>

      {open ? (
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
          {children}
        </div>
      ) : (
        <button
          type="button"
          onClick={onToggle}
          aria-label={`Show what is arriving — ${label}`}
          className={cn(
            "flex min-h-0 flex-1 flex-col items-center gap-2 rounded-md py-2",
            "border border-subtle bg-raised transition-colors hover:bg-hover"
          )}
        >
          {working ? (
            <Spinner size={12} />
          ) : count > 0 ? (
            <Badge tone="accent">{count}</Badge>
          ) : null}
          <span
            className="text-2xs uppercase tracking-caps text-faint"
            style={{ writingMode: "vertical-rl" }}
          >
            incoming
          </span>
        </button>
      )}
    </aside>
  );
}

/** The bundles suppliers have sent, and the pass that walks them.
 *
 * One row per bundle, newest first, in the order `/api/intake/batches`
 * returned - which is the order they were sent, because a queue that reordered
 * arrivals would be inventing a priority nobody set.
 */
function IncomingQueue({
  queue, progress, pending, walk, sweeping, swept,
  onProcessAll, onProcessOne, onStop, onOpenBatch,
}: {
  queue: BatchRow[] | null;
  progress: Record<string, QueueState>;
  pending: BatchRow[];
  walk: { batch: string; ordinal: number; total: number; name: string } | null;
  sweeping: "queue" | "cases" | null;
  swept: { done: number; total: number } | null;
  onProcessAll: () => void;
  onProcessOne: (batch: BatchRow) => void;
  onStop: () => void;
  onOpenBatch?: (batchId: string) => void;
}) {
  const running = sweeping === "queue";

  return (
    <Panel
      title="Incoming"
      icon={<IconIntake size={14} />}
      flush
      tone={pending.length ? "accent" : undefined}
      subtitle={
        queue === null
          ? "reading…"
          : queue.length
          ? `${pending.length} of ${queue.length} not yet processed`
          : undefined
      }
      actions={
        running ? (
          <Button size="xs" tone="danger" onClick={onStop}
                  icon={<IconPause size={12} />}>
            stop
          </Button>
        ) : (
          <Button
            size="xs"
            tone="primary"
            disabled={pending.length === 0 || sweeping !== null}
            onClick={onProcessAll}
            icon={<IconSpark size={12} />}
          >
            process {pending.length || ""}
          </Button>
        )
      }
    >
      {queue === null ? (
        <div className="p-3">
          <Skeleton className="h-20 w-full" rounded="md" />
        </div>
      ) : queue.length === 0 ? (
        <EmptyState compact art={<ArtQuietFeed />} title="Nothing has been sent">
          A supplier feed sent through the Vendor Portal lands here the moment
          it arrives, and waits until somebody processes it. Nothing is
          assessed on arrival — that is the queue's whole purpose.
        </EmptyState>
      ) : (
        <>
          {running && swept && (
            <div className="border-b border-subtle px-3 py-2">
              <div className="mb-1.5 flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5 text-accent-text">
                  <Spinner size={11} />
                  {walk
                    ? `${walk.name || "…"} — ${walk.ordinal} of ${walk.total}`
                    : "starting…"}
                </span>
                <span className="font-mono text-2xs text-faint tabular-nums">
                  bundle {swept.done + 1}/{swept.total}
                </span>
              </div>
              <ProgressBar
                value={walk && walk.total
                  ? (walk.ordinal / walk.total) * 100 : 0}
                tone="accent"
                ariaLabel="Products assessed in this bundle"
              />
            </div>
          )}

          <div className="sc-stagger max-h-[38vh] overflow-y-auto">
            {queue.map((batch, i) => (
              <QueueRow
                key={batch.batch_id}
                batch={batch}
                index={i}
                state={progress[batch.batch_id]}
                walking={walk?.batch === batch.batch_id ? walk : null}
                disabled={sweeping !== null}
                onProcess={() => onProcessOne(batch)}
                onOpen={onOpenBatch}
              />
            ))}
          </div>

          <p className="border-t border-subtle px-3 py-2 text-xs leading-relaxed text-faint">
            Processing walks a bundle one product at a time and lights each on
            the map as it is assessed, leaving a verdict-coloured ring behind
            it. It answers "is this record fit to sell?" — the correction loop
            above answers a different question about products already live.
          </p>
        </>
      )}
    </Panel>
  );
}

/** One bundle waiting, being walked, or walked. */
function QueueRow({ batch, index, state, walking, disabled, onProcess, onOpen }: {
  batch: BatchRow;
  index: number;
  state?: QueueState;
  walking: { ordinal: number; total: number; name: string } | null;
  disabled: boolean;
  onProcess: () => void;
  onOpen?: (batchId: string) => void;
}) {
  const status = state?.state ?? "queued";
  const totals = state?.totals;
  const n = batch.entities.length;

  return (
    <div
      style={{ ["--i" as string]: index }}
      className={cn(
        "flex flex-col gap-1.5 border-b border-subtle px-3 py-2",
        walking && "bg-accent-soft"
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        {status === "processing" ? (
          <Badge tone="accent" dot>working</Badge>
        ) : status === "done" ? (
          <Badge tone="ok">processed</Badge>
        ) : status === "failed" ? (
          <Badge tone="danger">failed</Badge>
        ) : (
          <Badge tone="neutral">queued</Badge>
        )}
        <span className="text-sm font-medium text-fg">{batch.supplier}</span>
        <span className="text-xs text-muted">
          {n} {n === 1 ? "row" : "rows"}
        </span>
        <Tooltip content={`Real time this platform received the bundle. On the replay clock the submission is stamped ${fmt.stamp(batch.submitted_at)}, which is the instant its facts were recorded at.`}>
          <span className="ml-auto font-mono text-2xs text-faint">
            {fmt.stamp(batch.wall_at)}
          </span>
        </Tooltip>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <Code>{batch.batch_id}</Code>
        <Tooltip content="The system the bundle arrived through">
          <span className="font-mono text-2xs text-faint">{batch.system}</span>
        </Tooltip>
        {batch.proposals.length > 0 && (
          <Tooltip content="Lines this bundle proposed that the catalog does not have yet. They are not assessed products — a reviewer accepts them first.">
            <span>
              <Badge tone="neutral">
                {batch.proposals.length} proposed
              </Badge>
            </span>
          </Tooltip>
        )}
      </div>

      {walking && (
        <p className="text-xs text-accent-text">
          assessing {walking.name || "…"} — {walking.ordinal} of {walking.total}
        </p>
      )}

      {/* What the pass found, in the vocabulary `verdict.ts` allows. Counted
          from the totals the server returned, never recomputed here. */}
      {totals && (
        <div className="flex flex-wrap items-center gap-1">
          <VerdictCount n={totals.cleared} verdict="READY_TO_LAUNCH"
                        complete={totals.checks_complete} />
          <VerdictCount n={totals.returned} verdict="RETURN_TO_SOURCE"
                        complete={totals.checks_complete} />
          <VerdictCount n={totals.blocked} verdict="BLOCKED"
                        complete={totals.checks_complete} />
          {totals.stopped > 0 && (
            <Tooltip content="Never reached onboarding — a regulation or this organisation's own policy refused it. Overlaps the counts beside it by construction.">
              <span><Badge tone="danger">{totals.stopped} stopped</Badge></span>
            </Tooltip>
          )}
        </div>
      )}

      {state?.error && (
        <p className="text-xs leading-relaxed text-danger-text">{state.error}</p>
      )}

      <div className="flex items-center gap-1.5">
        <Button size="xs" disabled={disabled} onClick={onProcess}>
          {status === "queued" ? "process this bundle" : "process again"}
        </Button>
        {onOpen && (
          <Button size="xs" tone="ghost" onClick={() => onOpen(batch.batch_id)}>
            open the report →
          </Button>
        )}
      </div>
    </div>
  );
}

/** One verdict count, said the way `verdict.ts` permits. A batch assessed
 *  without a model has been through seven checks of eleven, and this is the
 *  one place forty products at once could launder that into "ready". */
function VerdictCount({ n, verdict, complete }: {
  n: number; verdict: string; complete: boolean;
}) {
  if (!n) return null;
  const badge = verdictBadge(verdict, complete);
  return (
    <Badge tone={badge.tone}>
      {n} {badge.label}
    </Badge>
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
function CaseRow({ c, index, vocab, channels, busy, working, onWork }: {
  c: OpenCase;
  index: number;
  vocab: Vocab;
  channels: ChannelReach[];
  busy: boolean;
  /** The sweep is on this case now. */
  working?: boolean;
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
        working && "bg-accent-soft",
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
          {working ? "working now" : "work this case →"}
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
