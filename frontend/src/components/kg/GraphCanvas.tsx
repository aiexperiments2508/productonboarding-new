/* The graph, rendered by NVL, arranged by us.
 *
 * NVL is Neo4j's own visualisation library - the renderer under Neo4j Browser
 * and Bloom. It is the first chart or graph library in this repository, which
 * `README.md` used to rule out, and it was taken deliberately with its costs
 * known: a proprietary licence, a Segment analytics SDK among its transitive
 * dependencies, and four high-severity advisories at the time of writing. That
 * is recorded here rather than only in a commit message, because the next
 * person to read this file is the one who needs to know it.
 *
 * Only `@neo4j-nvl/base` and `@neo4j-nvl/interaction-handlers` are installed.
 * The official React wrapper declares `peer react "18.0.0 || ^19.0.0"` - exact
 * 18.0.0 - which will not resolve against this project's 18.3.1 and would have
 * made `--legacy-peer-deps` permanent, and `startup.bat clean` a special case.
 * Binding it to React by hand is forty lines and costs nothing.
 *
 * **NVL renders; it does not arrange.** The layout is `free` and every node
 * arrives with coordinates from `radialLayout.ts`. Letting NVL run its own
 * force layout would undo the entire point - rings mean hop distance, angle
 * means domain - and replace both with a hairball that merely looks nicer.
 *
 * **Two things a canvas costs, and what is done about them.**
 *
 * Colour: NVL takes colour strings, not Tailwind classes, so the domain tokens
 * are resolved at runtime and re-resolved when the theme moves, which
 * `useTokenPalette` watches for. Every other surface here gets theming free
 * through `@theme inline`; this is the one that has to ask.
 *
 * Accessibility: a canvas has no DOM per node, so the `aria-label`, `tabIndex`
 * and Enter/Space handling the previous SVG gave every node are simply gone.
 * They are replaced below by a real focusable list - not an `sr-only`
 * afterthought, but the same two actions, reachable by keyboard.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NVL } from "@neo4j-nvl/base";
import type { Node as NvlNode, Relationship as NvlRel } from "@neo4j-nvl/base";
import {
  ClickInteraction, DragNodeInteraction, PanInteraction, ZoomInteraction,
} from "@neo4j-nvl/interaction-handlers";

import type { KgDomain, KgEdge, KgNode } from "../../api";
import { cn } from "../../ui";
import { DOMAIN_LABEL, DOMAIN_ORDER, labelNoun } from "./domains";
import { radialLayout } from "./radialLayout";

/** Node size by degree. A well-connected node is worth more ink, but the range
 *  stays narrow: a hub forty times the size of a leaf is a picture of one node
 *  rather than of a neighbourhood.
 *
 *  These were three times bigger to begin with, which turned every wedge into
 *  a solid band of touching circles - the layout was right and unreadable at
 *  the same time. Node size has to be read against the arc spacing in
 *  `radialLayout.ts`, not chosen on its own. */
function sizeOf(degree: number): number {
  return Math.min(19, 8 + Math.sqrt(Math.max(degree, 0)) * 1.5);
}

/** Turn a CSS custom property into something NVL can paint with.
 *
 *  The design tokens are `oklch(...)` and NVL parses colours with tinycolor2,
 *  which predates oklch: handed one, it produces an invalid colour and the
 *  node is drawn with nothing. Every node in the graph came out blank exactly
 *  once for this reason, and the first attempted fix - assign the value to an
 *  element and read `getComputedStyle().color` back - does not work either,
 *  because current Chrome preserves the authored colour space and returns
 *  `oklch(...)` unchanged.
 *
 *  Reading `fillStyle` back does not work either, and for the same underlying
 *  reason: Chrome now preserves the authored colour space there too, so an
 *  `oklch()` goes in and an `oklch()` comes out.
 *
 *  **Rasterising is the only conversion that cannot be preserved away.** Paint
 *  one pixel and read its bytes: a pixel has no colour space to remember, only
 *  four numbers. That also gives a free validity check - an unparseable colour
 *  paints nothing, so the alpha byte comes back zero.
 */
function normaliseColour(probe: CanvasRenderingContext2D | null,
                         value: string, fallback: string): string {
  if (!probe || !value) return fallback;
  try {
    probe.clearRect(0, 0, 1, 1);
    probe.fillStyle = value;
    probe.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = probe.getImageData(0, 0, 1, 1).data;
    return a === 0 ? fallback : `rgb(${r}, ${g}, ${b})`;
  } catch {
    return fallback;
  }
}

function resolveColour(probe: CanvasRenderingContext2D | null,
                       token: string, fallback: string) {
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue(token).trim();
  return normaliseColour(probe, raw, fallback);
}

