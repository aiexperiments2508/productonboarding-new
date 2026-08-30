import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { GraphTopology, RunSnapshot } from "../api";
import { ArtBroken } from "../art/illustrations";
import { EmptyState, Panel, Skeleton, cn } from "../ui";

/* The agent graph, drawn locally.
 *
 * LangGraph Studio renders the same thing, but its UI is served from
 * smith.langchain.com and needs a sign-in - the graph runs locally, the *view*
 * does not. That is a dependency worth avoiding at a venue with a restricted
 * network, so the diagram is drawn here from the topology the compiled graph
 * reports about itself.
 *
 * Reading the structure from the running graph rather than hard-coding a
 * picture means the diagram cannot quietly drift from what actually executes -
 * add a node and it appears here.
 *
 * Layout is a longest-path layering: each node sits one rank deeper than its
 * deepest predecessor. That is enough for a DAG this size and needs no layout
 * library.
 *
 * The executed path draws itself in, rank by rank, so the picture reads as a
 * run that happened in an order rather than as a graph with some parts
 * highlighted. The suspended node keeps a slow halo, because that is the one
 * thing on this screen that is still waiting on a person.
 */

const NODE_W = 138;
const NODE_H = 32;
const H_GAP = 26;
const V_GAP = 48;
const PAD = 22;

interface Placed { id: string; x: number; y: number; rank: number }

