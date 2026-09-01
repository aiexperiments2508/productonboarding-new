/* The graph itself: hand-rolled SVG, laid out once, then still.
 *
 * The idioms are `NetworkMap`'s, because a second diagram in this application
 * that behaved differently from the first would be a second thing to learn:
 * markers for arrowheads, a `<title>` and an `aria-label` on every node, a
 * transparent oversized hit target so a 5px circle is still clickable, and the
 * whole thing in an `overflow-x-auto` frame so a wide graph scrolls inside its
 * panel rather than pushing the page sideways.
 *
 * **Zoom is a viewBox, not a CSS transform.** A transform would scale stroke
 * widths with the drawing - a hairline edge becomes a rope at 4x - and would
 * put hit targets somewhere other than where they are painted. Changing the
 * viewBox moves the camera and leaves the drawing alone.
 *
 * **Plain wheel scrolls the page; ctrl or cmd wheel zooms.** This panel lives
 * inside a column that scrolls, and a canvas that swallowed the wheel would
 * trap a reader trying to get past it. That is also why there is an expand
 * control: the full-screen dialog is where the graph gets the whole viewport
 * and the wheel can mean what it likes.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { KgEdge, KgNode } from "../../api";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import { cn } from "../../ui";
import { DOMAIN_FILL, DOMAIN_STROKE } from "./domains";
import { bounds, forceLayout } from "./forceLayout";

/** The frame the solver lays out inside.
 *
 *  Not the frame it is drawn in - the viewBox fits to whatever the solver
 *  produces - so this is only ever about how much room the nodes have to
 *  spread into, and it is free to be generous. It was 1000x620, and at a
 *  hundred and twenty nodes that left Fruchterman-Reingold's ideal edge length
 *  short enough that a hub's children settled into a regular lattice against
 *  the margins: a picture of the clamp, not of the graph. */
const FRAME_W = 1800;
const FRAME_H = 1120;

/** Node radius by degree. A well-connected node is worth more ink, but the
 *  range is deliberately narrow: a hub forty times bigger than a leaf is a
 *  picture of one node. */
function radiusOf(degree: number): number {
  return Math.min(15, 5.5 + Math.sqrt(Math.max(degree, 0)) * 1.3);
}

export interface GraphCanvasProps {
  nodes: KgNode[];
  edges: KgEdge[];
  rootId: string;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onExpand: (id: string) => void;
  /** Bumped by the caller to force a re-fit - after a reset, or a domain
   *  filter change that moved everything. */
  fitToken: number;
  className?: string;
  height?: number;
}

