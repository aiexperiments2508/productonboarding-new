import { useMemo, useState } from "react";
import type {
  CatalogNodeKind, CatalogState, Listing, ListingStatus,
} from "../api";
import type { LiveImpact } from "../liveImpact";
import { pulseStrength } from "../liveImpact";
import { cn } from "../ui";

/* The catalog as hand-drawn SVG.
 *
 * Four tiers, and they are the shape of the whole product: a supplier document
 * defines a product, a product has variants, and a variant is published to a
 * channel through a listing. A correction enters at the left and everything it
 * can reach is to the right of it, which is why the picture is worth drawing at
 * all.
 *
 *   Sources -> Products -> Variants -> Channels
 *
 * The generator emits x/y on every node (normalised 0-1 within the frame), so
 * there is nothing for a layout engine to solve. Fixed coordinates also mean
 * the blast radius is a class toggle rather than a re-layout, and the diagram
 * does not move between renders while a reviewer is reading it.
 *
 * The edges are not all the same kind of thing, and are not drawn as if they
 * were:
 *
 *   supplies / contains   membership. Who owns what. Static thin lines - the
 *                         catalog's skeleton, not a pipe.
 *   lists_on              one Listing: the pipe content actually publishes
 *                         through. These carry flow, and they carry state.
 *
 * What the motion is for, since motion on a diagram is usually decoration:
 *
 *   flow           this listing is publishing. Speed is scaled by the channel's
 *                  freeze window, so the print catalogue visibly lags the web.
 *   gate           the listing is WITHHELD. The flow stops dead at a bar across
 *                  the line: someone chose to hold this, it is not broken.
 *   break          the listing is REJECTED. The line itself is broken - the
 *                  channel bounced the feed and nothing is going through.
 *   pulse + tracer an event just landed here. A ring at the node, and a dot
 *                  that runs the listing the event travelled.
 *   sweep          a one-shot ripple when a reviewer traces a node, showing the
 *                  blast radius propagating rather than simply appearing.
 *   breathe        inside the blast radius, and staying there.
 *
 * Every one of those maps to something in the data. Nothing here animates
 * because motion is nice.
 */

const W = 1000;

/* Height is derived from the busiest tier, not fixed.
 *
 * It used to be a constant 460, with each tier spread evenly across whatever
 * room that left. That is exactly right for a catalog of six products and
 * silently wrong for one of a hundred and fifty: the nodes do not overlap
 * gracefully, they just stack until the labels are mud, and nothing on screen
 * says the picture has stopped being readable.
 *
 * So the frame grows with what is in it, up to a bound. Past that bound the
 * tier is truncated *visibly* - see MAX_ROWS - because a map that quietly drew
 * the first thirty of a hundred and fifty would be read as an estate of
 * thirty. */
const MIN_H = 360;
const MAX_H = 1400;

/** Vertical room one node needs: the body, its label above it, and air. */
const ROW_H = 34;

/** The most members any one tier will draw. Beyond this the tier shows a
 *  "+N more" marker and the filters are how you see the rest - which is the
 *  honest answer, because the alternative is a column of overlapping text
 *  that looks like a rendering fault rather than a full estate. */
const MAX_ROWS = Math.floor((MAX_H - 68) / ROW_H);
// Left padding carries the widest caption in the leftmost column. That used to
// be a six-character supplier code; it is now a system name, so the column
// needs room a short id never did.
const PAD = { top: 42, bottom: 26, left: 120, right: 92 };

const NODE_R = 11;
const GLYPH = 15;

/* The tiers, left to right. Order here *is* the layout: x comes from a tier's
   index and y from a node's place within that tier's live membership.
   Positions used to be written by the generator and read off each node. That
   stopped being tenable when the leftmost tier became one whose membership is
   only known at runtime - a coordinate written at generation time cannot
   describe a system that connected a minute ago. */
const TIERS: { kind: CatalogNodeKind; label: string }[] = [
  { kind: "SYSTEM", label: "Systems" },
  { kind: "SUPPLIER", label: "Sources" },
  { kind: "PRODUCT", label: "Products" },
  { kind: "VARIANT", label: "Variants" },
  { kind: "CHANNEL", label: "Channels" },
];

