/* Live impact tracking for the catalog map.
 *
 * The event feed already proves events are arriving, but a scrolling list of
 * text does not show a reviewer *where* in the catalog something is happening.
 * This resolves each event to the catalog nodes it touches - supplier, product,
 * variant, channel - and keeps a decaying highlight, so the map flickers with
 * routine supplier traffic and holds a steady glow on whatever a correction has
 * actually put at risk.
 *
 * Two distinct kinds of highlight, because they mean different things:
 *
 *   pulse   - an event just touched this node. Decays over a few seconds.
 *             This is traffic, not damage.
 *   impact  - this node is inside the blast radius of a correction that is in
 *             force. Persists until the correction is resolved.
 *   working - the onboarding pass is assessing this product *now*. Steady
 *             while it lasts and gone the moment it moves on.
 *
 * Conflating any two of them would make a routine price feed look like a
 * recall. `working` is a third field rather than a borrowed pulse for the same
 * reason the first two are separate: a pulse decays, and "we are looking at
 * this one" is not a statement that fades - it is either true or the pass has
 * moved on. A decaying version would leave a trail of half-lit products that
 * reads as "these are all being worked on", which is the one thing a
 * sequential pass exists to disprove.
 */

import type { AffectedScope, CatalogState, EventType, SCEvent } from "./api";

export const PULSE_MS = 5000;

export interface LiveImpact {
  /** catalog node id -> timestamp of the most recent event touching it */
  pulses: Map<string, number>;
  /** catalog node ids inside a live correction's blast radius */
  impacted: Set<string>;
  /** listing ids that cannot publish as they stand - the map's edges */
  blockedListings: Set<string>;
  /** the nodes on the path of the product being assessed right now */
  working: Set<string>;
  /** entity id -> the verdict the pass reached, for the ones already done */
  settled: Map<string, string>;
}

export const emptyImpact = (): LiveImpact => ({
  pulses: new Map(), impacted: new Set(), blockedListings: new Set(),
  working: new Set(), settled: new Map(),
});

/** Move the pass on to one product, or off the end of the batch.
 *
 *  The previous product's verdict is kept in `settled`, so a finished sweep
 *  leaves the map showing what it decided rather than reverting to how it
 *  looked before. Called with no ids to clear the working set at the end. */
export function withWorking(prev: LiveImpact, ids: string[],
                            settled?: { id: string; verdict: string }
                           ): LiveImpact {
  const next: LiveImpact = {
    ...prev,
    working: new Set(ids),
    settled: settled ? new Map(prev.settled) : prev.settled,
  };
  if (settled) next.settled.set(settled.id, settled.verdict);
  return next;
}

/** Forget a previous sweep, when a new one starts or the batch is cleared. */
export function clearSweep(prev: LiveImpact): LiveImpact {
  return { ...prev, working: new Set(), settled: new Map() };
}

/* --- catalog index -------------------------------------------------------- */

interface CatalogIndex {
  nodes: Set<string>;
  /** listing id -> the two nodes it joins */
  listings: Map<string, { variant: string; channel: string }>;
  /** variant id -> its product */
  productOf: Map<string, string>;
  /** product id -> its supplier */
  supplierOf: Map<string, string>;
}

/* Built once per CatalogState object. The state is replaced wholesale on every
 * poll, so identity is a sound cache key and a stale index is impossible. */
const INDEX = new WeakMap<CatalogState, CatalogIndex>();

function indexOf(catalog: CatalogState): CatalogIndex {
  const hit = INDEX.get(catalog);
  if (hit) return hit;
  const ix: CatalogIndex = {
    nodes: new Set(catalog.nodes.map((n) => n.id)),
    listings: new Map(
      catalog.listings.map((l) =>
        [l.id, { variant: l.variant_id, channel: l.channel_id }] as const
      )
    ),
    productOf: new Map(catalog.variants.map((v) => [v.id, v.product_id] as const)),
    supplierOf: new Map(catalog.products.map((p) => [p.id, p.supplier] as const)),
  };
  INDEX.set(catalog, ix);
  return ix;
}

/* --- events --------------------------------------------------------------- */

/** Payload keys worth reading, per event type.
 *
 * Deliberately generous: the tape is generated alongside this file and a
 * correction notice can name its subject as a product, a variant, a listing or
 * nothing at all. Anything that does not resolve to a node in the catalog is
 * dropped, so an unknown key costs nothing and a missed one costs a dark map.
 */
const EVENT_KEYS: Record<EventType, string[]> = {
  SUPPLIER_FEED: [
    "supplier", "supplier_id", "product", "product_id", "variant", "variant_id",
    "entity", "entity_id", "entities", "attribute_paths",
  ],
  SPEC_DOC: [
    "supplier", "supplier_id", "product", "product_id", "variant", "variant_id",
    "entity", "entity_id", "entities", "attribute_paths",
  ],
  CHANNEL_STATUS: [
    "channel", "channel_id", "listing", "listing_id", "listings",
    "product", "product_id", "variant", "variant_id", "entity", "entity_id",
    "entities",
  ],
  CATALOG_UPDATE: [
    "entity", "entity_id", "entities", "variant", "variant_id",
    "product", "product_id", "listing", "listing_id", "listings",
    "channel", "channel_id", "attribute_paths",
  ],
  PUBLISH_TELEMETRY: [
    "channel", "channel_id", "listing", "listing_id", "listings",
  ],
  COMMS: [
    "supplier", "supplier_id", "product", "product_id", "variant", "variant_id",
    "entity", "entity_id", "entities",
  ],
};

/** Publish telemetry is the one type that can never justify a persistent
 *  highlight. A feed row saying a listing went out is traffic; it is evidence
 *  that the pipeline is alive, not that anything is wrong with it. */
