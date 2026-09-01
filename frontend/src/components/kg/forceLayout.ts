/* Force-directed layout, hand-rolled.
 *
 * No d3, no cytoscape, no react-force-graph. `README.md` states the position:
 * every diagram in this application is hand-rolled SVG. That is not stubborn -
 * `NetworkMap` and `GraphView` already draw node-link diagrams from the same
 * tokens as the rest of the UI, and a canvas library would arrive with its own
 * theming, its own accessibility story and its own idea of what a focus ring
 * looks like.
 *
 * **It runs once and stops.** Fruchterman-Reingold with a fixed iteration
 * budget, computed in a `useMemo` and then static. Not a requestAnimationFrame
 * loop. `NetworkMap` states why: fixed coordinates mean the diagram does not
 * move between renders while somebody is reading it, and this screen already
 * animates four other things. A graph that settles for three seconds every
 * time React re-renders is a graph nobody can point at.
 *
 * **It is deterministic.** Initial positions come from a golden-angle spiral
 * indexed by a stable hash of the node id - never Math.random(). Two renders
 * of the same neighbourhood produce the same picture, so expanding a node does
 * not reshuffle what the reader was looking at, and a screenshot in a bug
 * report matches what the next person sees.
 *
 * **Repulsion uses a uniform grid, not a quadtree.** Barnes-Hut is about a
 * hundred and fifty lines of tree to maintain and it buys nothing at two
 * hundred nodes; a grid of cells the size of the ideal edge length, comparing
 * only the 3x3 neighbourhood, is a dozen lines and the same complexity in this
 * range. If the cap ever rises past a couple of thousand, revisit this comment
 * rather than the number.
 */

export interface LayoutInput {
  /** Node ids. Index order is the order every array below is in. */
  ids: string[];
  /** Edges as index pairs into `ids`. */
  edges: [number, number][];
  /** Indices held in place, with where to hold them. */
  pinned?: Map<number, [number, number]>;
  width: number;
  height: number;
  iterations?: number;
  /** Milliseconds to spend before settling for what it has. */
  budgetMs?: number;
}

export interface LayoutResult {
  x: Float32Array;
  y: Float32Array;
  /** How many iterations actually ran. Fewer than asked means the budget bit,
   *  which is worth knowing when a layout looks less relaxed than usual. */
  iterations: number;
}

/* Generous, because this runs once when somebody presses a button and then
   never again. 120ms was tuned for a solver that might run per frame; this one
   has a whole interaction to spend, and the difference between 300 iterations
   and 600 is the difference between a legible graph and a knot. */
const DEFAULT_ITERATIONS = 600;
const DEFAULT_BUDGET_MS = 450;

/** Stable string hash. Not for security - for making a layout reproducible.
 *
 *  JavaScript has no built-in stable hash, and the obvious alternative -
 *  seeding by array position - moves every node the moment one is added. FNV-1a
 *  keyed on the node id means a node lands in the same starting place whatever
 *  else is on screen. */