const KIND_NOUN: Record<CatalogNodeKind, string> = {
  SYSTEM: "System",
  SUPPLIER: "Source",
  PRODUCT: "Product",
  VARIANT: "Variant",
  CHANNEL: "Channel",
};

/* --- listing status ------------------------------------------------------- */

const STATUSES: ListingStatus[] = ["LIVE", "PREPARED", "WITHHELD", "REJECTED"];

const asStatus = (v: unknown): ListingStatus | undefined =>
  typeof v === "string" && (STATUSES as string[]).includes(v)
    ? (v as ListingStatus)
    : undefined;

/** Listing id -> the status in force at the catalog's instant.
 *
 * `correction.listings` is the authority, not the status baked into the listing
 * row: the row is the baseline, the overlay is what is true now. Exported
 * because the map and the floor above it must not disagree about which channels
 * are stopped.
 */
export function listingStatusMap(catalog: CatalogState): Map<string, ListingStatus> {
  const overlay = catalog.correction?.listings ?? {};
  const out = new Map<string, ListingStatus>();
  for (const listing of catalog.listings) {
    out.set(listing.id, asStatus(overlay[listing.id]) ?? listing.status);
  }
  return out;
}

/* --- placement ------------------------------------------------------------ */

interface Placed {
  id: string;
  kind: CatalogNodeKind;
  name: string;
  x: number;
  y: number;
  regulated: boolean;
  single: boolean;
  /** One line of context for the hover card. */
  detail: string;
  /** Systems only: the connection has stopped answering. */
  degraded?: boolean;
  /** False when the rows are too tight for text to be legible. */
  showLabel?: boolean;
}

interface Edge {
  key: string;
  relation: "feeds" | "supplies" | "contains" | "lists_on";
  a: Placed;
  b: Placed;
  listing?: Listing;
  status?: ListingStatus;
  /** Days of frozen content on the destination channel. Drives flow speed. */
  freeze: number;
}

/** Names run long. The label is a display trim only - the id beside it is
 *  never trimmed, because that is the half a reviewer searches by. */
const trim = (s: string, n = 24) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