export function GraphCanvas({
  nodes, edges, rootId, selectedId, onSelect, onExpand, fitToken,
  className, height = 420,
}: GraphCanvasProps) {
  const reduced = useReducedMotion();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [pinned, setPinned] = useState<Map<string, [number, number]>>(new Map());
  const [view, setView] = useState({ x: 0, y: 0, w: FRAME_W, h: FRAME_H });

  /* --- layout ------------------------------------------------------------
   * Once per data change, in a memo. See forceLayout.ts on why this is not a
   * running simulation. */
  const layout = useMemo(() => {
    const index = new Map(nodes.map((node, i) => [node.id, i]));
    const pairs: [number, number][] = [];
    for (const edge of edges) {
      const a = index.get(edge.source);
      const b = index.get(edge.target);
      if (a !== undefined && b !== undefined && a !== b) pairs.push([a, b]);
    }
    const held = new Map<number, [number, number]>();
    for (const [id, at] of pinned) {
      const i = index.get(id);
      if (i !== undefined) held.set(i, at);
    }
    const result = forceLayout({
      ids: nodes.map((n) => n.id),
      edges: pairs,
      pinned: held,
      width: FRAME_W,
      height: FRAME_H,
    });
    return { ...result, index };
  }, [nodes, edges, pinned]);

  const at = useCallback((id: string): [number, number] => {
    const i = layout.index.get(id);
    if (i === undefined) return [FRAME_W / 2, FRAME_H / 2];
    return [layout.x[i], layout.y[i]];
  }, [layout]);

  const fit = useCallback(() => {
    const box = bounds(layout.x, layout.y);
    setView({ x: box.x, y: box.y, w: box.w, h: box.h });
  }, [layout]);

  useEffect(() => { fit(); }, [fit, fitToken]);

  /* --- panning and dragging ---------------------------------------------
   * The dragged node's transform is written straight to the DOM on every
   * pointermove and only committed to React state on pointerup. A setState per
   * move would re-run the solver sixty times a second. */
  const drag = useRef<
    { id: string | null; startX: number; startY: number;
      originX: number; originY: number } | null>(null);

  const toFrame = useCallback((clientX: number, clientY: number) => {
    const box = svgRef.current?.getBoundingClientRect();
    if (!box) return [0, 0] as const;
    return [
      view.x + ((clientX - box.left) / box.width) * view.w,
      view.y + ((clientY - box.top) / box.height) * view.h,
    ] as const;
  }, [view]);

  const onPointerDown = (event: React.PointerEvent, id: string | null) => {
    (event.target as Element).setPointerCapture?.(event.pointerId);
    const [fx, fy] = toFrame(event.clientX, event.clientY);
    const origin = id ? at(id) : [view.x, view.y] as [number, number];
    drag.current = { id, startX: fx, startY: fy,
                     originX: origin[0], originY: origin[1] };
  };

  const onPointerMove = (event: React.PointerEvent) => {
    const held = drag.current;
    if (!held) return;
    const [fx, fy] = toFrame(event.clientX, event.clientY);
    if (held.id === null) {
      // Background drag pans the camera. Inverted, because moving the mouse
      // right should move the drawing right, which means moving the camera
      // left.
      setView((v) => ({ ...v,
        x: held.originX - (fx - held.startX),
        y: held.originY - (fy - held.startY) }));
      return;
    }
    const node = svgRef.current?.querySelector(
      `[data-node="${CSS.escape(held.id)}"]`);
    node?.setAttribute("transform",
      `translate(${held.originX + (fx - held.startX)},`
      + `${held.originY + (fy - held.startY)})`);
  };

  const onPointerUp = (event: React.PointerEvent) => {
    const held = drag.current;
    drag.current = null;
    if (!held?.id) return;
    const [fx, fy] = toFrame(event.clientX, event.clientY);
    const moved = Math.abs(fx - held.startX) + Math.abs(fy - held.startY);
    // A click is a drag that went nowhere. Below a few frame units it is a
    // selection, not a pin - otherwise every click would pin.
    if (moved < 4) return;
    setPinned((held2) => {
      const next = new Map(held2);
      next.set(held.id!, [held.originX + (fx - held.startX),
                          held.originY + (fy - held.startY)]);
      return next;
    });
  };

  const zoom = useCallback((factor: number, cx?: number, cy?: number) => {
    setView((v) => {
      const w = Math.min(FRAME_W * 3, Math.max(120, v.w * factor));
      const h = w * (v.h / v.w);
      const ax = cx ?? v.x + v.w / 2;
      const ay = cy ?? v.y + v.h / 2;
      return { w, h,
               x: ax - (ax - v.x) * (w / v.w),
               y: ay - (ay - v.y) * (h / v.h) };
    });
  }, []);

  const onWheel = (event: React.WheelEvent) => {
    // Only with a modifier. See the file header: this panel sits in a column
    // that scrolls, and swallowing the wheel would trap the reader in it.
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const [fx, fy] = toFrame(event.clientX, event.clientY);
    zoom(event.deltaY > 0 ? 1.12 : 0.89, fx, fy);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    const pan = view.w * 0.12;
    if (event.key === "+" || event.key === "=") zoom(0.85);
    else if (event.key === "-") zoom(1.18);
    else if (event.key === "0") fit();
    else if (event.key === "ArrowLeft") setView((v) => ({ ...v, x: v.x - pan }));
    else if (event.key === "ArrowRight") setView((v) => ({ ...v, x: v.x + pan }));
    else if (event.key === "ArrowUp") setView((v) => ({ ...v, y: v.y - pan }));
    else if (event.key === "ArrowDown") setView((v) => ({ ...v, y: v.y + pan }));
    else return;
    event.preventDefault();
  };

  const byId = useMemo(
    () => new Map(nodes.map((node) => [node.id, node])), [nodes]);

  /* The dozen best connected, which is about as many labels as fit before
     they start colliding. Ties break on id so the set does not flicker. */
  const labelled = useMemo(() => new Set(
    [...nodes]
      .sort((a, b) => b.degree - a.degree || a.id.localeCompare(b.id))
      .slice(0, 12)
      .map((node) => node.id),
  ), [nodes]);

  return (
    <div className={cn("relative min-w-0", className)}>
      <svg
        ref={svgRef}
        role="img"
        aria-label={`Knowledge graph: ${nodes.length} nodes, `
          + `${edges.length} connections`}
        tabIndex={0}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        onWheel={onWheel}
        onKeyDown={onKeyDown}
        onPointerDown={(e) => onPointerDown(e, null)}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        className={cn(
          "block w-full touch-none rounded-sm bg-sunken outline-none",
          "focus-visible:ring-2 focus-visible:ring-focus",
        )}
        style={{ height }}
      >
        <defs>
          <marker id="kg-arrow" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 1 L7 4 L0 7 z" className="fill-viz-edge" />
          </marker>
          <filter id="kg-halo" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Edges first, so nodes sit on top of them. */}
        <g>
          {edges.map((edge, i) => {
            const [x1, y1] = at(edge.source);
            const [x2, y2] = at(edge.target);
            const touched = selectedId
              && (edge.source === selectedId || edge.target === selectedId);
            return (
              <line
                key={edge.id}
                x1={x1} y1={y1} x2={x2} y2={y2}
                markerEnd="url(#kg-arrow)"
                strokeWidth={touched ? 1.8 : 1}
                strokeDasharray={edge.synthetic ? "4 3" : undefined}
                className={cn(
                  touched ? "stroke-accent" : "stroke-viz-edge",
                  !reduced && "sc-draw",
                )}
                style={!reduced
                  ? ({ "--draw-length": "600",
                       animationDelay: `${Math.min(i, 40) * 8}ms` } as never)
                  : undefined}
                opacity={selectedId && !touched ? 0.35 : 1}
              >
                <title>{`${byId.get(edge.source)?.name ?? edge.source} `
                  + `${edge.type.toLowerCase().replace(/_/g, " ")} `
                  + `${byId.get(edge.target)?.name ?? edge.target}`}</title>
              </line>
            );
          })}
        </g>

        <g>
          {nodes.map((node) => {
            const [cx, cy] = at(node.id);
            const r = radiusOf(node.degree);
            const isRoot = node.id === rootId;
            const isSelected = node.id === selectedId;
            const isPinned = pinned.has(node.id);
            return (
              <g key={node.id} data-node={node.id}
                 transform={`translate(${cx},${cy})`}>
                {/* The spine is a square, everything else a circle - so the
                    picture still parses without colour. */}
                {node.domain === "CORE" ? (
                  <rect
                    x={-r} y={-r} width={r * 2} height={r * 2} rx={3}
                    className={cn(DOMAIN_FILL[node.domain],
                                  DOMAIN_STROKE[node.domain])}
                    strokeWidth={isRoot ? 2.5 : 1.2}
                    strokeDasharray={node.synthetic ? "3 2" : undefined}
                    fillOpacity={isSelected ? 1 : 0.82}
                    filter={isSelected && !reduced ? "url(#kg-halo)" : undefined}
                  />
                ) : (
                  <circle
                    r={r}
                    className={cn(DOMAIN_FILL[node.domain],
                                  DOMAIN_STROKE[node.domain])}
                    strokeWidth={isRoot ? 2.5 : 1.2}
                    strokeDasharray={node.synthetic ? "3 2" : undefined}
                    fillOpacity={isSelected ? 1 : 0.82}
                    filter={isSelected && !reduced ? "url(#kg-halo)" : undefined}
                  />
                )}

                {isPinned && (
                  <circle r={r + 4} fill="none" strokeWidth={1}
                          strokeDasharray="2 2" className="stroke-strong" />
                )}

                {/* Labels only where they can be read.
                    Degree alone was the wrong test: in a dense neighbourhood
                    forty nodes clear any fixed threshold and their labels
                    overlap into a grey smear, which is worse than no labels at
                    all. `labelled` picks the dozen best-connected in this view,
                    so the count stays constant however dense the graph is.
                    Every node is named in its <title> and aria-label
                    regardless, so nothing is hidden from a screen reader. */}
                {(isRoot || isSelected || labelled.has(node.id)) && (
                  <text
                    y={-r - 5}
                    textAnchor="middle"
                    className="pointer-events-none fill-muted text-[10px]"
                  >
                    {node.name.length > 26
                      ? `${node.name.slice(0, 24)}…` : node.name}
                  </text>
                )}

                {/* A transparent target, so a small node is still clickable
                    and reachable by keyboard. NetworkMap does the same. */}
                <circle
                  r={Math.max(r + 7, 14)}
                  fill="transparent"
                  tabIndex={0}
                  role="button"
                  aria-label={`${node.name}, ${node.label}`
                    + `${node.synthetic ? ", generated data" : ""}`
                    + `, ${node.degree} connections`}
                  className="cursor-pointer outline-none focus-visible:stroke-focus"
                  strokeWidth={2}
                  onPointerDown={(e) => { e.stopPropagation();
                                          onPointerDown(e, node.id); }}
                  onClick={(e) => { e.stopPropagation();
                                    onSelect(isSelected ? null : node.id); }}
                  onDoubleClick={(e) => { e.stopPropagation();
                                          onExpand(node.id); }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(isSelected ? null : node.id);
                    } else if (e.key === "e") {
                      e.preventDefault();
                      onExpand(node.id);
                    }
                  }}
                >
                  <title>{node.name} — {node.label}</title>
                </circle>
              </g>
            );
          })}
        </g>
      </svg>

      <div className="pointer-events-none absolute bottom-1.5 right-2 text-2xs
                      text-faint">
        ctrl + wheel to zoom · drag to pan · double-click to expand
      </div>
    </div>
  );
}

export { FRAME_H, FRAME_W };