function hash(text: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export function forceLayout(input: LayoutInput): LayoutResult {
  const { ids, edges, width, height } = input;
  const n = ids.length;
  const x = new Float32Array(n);
  const y = new Float32Array(n);
  if (n === 0) return { x, y, iterations: 0 };

  const iterations = input.iterations ?? DEFAULT_ITERATIONS;
  const budgetMs = input.budgetMs ?? DEFAULT_BUDGET_MS;
  const pinned = input.pinned ?? new Map<number, [number, number]>();

  /* Golden-angle spiral: the arrangement sunflower seeds use, and the reason
     is the same one - it fills a disc evenly with no clumping at any radius,
     so the solver starts from something already spread out rather than
     spending its first fifty iterations pushing a pile apart. */
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.42;
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const held = pinned.get(i);
    if (held) {
      x[i] = held[0];
      y[i] = held[1];
      continue;
    }
    // The hash decides where on the spiral this id sits; the index decides
    // how far out. Both are stable.
    const step = (hash(ids[i]) % 997) / 997;
    const t = (i + 0.5) / n;
    const angle = (i + step) * golden;
    x[i] = cx + Math.cos(angle) * radius * Math.sqrt(t);
    y[i] = cy + Math.sin(angle) * radius * Math.sqrt(t);
  }
  if (n === 1) return { x, y, iterations: 0 };

  const dx = new Float32Array(n);
  const dy = new Float32Array(n);
  const edgeA = new Int32Array(edges.length);
  const edgeB = new Int32Array(edges.length);
  for (let e = 0; e < edges.length; e++) {
    edgeA[e] = edges[e][0];
    edgeB[e] = edges[e][1];
  }

  /* The ideal edge length. Everything else is expressed in terms of it. */
  const k = Math.sqrt((width * height) / n);
  const k2 = k * k;
  const cell = k;
  const cols = Math.max(1, Math.ceil(width / cell) + 2);
  const rows = Math.max(1, Math.ceil(height / cell) + 2);
  const heads = new Int32Array(cols * rows);
  const next = new Int32Array(n);

  const started = typeof performance !== "undefined" ? performance.now() : 0;
  let temperature = width / 10;
  const cooling = temperature / (iterations + 1);
  let ran = 0;

  for (let step = 0; step < iterations; step++) {
    ran = step + 1;

    // Checked every fifty rather than every pass: reading the clock is not
    // free, and a slow machine should get a slightly less relaxed graph, not
    // a frozen tab.
    if (step % 50 === 0 && started
        && performance.now() - started > budgetMs) break;

    dx.fill(0);
    dy.fill(0);

    /* --- repulsion, over the 3x3 cell neighbourhood --------------------- */
    heads.fill(-1);
    for (let i = 0; i < n; i++) {
      const gx = Math.min(cols - 1, Math.max(0, Math.floor(x[i] / cell) + 1));
      const gy = Math.min(rows - 1, Math.max(0, Math.floor(y[i] / cell) + 1));
      const bucket = gy * cols + gx;
      next[i] = heads[bucket];
      heads[bucket] = i;
    }

    for (let i = 0; i < n; i++) {
      const gx = Math.min(cols - 1, Math.max(0, Math.floor(x[i] / cell) + 1));
      const gy = Math.min(rows - 1, Math.max(0, Math.floor(y[i] / cell) + 1));
      for (let oy = -1; oy <= 1; oy++) {
        const ry = gy + oy;
        if (ry < 0 || ry >= rows) continue;
        for (let ox = -1; ox <= 1; ox++) {
          const rx = gx + ox;
          if (rx < 0 || rx >= cols) continue;
          for (let j = heads[ry * cols + rx]; j !== -1; j = next[j]) {
            if (j === i) continue;
            let vx = x[i] - x[j];
            let vy = y[i] - y[j];
            let d2 = vx * vx + vy * vy;
            if (d2 < 0.01) {
              // Two nodes exactly on top of each other have no direction to
              // separate along, so give them one from their indices rather
              // than from a random number.
              vx = ((i % 7) - 3) * 0.1 || 0.1;
              vy = ((j % 7) - 3) * 0.1 || 0.1;
              d2 = vx * vx + vy * vy;
            }
            const d = Math.sqrt(d2);
            const force = k2 / d;
            dx[i] += (vx / d) * force;
            dy[i] += (vy / d) * force;
          }
        }
      }
    }

    /* --- attraction along edges ----------------------------------------- */
    for (let e = 0; e < edgeA.length; e++) {
      const a = edgeA[e];
      const b = edgeB[e];
      const vx = x[a] - x[b];
      const vy = y[a] - y[b];
      const d = Math.sqrt(vx * vx + vy * vy) || 0.01;
      const force = (d * d) / k;
      const fx = (vx / d) * force;
      const fy = (vy / d) * force;
      dx[a] -= fx;
      dy[a] -= fy;
      dx[b] += fx;
      dy[b] += fy;
    }

    /* --- move, capped by the temperature -------------------------------- */
    for (let i = 0; i < n; i++) {
      if (pinned.has(i)) continue;
      const d = Math.sqrt(dx[i] * dx[i] + dy[i] * dy[i]) || 1;
      const limit = Math.min(d, temperature);
      x[i] += (dx[i] / d) * limit;
      y[i] += (dy[i] / d) * limit;
      // Kept inside the frame with a margin, so a node is never half off the
      // edge where its label cannot be read.
      x[i] = Math.min(width - 24, Math.max(24, x[i]));
      y[i] = Math.min(height - 24, Math.max(24, y[i]));
    }

    temperature = Math.max(temperature - cooling, 0.1);
  }

  return { x, y, iterations: ran };
}

/** The box the laid-out nodes actually occupy, padded. What zoom-to-fit uses.
 *
 *  Computed from the result rather than assumed to be the input frame: the
 *  solver clamps to the frame but rarely fills it, and fitting to the frame
 *  would leave a large graph looking small and a small one adrift in space. */
export function bounds(x: Float32Array, y: Float32Array, pad = 40) {
  if (x.length === 0) return { x: 0, y: 0, w: 100, h: 100 };
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (let i = 0; i < x.length; i++) {
    if (x[i] < minX) minX = x[i];
    if (x[i] > maxX) maxX = x[i];
    if (y[i] < minY) minY = y[i];
    if (y[i] > maxY) maxY = y[i];
  }
  return {
    x: minX - pad,
    y: minY - pad,
    w: Math.max(maxX - minX + pad * 2, 120),
    h: Math.max(maxY - minY + pad * 2, 120),
  };
}