export function GraphView({ run }: { run: RunSnapshot | null }) {
  const [topology, setTopology] = useState<GraphTopology | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.graph().then(setTopology).catch((e) => setError(String(e)));
  }, []);

  // Which nodes this run actually went through, and where it is now. Two trace
  // steps label themselves more readably than the node they run in, so they are
  // mapped back before the lookup - otherwise the executed path would skip them.
  const visited = useMemo(
    () => new Set((run?.values.trace ?? []).map((t) =>
      t.node === "validate" ? "validate_one"
      : t.node === "approval" ? "request_approval"
      : t.node)),
    [run]
  );
  const current = run?.next?.[0];

  const layout = useMemo(() => {
    if (!topology) return null;

    const incoming = new Map<string, string[]>();
    for (const n of topology.nodes) incoming.set(n, []);
    for (const e of topology.edges) {
      if (e.source !== e.target) incoming.get(e.target)?.push(e.source);
    }

    // Longest-path ranking, iterated to a fixed point. The graph has a cycle
    // back from close in principle, so cap the passes rather than recursing.
    const rank = new Map<string, number>(topology.nodes.map((n) => [n, 0]));
    for (let pass = 0; pass < topology.nodes.length; pass += 1) {
      let moved = false;
      for (const n of topology.nodes) {
        const preds = incoming.get(n) ?? [];
        const want = preds.length
          ? Math.max(...preds.map((p) => (rank.get(p) ?? 0) + 1)) : 0;
        if (want > (rank.get(n) ?? 0) && want < topology.nodes.length) {
          rank.set(n, want);
          moved = true;
        }
      }
      if (!moved) break;
    }

    const byRank = new Map<number, string[]>();
    for (const n of topology.nodes) {
      const r = rank.get(n) ?? 0;
      byRank.set(r, [...(byRank.get(r) ?? []), n]);
    }

    const ranks = [...byRank.keys()].sort((a, b) => a - b);
    const widest = Math.max(...ranks.map((r) => byRank.get(r)!.length));
    const width = PAD * 2 + widest * NODE_W + (widest - 1) * H_GAP;

    const placed: Placed[] = [];
    ranks.forEach((r, row) => {
      const nodes = byRank.get(r)!;
      const rowWidth = nodes.length * NODE_W + (nodes.length - 1) * H_GAP;
      const startX = (width - rowWidth) / 2;
      nodes.forEach((id, i) => {
        placed.push({
          id, rank: r,
          x: startX + i * (NODE_W + H_GAP),
          y: PAD + row * (NODE_H + V_GAP),
        });
      });
    });

    return {
      placed,
      byId: new Map(placed.map((p) => [p.id, p])),
      width,
      height: PAD * 2 + ranks.length * (NODE_H + V_GAP) - V_GAP,
    };
  }, [topology]);

  if (error) {
    return (
      <Panel title="Agent graph">
        <EmptyState art={<ArtBroken />} title="Could not read the topology">
          {error}
        </EmptyState>
      </Panel>
    );
  }
  if (!topology || !layout) {
    return (
      <Panel title="Agent graph">
        <Skeleton className="h-[260px] w-full" rounded="md" />
      </Panel>
    );
  }

  return (
    <Panel
      title="Agent graph"
      actions={
        <span className="text-sm text-faint">
          {topology.nodes.length} nodes · read from the running graph
        </span>
      }
    >
      <div className="min-w-0 overflow-x-auto">
        <svg
          viewBox={`0 0 ${layout.width} ${layout.height}`}
          style={{ width: "100%", minWidth: 440, display: "block" }}
          role="img"
          aria-label="LangGraph agent topology"
        >
          <defs>
            <marker id="gv-arrow" viewBox="0 0 8 8" refX="7" refY="4"
                    markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0,0 L8,4 L0,8 z" className="fill-strong" />
            </marker>
            <marker id="gv-arrow-on" viewBox="0 0 8 8" refX="7" refY="4"
                    markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M0,0 L8,4 L0,8 z" className="fill-accent" />
            </marker>
            <filter id="gv-halo" x="-70%" y="-70%" width="240%" height="240%">
              <feGaussianBlur stdDeviation="4" />
            </filter>
          </defs>

          {topology.edges.map((e, i) => {
            const a = layout.byId.get(e.source);
            const b = layout.byId.get(e.target);
            if (!a || !b) return null;
            const taken = visited.has(e.source) && visited.has(e.target);
            const x1 = a.x + NODE_W / 2;
            const y1 = a.y + NODE_H;
            const x2 = b.x + NODE_W / 2;
            const y2 = b.y;
            const my = (y1 + y2) / 2;
            const d = `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`;
            return (
              <g key={i}>
                <path
                  d={d}
                  fill="none"
                  strokeWidth={taken ? 1.8 : 1}
                  strokeDasharray={e.conditional ? "4 3" : undefined}
                  opacity={taken ? 0.9 : 0.4}
                  className={taken ? "stroke-accent" : "stroke-strong"}
                  markerEnd={`url(#${taken ? "gv-arrow-on" : "gv-arrow"})`}
                />
                {/* The traversal, drawn on. Delayed by the source's rank so the
                    path appears in the order the run took it. Conditional edges
                    keep their dashes on the base path above, so this overlay is
                    solid and does not fight the dash pattern. */}
                {taken && !e.conditional && (
                  <path
                    d={d}
                    fill="none"
                    strokeWidth={2.4}
                    strokeLinecap="round"
                    className="sc-draw stroke-accent"
                    style={{
                      ["--draw-length" as string]: "200",
                      animationDelay: `${a.rank * 120}ms`,
                    }}
                    opacity={0.55}
                  />
                )}
              </g>
            );
          })}

          {layout.placed.map((n) => {
            const terminal = n.id.startsWith("__");
            const isCurrent = n.id === current;
            const wasVisited = visited.has(n.id);
            return (
              <g
                key={n.id}
                className="animate-fade-in"
                style={{ animationDelay: `${n.rank * 120}ms` }}
              >
                {isCurrent && (
                  <rect
                    x={n.x - 3}
                    y={n.y - 3}
                    width={NODE_W + 6}
                    height={NODE_H + 6}
                    rx={8}
                    className="sc-breathe fill-warn"
                    filter="url(#gv-halo)"
                    opacity={0.45}
                  />
                )}
                <rect
                  x={n.x}
                  y={n.y}
                  width={NODE_W}
                  height={NODE_H}
                  rx={terminal ? NODE_H / 2 : 6}
                  strokeWidth={isCurrent ? 2.2 : wasVisited ? 1.6 : 1}
                  className={cn(
                    "transition-[fill,stroke] duration-[var(--dur-base)]",
                    isCurrent
                      ? "fill-warn-soft stroke-warn"
                      : wasVisited
                      ? "fill-accent-soft stroke-accent"
                      : terminal
                      ? "fill-sunken stroke-strong"
                      : "fill-raised stroke-strong"
                  )}
                />
                <text
                  x={n.x + NODE_W / 2}
                  y={n.y + NODE_H / 2 + 4}
                  textAnchor="middle"
                  className={cn(
                    "font-mono text-[11px]",
                    isCurrent
                      ? "fill-warn-text font-semibold"
                      : wasVisited
                      ? "fill-accent-text font-semibold"
                      : "fill-muted"
                  )}
                >
                  {n.id.replace(/^__|__$/g, "")}
                </text>
                {isCurrent && (
                  <text
                    x={n.x + NODE_W / 2}
                    y={n.y - 7}
                    textAnchor="middle"
                    className="fill-warn-text text-[10px] font-bold"
                  >
                    SUSPENDED HERE
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3.5 gap-y-1.5 text-sm text-faint">
        <Swatch fillClass="fill-accent-soft" strokeClass="stroke-accent" label="executed" />
        <Swatch fillClass="fill-warn-soft" strokeClass="stroke-warn" label="suspended here" />
        <Swatch fillClass="fill-raised" strokeClass="stroke-strong" label="not taken" />
        <span className="flex items-center gap-1.5">
          <svg width="22" height="8" aria-hidden="true">
            <line x1="1" y1="4" x2="21" y2="4" className="stroke-strong"
                  strokeDasharray="4 3" />
          </svg>
          conditional
        </span>
      </div>

      {!run && (
        <p className="mt-2 text-sm text-muted">
          Run the correction loop to see which path it takes.
        </p>
      )}
    </Panel>
  );
}

function Swatch({ fillClass, strokeClass, label }: {
  fillClass: string; strokeClass: string; label: string;
}) {
  return (
    <span className="flex items-center gap-1.5">
      <svg width="14" height="10" aria-hidden="true">
        <rect x="1" y="1" width="12" height="8" rx="2"
              className={cn(fillClass, strokeClass)} />
      </svg>
      {label}
    </span>
  );
}