interface Palette {
  domain: Record<KgDomain, string>;
  edge: string;
  edgeSelected: string;
}

/** The domain colours, resolved, and re-resolved whenever the theme moves.
 *
 *  The theme is an attribute on `<html>`, so a MutationObserver on it is the
 *  whole mechanism - plus the media query, because "system" sets no attribute
 *  at all. Without this the graph keeps its light-mode colours on a dark
 *  background until something unrelated re-renders it, which reads as a
 *  rendering bug rather than a missing subscription.
 */
function useTokenPalette(): Palette {
  const read = useCallback((): Palette => {
    // willReadFrequently: this is a read-back-per-colour probe, which is
    // exactly the pattern that hint exists for.
    const probe = document.createElement("canvas")
      .getContext("2d", { willReadFrequently: true });
    const domain = {} as Record<KgDomain, string>;
    for (const name of DOMAIN_ORDER) {
      domain[name] = resolveColour(
        probe, `--kg-${name.toLowerCase()}`, "#7a7a7a");
    }
    return {
      domain,
      edge: resolveColour(probe, "--viz-edge", "#b4b4b4"),
      edgeSelected: resolveColour(probe, "--a-500", "#3c78dc"),
    };
  }, []);

  const [palette, setPalette] = useState<Palette>(read);

  useEffect(() => {
    const observer = new MutationObserver(() => setPalette(read()));
    observer.observe(document.documentElement,
                     { attributes: true,
                       attributeFilter: ["data-theme", "class", "style"] });
    const media = matchMedia("(prefers-color-scheme: dark)");
    const onScheme = () => setPalette(read());
    media.addEventListener("change", onScheme);
    return () => {
      observer.disconnect();
      media.removeEventListener("change", onScheme);
    };
  }, [read]);

  return palette;
}

export interface GraphCanvasProps {
  nodes: KgNode[];
  edges: KgEdge[];
  rootId: string;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onExpand: (id: string) => void;
  /** Bumped by the caller to force a re-fit - after a reset, or a filter
   *  change that moved everything. */
  fitToken: number;
  className?: string;
  height?: number;
}