export const impliesImpact = (type: EventType): boolean =>
  type !== "PUBLISH_TELEMETRY";

/** Qualified references arrive as "VAR-01B:specs.power_w"; the entity is the
 *  half the map can draw. */
const entityOf = (ref: string) =>
  ref.includes(":") ? ref.slice(0, ref.indexOf(":")) : ref;

function collect(payload: Record<string, unknown>, keys: string[]): string[] {
  const out: string[] = [];
  for (const key of keys) {
    const v = payload[key];
    if (typeof v === "string") out.push(v);
    else if (Array.isArray(v)) {
      for (const item of v) if (typeof item === "string") out.push(item);
    }
  }
  return out;
}

/** Catalog nodes an event touches, as ids the map can highlight.
 *
 * A listing is an edge rather than a node, so it lights both of its endpoints.
 * A variant also lights its product and that product's supplier: the four tiers
 * are drawn left to right, and a correction that reaches a variant has come
 * down that path, so lighting the path is what makes the map legible as the
 * tape plays. That lifting is for *traffic* only - the persistent blast radius
 * below takes products and channels from the API rather than inferring them.
 */
export function entitiesFor(event: SCEvent, catalog: CatalogState): string[] {
  const ix = indexOf(catalog);
  const payload = (event.payload ?? {}) as Record<string, unknown>;
  const out: string[] = [];

  const lift = (id: string) => {
    if (!ix.nodes.has(id)) return;
    out.push(id);
    const product = ix.productOf.get(id);
    if (product && ix.nodes.has(product)) {
      out.push(product);
      const supplier = ix.supplierOf.get(product);
      if (supplier && ix.nodes.has(supplier)) out.push(supplier);
      return;
    }
    const supplier = ix.supplierOf.get(id);
    if (supplier && ix.nodes.has(supplier)) out.push(supplier);
  };

  const resolve = (raw: string) => {
    const id = entityOf(raw);
    if (!id) return;
    const listing = ix.listings.get(id);
    if (listing) {
      lift(listing.variant);
      lift(listing.channel);
      return;
    }
    lift(id);
  };

  // `source` is an id often enough to be worth trying - a CHANNEL_STATUS is
  // sourced from the channel that rejected the listing.
  for (const raw of collect(payload, EVENT_KEYS[event.type] ?? [])) resolve(raw);
  if (event.source) resolve(event.source);

  return Array.from(new Set(out));
}

/** Fold new events into the highlight state. */
export function applyEvents(
  previous: LiveImpact, events: SCEvent[], catalog: CatalogState
): LiveImpact {
  const pulses = new Map(previous.pulses);
  const now = Date.now();
  for (const event of events) {
    for (const id of entitiesFor(event, catalog)) pulses.set(id, now);
  }
  return { ...previous, pulses };
}

/** Drop pulses that have decayed, so the map settles when the feed is quiet. */
export function prunePulses(impact: LiveImpact): LiveImpact {
  const cutoff = Date.now() - PULSE_MS;
  let changed = false;
  const pulses = new Map<string, number>();
  for (const [id, at] of impact.pulses) {
    if (at >= cutoff) pulses.set(id, at);
    else changed = true;
  }
  return changed ? { ...impact, pulses } : impact;
}

/** 1 at the moment of the event, fading to 0 over PULSE_MS. */
export function pulseStrength(impact: LiveImpact, id: string): number {
  const at = impact.pulses.get(id);
  if (at === undefined) return 0;
  return Math.max(0, 1 - (Date.now() - at) / PULSE_MS);
}

/** Persistent blast radius, from the corrections currently in force.
 *
 * Every id here is one the API named: the run's affected scope, the correction
 * signals' entities, and the listings the catalog itself reports as no longer
 * publishable. Nothing is inferred - the whole point of the deterministic
 * propagation is that the map shows the same radius the validator counted.
 */
export function impactFrom(
  catalog: CatalogState,
  runAffected: Partial<AffectedScope> | undefined,
  signalEntities: string[]
): { impacted: Set<string>; blockedListings: Set<string> } {
  const ix = indexOf(catalog);
  const impacted = new Set<string>();
  const blockedListings = new Set<string>();

  const add = (raw: string) => {
    const id = entityOf(raw);
    if (id && ix.nodes.has(id)) impacted.add(id);
  };

  for (const id of signalEntities) add(id);
  for (const id of runAffected?.products ?? []) add(id);
  for (const id of runAffected?.variants ?? []) add(id);
  for (const id of runAffected?.channels ?? []) add(id);
  // Qualified attribute references carry the entity they were measured on.
  for (const ref of runAffected?.attributes ?? []) add(ref);

  // A listing in the affected scope implicates the two nodes it joins, the
  // same way a correction to a variant reaches the channel that published it.
  const touch = (listingId: string) => {
    const listing = ix.listings.get(listingId);
    if (!listing) return;
    add(listing.variant);
    add(listing.channel);
  };
  for (const id of runAffected?.listings ?? []) touch(id);

  // Anything the catalog no longer reports as publishable. `correction.listings`
  // is the authority here: it is the status in force at `as_of`, which is not
  // necessarily the status baked into the listing row.
  for (const listing of catalog.listings) {
    if (listing.status === "WITHHELD" || listing.status === "REJECTED") {
      blockedListings.add(listing.id);
    }
  }
  for (const [id, status] of Object.entries(catalog.correction?.listings ?? {})) {
    if (status === "WITHHELD" || status === "REJECTED" || status === "BLOCKED") {
      blockedListings.add(id);
    } else {
      blockedListings.delete(id);
    }
  }
  for (const id of blockedListings) touch(id);

  return { impacted, blockedListings };
}