export function NetworkMap({ catalog, affected, selected, onSelect, live }: {
  catalog: CatalogState;
  /** The blast radius: catalog nodes, and the listings that carry it. */
  affected?: { nodes: Set<string>; listings: Set<string> };
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  /** Decaying highlights driven by the live event stream. */
  live?: LiveImpact;
}) {
  const [hover, setHover] = useState<Placed | null>(null);

  const { placed, edges, tiers, H, overflow } = useMemo(() => {
    const innerW = W - PAD.left - PAD.right;

    const productById = new Map(catalog.products.map((p) => [p.id, p]));
    const variantById = new Map(catalog.variants.map((v) => [v.id, v]));
    const channelById = new Map(catalog.channels.map((c) => [c.id, c]));
    const nodeName = new Map(catalog.nodes.map((n) => [n.id, n.name]));

    const productsPerSupplier = new Map<string, number>();
    for (const p of catalog.products) {
      productsPerSupplier.set(p.supplier, (productsPerSupplier.get(p.supplier) ?? 0) + 1);
    }
    const listingsPerNode = new Map<string, number>();
    for (const l of catalog.listings) {
      listingsPerNode.set(l.variant_id, (listingsPerNode.get(l.variant_id) ?? 0) + 1);
      listingsPerNode.set(l.channel_id, (listingsPerNode.get(l.channel_id) ?? 0) + 1);
    }
    const count = (n: number, one: string, many = `${one}s`) =>
      `${n} ${n === 1 ? one : many}`;

    // How many sources each system has actually carried data for. Derived from
    // the edges the server sent rather than counted again here, so the hover
    // card and the lines cannot disagree.
    const suppliersPerSystem = new Map<string, number>();
    for (const e of catalog.edges ?? []) {
      if (e.relation === "feeds") {
        suppliersPerSystem.set(e.from, (suppliersPerSystem.get(e.from) ?? 0) + 1);
      }
    }

    const systemById = new Map(
      catalog.nodes.filter((n) => n.kind === "SYSTEM").map((n) => [n.id, n]));

    const detailOf = (id: string, kind: CatalogNodeKind): string => {
      switch (kind) {
        case "SYSTEM": {
          const sys = systemById.get(id);
          if (!sys) return "";
          const reach = count(suppliersPerSystem.get(id) ?? 0, "source");
          return sys.state === "connected"
            ? `${sys.transport ?? "http"} · ${count(sys.tools ?? 0, "tool")} · ${reach}`
            : `${sys.state ?? "unknown"} · ${reach}`;
        }
        case "SUPPLIER":
          return count(productsPerSupplier.get(id) ?? 0, "product");
        case "PRODUCT": {
          const p = productById.get(id);
          return p ? `${p.category} · ${nodeName.get(p.supplier) ?? p.supplier}` : "";
        }
        case "VARIANT": {
          const v = variantById.get(id);
          const of = v ? nodeName.get(v.product_id) ?? v.product_id : "";
          const role = v?.is_base ? "base model" : "variant";
          return `${role} of ${of} · ${count(listingsPerNode.get(id) ?? 0, "listing")}`;
        }
        case "CHANNEL": {
          const c = channelById.get(id);
          const freeze = c?.freeze_days
            ? ` · ${c.freeze_days}-day freeze window`
            : "";
          return `${count(listingsPerNode.get(id) ?? 0, "listing")}${freeze}`;
        }
      }
    };

    /* Position, derived.
     *
     * x is the tier's index; y spreads a tier's members evenly inside its
     * column with a margin at both ends, so the outermost boxes are not on the
     * edge. This is what the generator used to compute and write down; doing it
     * here is what lets a tier gain and lose members while the map is open.
     *
     * A tier nobody is in takes no space and draws no header. That matters for
     * the systems column specifically: before anything connects, the map should
     * look like the map it always was rather than like one with a gap. */
    const membership = new Map<CatalogNodeKind, string[]>();
    for (const n of catalog.nodes) {
      const list = membership.get(n.kind) ?? [];
      list.push(n.id);
      membership.set(n.kind, list);
    }
    const occupied = TIERS.filter((t) => (membership.get(t.kind) ?? []).length);
    const columnOf = new Map(occupied.map((t, i) => [t.kind, i]));
    const lastColumn = Math.max(occupied.length - 1, 1);

    // What each tier will actually draw, and what it had to leave out.
    const drawn = new Map<CatalogNodeKind, string[]>();
    const overflow = new Map<CatalogNodeKind, number>();
    for (const [kind, ids] of membership) {
      drawn.set(kind, ids.slice(0, MAX_ROWS));
      if (ids.length > MAX_ROWS) overflow.set(kind, ids.length - MAX_ROWS);
    }

    const busiest = Math.max(
      1, ...[...drawn.values()].map((ids) => ids.length));
    const H = Math.min(
      MAX_H, Math.max(MIN_H, PAD.top + PAD.bottom + busiest * ROW_H));
    const innerH = H - PAD.top - PAD.bottom;

    /* One pitch for every tier, rather than each tier spreading itself over
       the full height.
       Before, a tier of four and a tier of eight had different vertical
       spacings, so their connecting edges fanned and crossed for no reason
       anybody could read - the geometry was saying something about the data
       that was not true. A shared pitch makes the picture a grid: rows line up
       across columns, and a crossing edge means a real crossing. */
    const rowPitch = innerH / busiest;

    const placed: Placed[] = catalog.nodes.flatMap((n) => {
      const peers = drawn.get(n.kind) ?? [];
      const seat = peers.indexOf(n.id);
      if (seat < 0) return [];  // past the tier's cap, counted in `overflow`
      // Centred as a block, so a tier of three in a frame sized for twelve
      // sits in the middle rather than clinging to the top.
      const offset = (innerH - peers.length * rowPitch) / 2;
      return [{
        id: n.id,
        kind: n.kind,
        name: n.name,
        x: PAD.left + ((columnOf.get(n.kind) ?? 0) / lastColumn) * innerW,
        y: PAD.top + offset + (seat + 0.5) * rowPitch,
        regulated: n.regulated,
        single: n.single_source,
        detail: detailOf(n.id, n.kind),
        // Systems only. A connection that stopped answering greys its node and
        // keeps every edge it drew: what it delivered was true when it
        // delivered it, and a bitemporal store does not retract history
        // because a socket closed.
        degraded: n.kind === "SYSTEM" && n.state !== "connected",
        // Labels turn to mud long before nodes collide. Below this pitch the
        // hover card carries identity instead.
        showLabel: rowPitch >= 26,
      }];
    });

    const byId = new Map(placed.map((p) => [p.id, p]));

    const edges: Edge[] = [];
    // system -> supplier. Taken from the server rather than rebuilt: which
    // system fed which source is a fact about what has actually arrived, and
    // the client has no way to know it.
    for (const e of catalog.edges ?? []) {
      if (e.relation !== "feeds") continue;
      const a = byId.get(e.from);
      const b = byId.get(e.to);
      if (a && b) {
        edges.push({ key: `fed:${e.from}:${e.to}`, relation: "feeds", a, b,
                     freeze: 0 });
      }
    }
    // supplier -> product
    for (const p of catalog.products) {
      const a = byId.get(p.supplier);
      const b = byId.get(p.id);
      if (a && b) edges.push({ key: `sup:${p.id}`, relation: "supplies", a, b, freeze: 0 });
    }
    // product -> variant
    for (const v of catalog.variants) {
      const a = byId.get(v.product_id);
      const b = byId.get(v.id);
      if (a && b) edges.push({ key: `con:${v.id}`, relation: "contains", a, b, freeze: 0 });
    }
    // variant -> channel, one per listing
    const statuses = listingStatusMap(catalog);
    for (const listing of catalog.listings) {
      const a = byId.get(listing.variant_id);
      const b = byId.get(listing.channel_id);
      if (!a || !b) continue;
      edges.push({
        key: listing.id,
        relation: "lists_on",
        a,
        b,
        listing,
        status: statuses.get(listing.id),
        freeze: channelById.get(listing.channel_id)?.freeze_days ?? 0,
      });
    }

    // Tier headers sit over the column they name, derived from the nodes so a
    // regenerated catalog cannot leave the captions behind.
    // An empty tier draws no caption. Before anything connects, the systems
    // column should be absent rather than an empty heading over a gap.
    const tiers = TIERS.map((t) => {
      const xs = placed.filter((p) => p.kind === t.kind).map((p) => p.x);
      const x = xs.length ? xs.reduce((s, v) => s + v, 0) / xs.length : 0;
      return { ...t, x, n: xs.length };
    }).filter((t) => t.n > 0);

    return { placed, edges, tiers, H, overflow };
  }, [catalog]);

  const hitNodes = affected?.nodes ?? new Set<string>();
  const hitListings = affected?.listings ?? new Set<string>();

  return (
    <div className="relative">
      <svg
        className="block w-full bg-sunken"
        viewBox={`0 0 ${W} ${H}`}
        style={{ minHeight: Math.min(H, 520) }}
        role="img"
        aria-label="Product catalog, from supplier sources through to sales channels, with the blast radius of the correction highlighted"
      >
        <defs>
          {/* Node glyphs. Deliberately simpler than the toolbar icon set -
              these render at roughly 15px and interior detail turns to mud. */}
          <symbol id="g-SUPPLIER" viewBox="0 0 24 24">
            <path d="M4 8.6 12 4.6l8 4v10L12 22.6l-8-4z" />
            <path d="M4 8.6 12 12.6l8-4M12 12.6v10" />
          </symbol>
          <symbol id="g-PRODUCT" viewBox="0 0 24 24">
            <rect x="4.5" y="4" width="15" height="16" rx="2.4" />
            <path d="M4.5 9.5h15M9.6 4v5.5" />
          </symbol>
          <symbol id="g-VARIANT" viewBox="0 0 24 24">
            <rect x="3.4" y="8.6" width="11.4" height="11.4" rx="2.2" />
            <path d="M9.2 8.6V6.2a2 2 0 0 1 2-2h7.4a2 2 0 0 1 2 2v7.4a2 2 0 0 1-2 2h-2.4" />
          </symbol>
          <symbol id="g-CHANNEL" viewBox="0 0 24 24">
            <rect x="3.4" y="4.4" width="17.2" height="12" rx="2.2" />
            <path d="M8.6 20.4h6.8M12 16.4v4" />
          </symbol>

          {/* Glow for whatever is live right now. */}
          <filter id="map-glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="3.5" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {tiers.map((t) => (
          <text
            key={t.kind}
            x={t.x}
            y={22}
            textAnchor="middle"
            className="fill-faint font-mono text-[11px] uppercase tracking-caps"
          >
            {t.label}
            {/* Said in the caption rather than left implicit. A column that
                quietly drew the first forty of a hundred and fifty would be
                read as a column that has forty. */}
            {overflow.get(t.kind)
              ? ` +${overflow.get(t.kind)} not drawn`
              : ""}
          </text>
        ))}

        {/* --- membership: who owns what ------------------------------------ */}
        {edges.filter((e) => e.relation !== "lists_on").map((e) => {
          const isHit = hitNodes.has(e.a.id) && hitNodes.has(e.b.id);
          return (
            <path
              key={e.key}
              d={curve(e)}
              fill="none"
              strokeWidth={isHit ? 2 : 1.2}
              className={cn(
                "transition-[stroke,stroke-width] duration-[var(--dur-base)]",
                isHit ? "stroke-danger opacity-90" : "stroke-viz-edge opacity-70"
              )}
            >
              <title>
                {e.relation === "feeds"
                  ? `${e.a.name} has delivered data for ${e.b.name}`
                  : e.relation === "supplies"
                  ? `${e.a.name} supplies ${e.b.name}`
                  : `${e.b.name} is a variant of ${e.a.name}`}
              </title>
            </path>
          );
        })}

        {/* --- listings: the pipe content publishes through ------------------ */}
        {edges.filter((e) => e.relation === "lists_on").map((e) => {
          const listing = e.listing!;
          const held = e.status === "WITHHELD";
          const rejected = e.status === "REJECTED";
          const isHit = hitListings.has(listing.id);
          // Pulses are keyed by node, so an event travelled this listing only
          // when it lit both of its ends.
          const pulse = live
            ? Math.min(pulseStrength(live, e.a.id), pulseStrength(live, e.b.id))
            : 0;
          const d = curve(e);
          const [mx, my, angle] = midpoint(e);
          // A frozen channel is slower to turn a correction around, and the
          // line says so before anything is read.
          const speed = 1.5 + Math.min(e.freeze, 14) * 0.13;

          return (
            <g key={listing.id}>
              <path
                d={d}
                fill="none"
                strokeWidth={held || rejected || isHit ? 2.2 : 1.4}
                className={cn(
                  "transition-[stroke,stroke-width] duration-[var(--dur-base)]",
                  rejected
                    ? "stroke-danger opacity-95 [stroke-dasharray:3_3.5]"
                    : held
                    ? "stroke-warn opacity-95"
                    : isHit
                    ? "stroke-danger opacity-95"
                    : "stroke-viz-edge"
                )}
              />

              {/* Flow overlay. Absent entirely on a stopped listing - a held
                  channel that still appears to be publishing is the one thing
                  this diagram must never say. Hidden under reduced motion,
                  where a static dashed line would imply a break. */}
              {!held && !rejected && (
                <path
                  d={d}
                  fill="none"
                  strokeWidth={1.4}
                  strokeLinecap="round"
                  className={cn(
                    "sc-flow",
                    isHit ? "stroke-danger opacity-70" : "stroke-viz-flow opacity-30"
                  )}
                  style={{ animationDuration: `${speed}s` }}
                />
              )}

              {/* A bar across the line: stopped on purpose. */}
              {held && (
                <g transform={`rotate(${angle} ${mx} ${my})`}>
                  <circle cx={mx} cy={my} r={5.4} className="fill-sunken" />
                  <line
                    x1={mx}
                    y1={my - 5.4}
                    x2={mx}
                    y2={my + 5.4}
                    strokeWidth={2.6}
                    strokeLinecap="round"
                    className="stroke-warn"
                  />
                </g>
              )}

              {/* A break in the line: the channel bounced it. */}
              {rejected && (
                <g>
                  <circle cx={mx} cy={my} r={5.4} className="fill-sunken" />
                  <path
                    d={`M${mx - 3.4} ${my - 3.4}l6.8 6.8M${mx + 3.4} ${my - 3.4}l-6.8 6.8`}
                    strokeWidth={2}
                    strokeLinecap="round"
                    className="stroke-danger"
                  />
                </g>
              )}

              {/* Tracer: an event just travelled this listing. */}
              {pulse > 0 && !held && !rejected && (
                <circle r={3.4} className="fill-accent" filter="url(#map-glow)"
                        opacity={pulse}>
                  <animateMotion dur="1.1s" repeatCount="indefinite" path={d} />
                </circle>
              )}

              <title>
                {`${listing.id}  ${e.a.name} → ${e.b.name}`}
                {`\npublished ${listing.published_version} · ${statusWords(e.status)}`}
                {e.freeze ? `\n${e.freeze}-day freeze window before a print run` : ""}
                {isHit ? "\nIn the blast radius of the correction" : ""}
              </title>
            </g>
          );
        })}

        {/* --- nodes -------------------------------------------------------- */}
        {placed.map((n) => {
          const isHit = hitNodes.has(n.id);
          const isSelected = selected === n.id;
          const pulse = live ? pulseStrength(live, n.id) : 0;
          const isChannel = n.kind === "CHANNEL";
          const isWorking = live?.working.has(n.id) ?? false;
          const settled = live?.settled.get(n.id);

          return (
            <g key={n.id}>
              {/* One-shot ripple when this node becomes the trace root. Keyed
                  on the id so re-selecting the same node replays it. */}
              {isSelected && (
                <circle
                  key={`sweep-${n.id}`}
                  cx={n.x}
                  cy={n.y}
                  fill="none"
                  className="sc-sweep stroke-accent"
                  style={{ ["--sweep-r" as string]: "150" }}
                />
              )}

              {pulse > 0 && (
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={NODE_R + 3 + pulse * 10}
                  fill="none"
                  strokeWidth={1.6}
                  opacity={pulse * 0.75}
                  className="stroke-accent"
                />
              )}

              {/* The onboarding pass is on this product. A fixed radius, not a
                  decaying one: a pulse says something touched this and fades,
                  and this says the pass is here, which is true until it is
                  not. */}
              {isWorking && (
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={NODE_R + 7}
                  fill="none"
                  strokeWidth={2}
                  className="stroke-accent sc-breathe"
                />
              )}

              {/* Already decided. Thin, quiet, and coloured by the verdict, so
                  a finished sweep leaves the map showing what it found rather
                  than reverting to how it looked before. */}
              {!isWorking && settled && (
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={NODE_R + 4}
                  fill="none"
                  strokeWidth={1.4}
                  opacity={0.85}
                  className={verdictStroke(settled)}
                />
              )}

              {/* Body. The catalog's own things are rounded squares; channels
                  are circles - they are the outside world, and the shape says
                  so before the glyph is read. */}
              {isChannel ? (
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={NODE_R}
                  className={bodyClass(n, isHit, isSelected, isWorking)}
                />
              ) : (
                <rect
                  x={n.x - NODE_R}
                  y={n.y - NODE_R}
                  width={NODE_R * 2}
                  height={NODE_R * 2}
                  rx={3.5}
                  className={bodyClass(n, isHit, isSelected, isWorking)}
                />
              )}

              <use
                href={`#g-${n.kind}`}
                x={n.x - GLYPH / 2}
                y={n.y - GLYPH / 2}
                width={GLYPH}
                height={GLYPH}
                fill="none"
                strokeWidth={1.7}
                strokeLinecap="round"
                strokeLinejoin="round"
                className={cn(
                  "pointer-events-none transition-colors duration-[var(--dur-base)]",
                  isHit ? "stroke-danger" : isSelected ? "stroke-accent" : "stroke-muted"
                )}
                opacity={0.85}
              />

              {/* Id first, then the name. The id is what a reviewer searches
                  by; the name is what the correction is actually about.
                  Dropped entirely when the rows are too tight to read - three
                  overlapping labels say less than none, and the hover card
                  still names everything. */}
              {n.showLabel !== false && <text
                x={n.x}
                y={n.y - NODE_R - 6}
                textAnchor="middle"
                className={cn(
                  "pointer-events-none text-[10px]",
                  isHit
                    ? "fill-danger-text"
                    : isSelected
                    ? "fill-accent-text"
                    : "fill-muted"
                )}
              >
                {/* A system's identifier is its own name in kebab-case, so
                    printing both spells the same words twice and overruns the
                    column. Catalog ids are short codes a reviewer searches by,
                    and those keep the pair. */}
                {n.kind === "SYSTEM" ? (
                  <tspan className="font-medium">{trim(n.name)}</tspan>
                ) : (
                  <>
                    <tspan className="font-mono font-medium">{n.id}</tspan>
                    <tspan dx="4.5" opacity="0.72">{trim(n.name)}</tspan>
                  </>
                )}
              </text>}

              {/* Hit target. Larger than the body so a node this small stays
                  clickable, and it is the element that owns focus. */}
              <circle
                cx={n.x}
                cy={n.y}
                r={19}
                fill="transparent"
                className="cursor-pointer"
                tabIndex={0}
                role="button"
                aria-label={`${KIND_NOUN[n.kind]} ${n.name}, ${n.id}`}
                onClick={() => onSelect?.(isSelected ? null : n.id)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelect?.(isSelected ? null : n.id);
                  }
                }}
                onMouseEnter={() => setHover(n)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(n)}
                onBlur={() => setHover(null)}
              >
                {/* Kept as the accessible name for assistive tech; the visible
                    hover card below is the styled one. */}
                <title>{`${n.name} — ${n.id}`}</title>
              </circle>
            </g>
          );
        })}
      </svg>

      {/* One hover card for the whole map.
          A tooltip per node would mean ~18 portals and 18 popper instances on
          a diagram where at most one is ever open. Positioned in percent so it
          tracks the SVG at any render width. */}
      {hover && (
        <div
          className={cn(
            "pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full",
            "animate-scale-in max-w-[220px] rounded-sm border border-strong",
            "bg-overlay px-2 py-1.5 text-sm shadow-e3"
          )}
          style={{
            left: `${(hover.x / W) * 100}%`,
            top: `${((hover.y - NODE_R - 16) / H) * 100}%`,
          }}
        >
          <div className="text-xs font-semibold text-fg">{hover.name}</div>
          <div className="font-mono text-2xs text-faint">
            {KIND_NOUN[hover.kind]} · {hover.id}
          </div>
          {hover.detail && (
            <div className="mt-0.5 text-xs text-muted">{hover.detail}</div>
          )}
          {hover.regulated && (
            <div className="mt-0.5 text-xs text-accent-text">
              Regulated — the ingredient and allergen declarations are legally
              binding
            </div>
          )}
          {hover.single && (
            <div className="mt-0.5 text-xs text-warn-text">
              Single source — exactly one supplier document defines this, so
              there is nothing to check it against
            </div>
          )}
          {hitNodes.has(hover.id) && (
            <div className="mt-0.5 text-xs text-danger-text">
              In the blast radius of the correction
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* --- geometry ------------------------------------------------------------- */

/** A gentle S-curve, so listings that share endpoints stay distinguishable
 *  where several run in the same horizontal band. */
function curve(e: Edge): string {
  const mx = (e.a.x + e.b.x) / 2;
  return `M ${e.a.x} ${e.a.y} C ${mx} ${e.a.y}, ${mx} ${e.b.y}, ${e.b.x} ${e.b.y}`;
}

/** The midpoint of that curve and the tangent angle there, in degrees.
 *
 * Both fall out of the cubic in closed form - the control points share the
 * midpoint's x, so t=0.5 lands exactly on the average of the endpoints. No
 * getTotalLength, no DOM measurement, no layout pass. */
function midpoint(e: Edge): [number, number, number] {
  const mx = (e.a.x + e.b.x) / 2;
  const my = (e.a.y + e.b.y) / 2;
  const angle =
    (Math.atan2(0.5 * (e.b.y - e.a.y), 0.25 * (e.b.x - e.a.x)) * 180) / Math.PI;
  return [mx, my, angle];
}

const STATUS_WORDS: Record<ListingStatus, string> = {
  LIVE: "live on the channel",
  PREPARED: "prepared, ready to publish",
  WITHHELD: "held back until a reviewer approves",
  REJECTED: "rejected by the channel",
};

const statusWords = (s?: ListingStatus) =>
  s ? STATUS_WORDS[s] : "status unknown";

/** The ring colour for a product the pass has already decided.
 *
 *  Three words, three colours, and no fourth: `verdict.decide` returns a
 *  closed set of three and a colour for anything else would be a colour for a
 *  state that cannot happen. */
function verdictStroke(verdict: string): string {
  if (verdict === "READY_TO_LAUNCH") return "stroke-ok";
  if (verdict === "BLOCKED") return "stroke-danger";
  return "stroke-warn";
}


function bodyClass(n: Placed, hit: boolean, selected: boolean,
                   working = false) {
  return cn(
    "transition-[fill,stroke,stroke-width] duration-[var(--dur-base)]",
    hit
      ? "fill-danger-soft stroke-danger [stroke-width:2.5] sc-breathe"
      : working
      // The same breathe the blast radius uses, in the accent rather than the
      // danger colour: "we are looking at this" and "this is at risk" are both
      // states that persist, and neither is traffic - but only one of them is
      // bad news, and the colour is the only thing saying which.
      ? "fill-accent-soft stroke-accent [stroke-width:2.5] sc-breathe"
      : "fill-raised stroke-strong [stroke-width:1.5]",
    // Regulated: a claim- or allergen-controlled product. Nothing on this
    // diagram is allowed to be easier to miss.
    n.regulated && !hit && "stroke-accent [stroke-width:2.5]",
    // Single-source entities are drawn with a broken outline: there is no
    // second document behind them, and the outline says so before anything
    // is read.
    n.single && "[stroke-dasharray:4_2.5]",
    selected && "stroke-accent [stroke-width:3]"
  );
}

/** Legend. Without it the shapes are decoration rather than information.
 *
 * Each swatch is drawn the way the map actually draws that state - same
 * rounded square, same stroke weights, same gate bar - so the legend is a
 * sample of the diagram rather than an approximation that can drift from it.
 */
export function MapLegend({ live }: { live?: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-faint">
      {live && (
        <LegendItem label="live event" className="text-accent-text">
          <circle cx="9" cy="9" r="3.2" className="fill-accent" />
          <circle cx="9" cy="9" r="7" fill="none" className="stroke-accent"
                  strokeWidth="1.2" opacity="0.5" />
        </LegendItem>
      )}
      <LegendItem label="product or variant">
        <NodeSwatch className="fill-raised stroke-strong" strokeWidth={1.5} />
      </LegendItem>
      <LegendItem label="channel">
        <circle cx="9" cy="9" r="7" className="fill-raised stroke-strong"
                strokeWidth="1.5" />
      </LegendItem>
      <LegendItem label="in blast radius">
        <NodeSwatch className="fill-danger-soft stroke-danger" strokeWidth={2.2} />
      </LegendItem>
      <LegendItem label="regulated">
        <NodeSwatch className="fill-raised stroke-accent" strokeWidth={2.2} />
      </LegendItem>
      <LegendItem label="single source">
        <NodeSwatch className="fill-raised stroke-strong" strokeWidth={1.5}
                    dash="3 2" />
      </LegendItem>
      <LegendItem label="listing">
        <line x1="1" y1="9" x2="17" y2="9" className="stroke-viz-edge"
              strokeWidth="1.4" />
        <line x1="1" y1="9" x2="17" y2="9"
              className="sc-flow stroke-viz-flow opacity-60" strokeWidth="1.4" />
      </LegendItem>
      <LegendItem label="held for review">
        <line x1="1" y1="9" x2="17" y2="9" className="stroke-warn"
              strokeWidth="2" />
        <line x1="9" y1="3.5" x2="9" y2="14.5" className="stroke-warn"
              strokeWidth="2.4" strokeLinecap="round" />
      </LegendItem>
      <LegendItem label="rejected by the channel">
        <line x1="1" y1="9" x2="17" y2="9" className="stroke-danger"
              strokeWidth="2" strokeDasharray="3 3.5" />
        <path d="M6 6l6 6M12 6l-6 6" className="stroke-danger" strokeWidth="1.8"
              strokeLinecap="round" />
      </LegendItem>
    </div>
  );
}

function LegendItem({ label, children, className }: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("flex items-center gap-1.5 whitespace-nowrap", className)}>
      <svg width="18" height="18" aria-hidden="true" className="shrink-0">
        {children}
      </svg>
      {label}
    </span>
  );
}

function NodeSwatch({ className, strokeWidth, dash }: {
  className: string;
  strokeWidth: number;
  dash?: string;
}) {
  return (
    <rect
      x="2" y="2" width="14" height="14" rx="3"
      className={className}
      strokeWidth={strokeWidth}
      strokeDasharray={dash}
    />
  );
}
