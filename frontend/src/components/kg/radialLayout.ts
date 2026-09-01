/* Radial layout: rings by hop distance, sectors by domain.
 *
 * This replaces a Fruchterman-Reingold solver, and the reason is worth stating
 * because "we had a force layout and now we don't" reads like a downgrade.
 *
 * A force layout has no opinion. It is the right tool when you do not know
 * what the graph means and want the structure to emerge - which is exactly not
 * this case. Every neighbourhood here has a centre (the SKU somebody opened),
 * every node has a known hop distance from it, and every node has a known
 * domain. Physics was being asked to rediscover, badly, three things we
 * already knew, and what it produced was a hairball: fifty-eight product nodes
 * in a mass with the other six domains scattered around the edge.
 *
 * So position carries information instead:
 *
 *   * **Distance from the centre is hop distance.** The inner ring is what
 *     this product touches directly. The next ring is what those touch. You
 *     can read the depth control's effect off the picture rather than trusting
 *     it happened.
 *
 *   * **Angle is domain.** The seven domains occupy sectors in a fixed order,
 *     so compliance is always in the same direction as compliance. Two
 *     neighbourhoods of two different products are comparable at a glance,
 *     which a force layout can never be - it reaches a different arrangement
 *     every time the node set changes.
 *
 * The layout cannot produce a hairball because nothing is free to move.
 *
 * **Sector widths are proportional, with a floor.** Equal sevenths would be
 * more learnable, and would also put fifty-eight product nodes into the same
 * arc as three media nodes. Proportional widths keep the density even; the
 * fixed *order* is what keeps it learnable. A domain with one node still gets
 * a visible wedge, because a sector too thin to see reads as a domain that is
 * not there.
 */

import type { KgDomain, KgEdge, KgNode } from "../../api";
import { DOMAIN_ORDER } from "./domains";

export interface RadialInput {
  nodes: KgNode[];
  edges: KgEdge[];
  /** The node everything is measured from. */
  rootId: string;
  /** Distance between rings, in layout units. */
  ringGap?: number;
}

export interface Placed {
  id: string;
  x: number;
  y: number;
  /** Hops from the root. 0 is the root itself. */
  hop: number;
}

const RING_GAP = 260;

/** Roughly the room one node needs along an arc, in layout units. Node
 *  diameters top out well below this; the surplus is the gap that stops a
 *  crowded wedge reading as a solid band. */
const SPACING = 74;

/** How far apart the sub-rings inside one wedge sit. Deliberately much less
 *  than RING_GAP: a domain that needs three sub-rings must still look nearer
 *  than the next hop out, or distance stops meaning hops. */
const SUB_RING_GAP = 56;

/** The smallest slice a domain may get, as a fraction of the circle. Below
 *  about a twentieth the wedge stops reading as a direction. */
const MIN_SHARE = 0.05;

/** Hops from the root, breadth-first over the edges actually returned.
 *
 *  Computed here rather than asked of the server: the API returns a node set
 *  and its edges, and the hop distance is a property of *this* subgraph, not
 *  of the whole graph. A node two hops away in the database may be one hop
 *  away in a view that filtered out what sat between them, and the picture has
 *  to show the graph the reader is actually looking at.
 */
export function hopDistances(
  nodes: KgNode[], edges: KgEdge[], rootId: string,
): Map<string, number> {
  const present = new Set(nodes.map((node) => node.id));
  const neighbours = new Map<string, string[]>();
  for (const edge of edges) {
    if (!present.has(edge.source) || !present.has(edge.target)) continue;
    (neighbours.get(edge.source) ?? neighbours.set(edge.source, []).get(edge.source)!)
      .push(edge.target);
    (neighbours.get(edge.target) ?? neighbours.set(edge.target, []).get(edge.target)!)
      .push(edge.source);
  }

  const hops = new Map<string, number>([[rootId, 0]]);
  const queue = [rootId];
  while (queue.length) {
    const current = queue.shift()!;
    const hop = hops.get(current)!;
    for (const other of neighbours.get(current) ?? []) {
      if (hops.has(other)) continue;
      hops.set(other, hop + 1);
      queue.push(other);
    }
  }

  // Anything the walk did not reach - an expansion that arrived without its
  // connecting edge, say - is parked on the outermost ring rather than dropped
  // or piled on the centre. Being visibly far away is the honest placement for
  // a node whose distance is unknown.
  let furthest = 0;
  for (const hop of hops.values()) furthest = Math.max(furthest, hop);
  for (const node of nodes) {
    if (!hops.has(node.id)) hops.set(node.id, furthest + 1);
  }
  return hops;
}