export function GraphCanvas({
  nodes, edges, rootId, selectedId, onSelect, onExpand, fitToken,
  className, height = 420,
}: GraphCanvasProps) {
  const frame = useRef<HTMLDivElement | null>(null);
  const nvl = useRef<NVL | null>(null);
  const interactions = useRef<{ destroy: () => void }[]>([]);
  const palette = useTokenPalette();

  // The interaction handlers are attached once, so a callback captured then
  // would close over the first render's props for ever. A ref is the seam.
  const handlers = useRef({ onSelect, onExpand });
  handlers.current = { onSelect, onExpand };

  const placed = useMemo(
    () => radialLayout({ nodes, edges, rootId }), [nodes, edges, rootId]);

  // Positions are applied through `setNodePositions` below rather than as
  // fields here. NVL's own note on the free layout says so - "arbitrary
  // positioning ... using NVL's setPosition method" - and passing x/y on the
  // node objects instead leaves the renderer with nothing to draw and throws
  // inside its animation loop, which is a long way from the mistake.
  const placedNodes = useMemo<NvlNode[]>(
    () => placed.map((entry) => ({ id: entry.id, x: entry.x, y: entry.y })),
    [placed]);

  /** The dozen best-connected nodes, which is about as many captions as fit
   *  before they start colliding. Ties break on id so the set does not
   *  flicker between renders. */
  const captioned = useMemo(() => new Set(
    [...nodes]
      .sort((a, b) => b.degree - a.degree || a.id.localeCompare(b.id))
      .slice(0, 12)
      .map((node) => node.id),
  ), [nodes]);

  const nvlNodes = useMemo<NvlNode[]>(() => nodes.map((node) => {
    const isRoot = node.id === rootId;
    return {
      id: node.id,
      size: sizeOf(node.degree) * (isRoot ? 1.5 : 1),
      color: palette.domain[node.domain],
      // Captions on the root, the selection, and a dozen others - never a
      // fixed degree threshold, which put captions on eighty-three of a
      // hundred and twenty-three nodes and produced a grey smear. A count is
      // the right control here: it holds however dense the graph gets.
      caption: isRoot || node.id === selectedId || captioned.has(node.id)
        ? node.name.slice(0, 24) : "",
      captionAlign: "bottom" as const,
      selected: node.id === selectedId,
    };
  }), [nodes, palette, rootId, selectedId, captioned]);

  const nvlRels = useMemo<NvlRel[]>(() => edges.map((edge) => {
    const touched = Boolean(selectedId)
      && (edge.source === selectedId || edge.target === selectedId);
    return {
      id: edge.id,
      from: edge.source,
      to: edge.target,
      color: touched ? palette.edgeSelected : palette.edge,
      width: touched ? 2 : 1,
    };
  }), [edges, palette, selectedId]);

  /* --- the instance, created once ---------------------------------------- */
  useEffect(() => {
    if (!frame.current) return undefined;

    const instance = new NVL(frame.current, [], [], {
      // See the file header: we arrange, NVL renders.
      layout: "free",
      renderer: "canvas",
      initialZoom: 1,
      // NVL phones home through @segment/analytics-next otherwise. This
      // application does not send anything anywhere, and a graph library is
      // not the place to start.
      disableTelemetry: true,
    } as never, {});
    nvl.current = instance;

    // NVL types every interaction callback as `(...args: unknown[]) => void`,
    // so the first argument is narrowed here rather than in the signature.
    const click = new ClickInteraction(instance);
    click.updateCallback("onNodeClick", (...args: unknown[]) =>
      handlers.current.onSelect((args[0] as NvlNode).id));
    click.updateCallback("onNodeDoubleClick", (...args: unknown[]) =>
      handlers.current.onExpand((args[0] as NvlNode).id));
    click.updateCallback("onCanvasClick", () =>
      handlers.current.onSelect(null));

    interactions.current = [
      new ZoomInteraction(instance),
      new PanInteraction(instance),
      new DragNodeInteraction(instance),
      click,
    ];

    return () => {
      for (const handler of interactions.current) handler.destroy();
      interactions.current = [];
      instance.destroy();
      nvl.current = null;
    };
  }, []);

  /* --- data, whenever it changes ----------------------------------------- */
  useEffect(() => {
    const instance = nvl.current;
    if (!instance) return;
    instance.addAndUpdateElementsInGraph(nvlNodes, nvlRels);
    // Then the arrangement. `false` means "do not let a layout algorithm move
    // them afterwards" - which with `layout: free` is belt and braces, and
    // costs nothing if the layout is ever changed.
    instance.setNodePositions(placedNodes, false);
  }, [nvlNodes, nvlRels, placedNodes]);

  /* --- fit, on demand ---------------------------------------------------- */
  useEffect(() => {
    const instance = nvl.current;
    if (!instance || nvlNodes.length === 0) return undefined;
    // Deferred a frame: `fit` measures the container, and on the first paint
    // after a filter change the container has not been laid out yet.
    const timer = window.setTimeout(
      () => instance.fit(nvlNodes.map((node) => node.id)), 80);
    return () => window.clearTimeout(timer);
  }, [fitToken, nvlNodes]);

  const byDegree = useMemo(
    () => [...nodes].sort(
      (a, b) => b.degree - a.degree || a.id.localeCompare(b.id)),
    [nodes]);

  return (
    <div className={cn("relative min-w-0", className)}>
      <div
        ref={frame}
        style={{ height }}
        className="w-full overflow-hidden rounded-sm bg-sunken"
      />

      <div className="pointer-events-none absolute right-2 top-1.5 text-2xs
                      text-faint">
        distance from the centre is hops · direction is domain
      </div>

      {/* The keyboard and screen-reader path.
        *
        * Not decoration: a canvas cannot be tabbed into, so this is the only
        * way to reach a node without a mouse. Ordered by connectedness so the
        * most useful nodes come first rather than whatever order the walk
        * happened to return, and kept to a scrolling strip so it costs little
        * room on a screen that is mostly picture.
        */}
      <div className="mt-2">
        <h4 className="mb-1 text-2xs uppercase tracking-caps text-faint">
          Nodes in this view — Enter selects, E expands
        </h4>
        <ul className="flex max-h-20 flex-wrap gap-1 overflow-y-auto">
          {byDegree.map((node) => (
            <li key={node.id}>
              <button
                onClick={() => onSelect(node.id === selectedId ? null : node.id)}
                onKeyDown={(event) => {
                  if (event.key === "e" || event.key === "E") {
                    event.preventDefault();
                    onExpand(node.id);
                  }
                }}
                aria-pressed={node.id === selectedId}
                aria-label={`${node.name}, ${labelNoun(node.label)}, `
                  + `${DOMAIN_LABEL[node.domain]}`
                  + `${node.synthetic ? ", generated data" : ""}`
                  + `, ${node.degree} connections`}
                className={cn(
                  "rounded-xs border px-1.5 py-0.5 text-2xs",
                  node.id === selectedId
                    ? "border-accent-border bg-accent-soft text-accent-text"
                    : "border-subtle text-muted hover:text-fg",
                  node.synthetic && "border-dashed",
                )}
              >
                {node.name.length > 22
                  ? `${node.name.slice(0, 20)}…` : node.name}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