export function radialLayout(input: RadialInput): Placed[] {
  const { nodes, edges, rootId } = input;
  const ringGap = input.ringGap ?? RING_GAP;
  if (nodes.length === 0) return [];

  const hops = hopDistances(nodes, edges, rootId);
  const placed: Placed[] = [];

  /* --- how wide each domain's wedge is ---------------------------------- */
  const counts = new Map<KgDomain, number>();
  for (const node of nodes) {
    if (node.id === rootId) continue;
    counts.set(node.domain, (counts.get(node.domain) ?? 0) + 1);
  }
  const present = DOMAIN_ORDER.filter((domain) => (counts.get(domain) ?? 0) > 0);
  const total = [...counts.values()].reduce((sum, n) => sum + n, 0) || 1;

  // Raw share, floored, then renormalised so the floors do not push the total
  // past a full turn.
  const raw = new Map<KgDomain, number>();
  for (const domain of present) {
    raw.set(domain, Math.max((counts.get(domain) ?? 0) / total, MIN_SHARE));
  }
  const rawTotal = [...raw.values()].reduce((sum, n) => sum + n, 0) || 1;

  const sector = new Map<KgDomain, { from: number; to: number }>();
  let cursor = -Math.PI / 2;          // start at twelve o'clock
  for (const domain of present) {
    const span = ((raw.get(domain) ?? 0) / rawTotal) * Math.PI * 2;
    sector.set(domain, { from: cursor, to: cursor + span });
    cursor += span;
  }

  /* --- place, ring by ring, inside each domain's wedge ------------------- */
  const byRing = new Map<string, KgNode[]>();
  for (const node of nodes) {
    if (node.id === rootId) continue;
    const key = `${node.domain}:${hops.get(node.id) ?? 1}`;
    (byRing.get(key) ?? byRing.set(key, []).get(key)!).push(node);
  }

  placed.push({ id: rootId, x: 0, y: 0, hop: 0 });

  for (const [key, group] of byRing) {
    const [domain, hopText] = key.split(":") as [KgDomain, string];
    const hop = Number(hopText);
    const wedge = sector.get(domain);
    if (!wedge) continue;

    // Stable order inside a wedge, so the same neighbourhood draws the same
    // way twice. Best connected first, then by id.
    const ordered = [...group].sort(
      (a, b) => b.degree - a.degree || a.id.localeCompare(b.id));

    const radius = ringGap * hop;
    const span = wedge.to - wedge.from;
    // Inset from the wedge edges so neighbouring domains do not touch.
    const inset = span * 0.06;
    const from = wedge.from + inset;
    const usable = span - inset * 2;

    /* One wedge can hold only so many nodes at a given radius before they
     * touch. Rather than letting them overlap - or spiralling them outward in
     * a way that makes hop distance unreadable - the wedge is filled as a
     * short stack of sub-rings, inner first, each holding what its arc length
     * allows.
     *
     * Sub-rings sit close together and well inside the next hop's ring, so a
     * crowded domain grows *thicker* rather than reaching into the next ring.
     * Distance still reads as hop distance, which is the whole point of the
     * arrangement and the thing an overflow must not break.
     */
    const capacityAt = (r: number) =>
      Math.max(2, Math.floor((r * usable) / SPACING));

    let index = 0;
    let subRing = 0;
    while (index < ordered.length) {
      const r = radius + subRing * SUB_RING_GAP;
      const capacity = capacityAt(r);
      const slice = ordered.slice(index, index + capacity);
      const step = usable / slice.length;

      slice.forEach((node, slot) => {
        // Slot centres, not wedge edges: a wedge with one node puts it in the
        // middle of its direction rather than on the boundary with the next
        // domain.
        const angle = from + step * (slot + 0.5);
        placed.push({
          id: node.id,
          x: Math.cos(angle) * r,
          y: Math.sin(angle) * r,
          hop,
        });
      });

      index += slice.length;
      subRing += 1;
    }
  }

  return placed;
}
