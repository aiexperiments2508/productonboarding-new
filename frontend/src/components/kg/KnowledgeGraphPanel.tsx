/* The Knowledge Graph section of Product 360.
 *
 * **It does not load until asked.** The section renders a button and fetches
 * on click, the way the root-cause panel does. Product 360's own header
 * comment defends the reason: running the expensive thing on every list-row
 * click turned that page from a look into a wait. Projecting and laying out
 * two hundred nodes every time somebody arrows down a product list would undo
 * that decision.
 *
 * **It is bounded, with a way out.** The canvas sits in a fixed-height box
 * because a full-height interactive graph inside a column that scrolls fights
 * the reader for the wheel. The way out is the expand control, which promotes
 * it to a dialog at full viewport - the same escalation the staging page
 * already makes for the other thing too big for this column.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Dialog } from "radix-ui";

import type { KgDomain, KgEdge, KgNeighbourhood, KgNode } from "../../api";
import { api } from "../../api";
import { ArtBroken, ArtNoEvidence } from "../../art/illustrations";
import { IconClose, IconGraph, IconRefresh } from "../../icons";
import {
  Badge, Button, EmptyState, Menu, MenuItem, SegmentedControl, Skeleton,
  Tooltip, cn,
} from "../../ui";
import { GraphCanvas } from "./GraphCanvas";
import { GraphSidePanel } from "./GraphSidePanel";
import { InsightBar } from "./InsightBar";
import {
  DOMAIN_BLURB, DOMAIN_FILL, DOMAIN_LABEL, DOMAIN_ORDER, DOMAIN_STROKE,
} from "./domains";

type Depth = "1" | "2" | "3";

/** How many nodes one view draws before it says it truncated.
 *
 *  Past this the picture stops being a picture. Raising it does not show more
 *  - it shows a hairball - so the way to see more is the domain filter and the
 *  expand gesture, not a bigger number. */
const CAP = 200;

export interface KnowledgeGraphPanelProps {
  /** The variant the record is open on. */
  entityId: string;
  /** Product 360's own section jump, so a quick link lands where expected. */
  onJumpTo: (section: "findings" | "cause" | "record" | "media") => void;
}

export function KnowledgeGraphPanel({
  entityId, onJumpTo,
}: KnowledgeGraphPanelProps) {
  const [asked, setAsked] = useState(false);
  const [graph, setGraph] = useState<KgNeighbourhood | null>(null);
  const [extra, setExtra] = useState<{ nodes: KgNode[]; edges: KgEdge[] }>(
    { nodes: [], edges: [] });
  const [error, setError] = useState<string | null>(null);
  const [depth, setDepth] = useState<Depth>("2");
  const [domains, setDomains] = useState<KgDomain[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [fullScreen, setFullScreen] = useState(false);
  const [fitToken, setFitToken] = useState(0);

  // A different product is a different graph. Asking again is the reader's
  // call, not something that should happen while they scroll past.
  useEffect(() => {
    setAsked(false);
    setGraph(null);
    setExtra({ nodes: [], edges: [] });
    setSelected(null);
    setError(null);
  }, [entityId]);

  const live = useRef(0);
  const load = useCallback(() => {
    const ticket = ++live.current;
    setAsked(true);
    setGraph(null);
    setExtra({ nodes: [], edges: [] });
    setError(null);
    api.productGraph(entityId, {
      depth: Number(depth),
      domains: domains.length ? domains : undefined,
      limit: CAP,
    })
      .then((answer) => {
        if (ticket !== live.current) return;
        setGraph(answer);
        setFitToken((n) => n + 1);
      })
      .catch((e) => { if (ticket === live.current) setError(String(e)); });
  }, [entityId, depth, domains]);

  // Once the reader has asked, the controls act immediately. Re-asking after
  // every depth change is the whole point of the control.
  useEffect(() => { if (asked) load(); }, [asked, depth, domains, load]);

  const nodes = useMemo(
    () => mergeNodes(graph?.nodes ?? [], extra.nodes), [graph, extra]);
  const edges = useMemo(
    () => mergeEdges(graph?.edges ?? [], extra.edges, nodes), [graph, extra, nodes]);
  const byId = useMemo(
    () => new Map(nodes.map((node) => [node.id, node])), [nodes]);

  const expand = useCallback((nodeId: string) => {
    api.kgExpand(nodeId, {
      seen: nodes.map((n) => n.id),
      domains: domains.length ? domains : undefined,
    })
      .then((answer) => {
        setExtra((held) => ({
          nodes: [...held.nodes, ...answer.nodes],
          edges: [...held.edges, ...answer.edges],
        }));
      })
      .catch((e) => setError(String(e)));
  }, [nodes, domains]);

  const toggle = (domain: KgDomain) =>
    setDomains((held) => held.includes(domain)
      ? held.filter((d) => d !== domain) : [...held, domain]);

  const controls = (
    <div className="flex flex-wrap items-center gap-2">
      <SegmentedControl<Depth>
        ariaLabel="How many hops to draw"
        value={depth}
        onChange={setDepth}
        options={[
          { value: "1", label: "1 hop", title: "Only what it touches directly" },
          { value: "2", label: "2 hops", title: "And what those touch" },
          { value: "3", label: "3 hops", title: "As far as this view goes" },
        ]}
      />
      <Menu
        trigger={
          <Button size="xs" tone={domains.length ? "subtle" : "default"}>
            {domains.length
              ? `${domains.length} of 7 domains`
              : "All domains"}
          </Button>
        }
      >
        {DOMAIN_ORDER.map((domain) => (
          <MenuItem key={domain} keepOpen onSelect={() => toggle(domain)}>
            <span className="min-w-0 flex-1 truncate">
              {domains.length === 0 || domains.includes(domain) ? "✓ " : "   "}
              {DOMAIN_LABEL[domain]}
            </span>
          </MenuItem>
        ))}
      </Menu>
      {domains.length > 0 && (
        <Button size="xs" tone="ghost" onClick={() => setDomains([])}>
          clear
        </Button>
      )}
      <Button size="xs" tone="ghost" icon={<IconRefresh size={13} />}
              onClick={() => { setExtra({ nodes: [], edges: [] });
                               setSelected(null);
                               setFitToken((n) => n + 1); load(); }}>
        reset
      </Button>
      <Button size="xs" tone="ghost" onClick={() => setFullScreen(true)}>
        expand
      </Button>
    </div>
  );

  /* --- the three states --------------------------------------------------- */

  if (!asked) {
    return (
      <div className="flex flex-col gap-3">
        <EmptyState
          compact
          title="How this product connects to everything else"
          action={
            <Button icon={<IconGraph size={14} />} onClick={load}>
              Draw the graph
            </Button>
          }
        >
          Its category lineage, the obligations on it, which depots hold it,
          what it earns and who is being told about it — and the paths between
          any two of those. Not drawn until asked, because laying it out on
          every click would make this page a wait rather than a look.
        </EmptyState>
        <InsightBar />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col gap-3">
        <EmptyState art={<ArtBroken />} title="Could not read the graph">
          {error}
        </EmptyState>
        <Button size="sm" onClick={load}>Try again</Button>
      </div>
    );
  }

  if (!graph) {
    return (
      <div className="flex flex-col gap-3">
        {controls}
        <Skeleton className="h-[26rem] w-full" rounded="md" />
      </div>
    );
  }

  if (nodes.length <= 1) {
    return (
      <div className="flex flex-col gap-3">
        {controls}
        <EmptyState art={<ArtNoEvidence />} title="Nothing connected here">
          {domains.length > 0
            ? "No neighbours in the domains you have on. Turn some back on, or "
              + "widen the depth."
            : "This product has no connections in the graph. That is unusual "
              + "enough to be worth checking the reference pack has loaded."}
        </EmptyState>
        <InsightBar />
      </div>
    );
  }

  const canvas = (height: number) => (
    <GraphCanvas
      nodes={nodes}
      edges={edges}
      rootId={graph.root}
      selectedId={selected}
      onSelect={setSelected}
      onExpand={expand}
      fitToken={fitToken}
      height={height}
    />
  );

  const detail = (
    <GraphSidePanel
      node={selected ? byId.get(selected) ?? null : null}
      edges={edges}
      nodesById={byId}
      onSelect={setSelected}
      onExpand={expand}
      onJumpTo={onJumpTo}
    />
  );

  return (
    <div className="flex flex-col gap-3">
      {controls}

      <div className={cn(
        "grid min-h-0 gap-3",
        "lg:grid-cols-[minmax(0,2.2fr)_minmax(220px,1fr)]",
      )}>
        <div className="min-w-0">
          {canvas(400)}
          <Legend graph={graph} shown={nodes.length} />
        </div>
        <div className="min-w-0 rounded-sm border border-subtle bg-canvas p-3">
          {detail}
        </div>
      </div>

      <InsightBar />

      <Dialog.Root open={fullScreen} onOpenChange={setFullScreen}>
        <Dialog.Portal>
          <Dialog.Overlay className={cn(
            "fixed inset-0 z-[var(--z-dialog)] bg-scrim",
            "data-[state=open]:animate-fade-in")} />
          <Dialog.Content className={cn(
            "fixed inset-3 z-[var(--z-dialog)] flex flex-col overflow-hidden",
            "rounded-lg border border-strong bg-overlay shadow-e3",
            "data-[state=open]:animate-scale-in")}>
            <div className="flex items-center justify-between gap-3 border-b
                            border-subtle px-4 py-2.5">
              <div className="min-w-0">
                <Dialog.Title className="text-base font-medium text-fg">
                  {graph.resolved.sku ?? graph.resolved.entity_id}
                </Dialog.Title>
                <Dialog.Description className="text-xs text-muted">
                  {nodes.length} nodes, {edges.length} connections, {depth} hop
                  {depth === "1" ? "" : "s"}
                </Dialog.Description>
              </div>
              <div className="flex items-center gap-2">
                {controls}
                <Dialog.Close asChild>
                  <Button size="sm" tone="ghost" iconOnly aria-label="Close"
                          icon={<IconClose size={15} />} />
                </Dialog.Close>
              </div>
            </div>
            <div className="grid min-h-0 flex-1 gap-3 p-3
                            lg:grid-cols-[minmax(0,3fr)_minmax(260px,1fr)]">
              <div className="flex min-h-0 min-w-0 flex-col">
                <div className="min-h-0 flex-1">{canvas(0 || 640)}</div>
                <Legend graph={graph} shown={nodes.length} />
              </div>
              <div className="min-w-0 overflow-auto rounded-sm border
                              border-subtle bg-canvas p-3">
                {detail}
              </div>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}

/** The key, drawn the way the canvas draws.
 *
 *  Each swatch is the same shape and colour the diagram uses, so the legend is
 *  a sample of the picture rather than an approximation that can drift from
 *  it - the rule the estate map's legend already states. */
function Legend({ graph, shown }: { graph: KgNeighbourhood; shown: number }) {
  const dropped = Object.entries(graph.dropped_domains ?? {})
    .filter(([, n]) => n > 0);

  return (
    <div className="mt-2 flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5
                      text-2xs text-faint">
        {DOMAIN_ORDER.map((domain) => (
          <Tooltip key={domain} content={DOMAIN_BLURB[domain]}>
            <span className="flex items-center gap-1.5 whitespace-nowrap">
              <svg width="14" height="14" aria-hidden="true" className="shrink-0">
                {domain === "CORE" ? (
                  <rect x="3" y="3" width="8" height="8" rx="2"
                        className={cn(DOMAIN_FILL[domain], DOMAIN_STROKE[domain])}
                        fillOpacity={0.82} strokeWidth={1.2} />
                ) : (
                  <circle cx="7" cy="7" r="4.5"
                          className={cn(DOMAIN_FILL[domain], DOMAIN_STROKE[domain])}
                          fillOpacity={0.82} strokeWidth={1.2} />
                )}
              </svg>
              {DOMAIN_LABEL[domain]}
            </span>
          </Tooltip>
        ))}
        <span className="flex items-center gap-1.5 whitespace-nowrap">
          <svg width="14" height="14" aria-hidden="true" className="shrink-0">
            <circle cx="7" cy="7" r="4.5" fill="none" strokeWidth={1.2}
                    strokeDasharray="3 2" className="stroke-strong" />
          </svg>
          generated, not the retailer&rsquo;s data
        </span>
      </div>

      <p className="text-2xs text-faint">
        Squares are the product spine; size is how connected a node is inside
        this view. {shown} of {graph.total_nodes} drawn
        {graph.backend === "memory"
          ? ", walked in process"
          : ", answered by Neo4j"}.
      </p>

      {dropped.length > 0 && (
        <p className="flex flex-wrap items-center gap-1.5 text-2xs text-faint">
          <Badge tone="warn">capped at {CAP}</Badge>
          Left out:{" "}
          {dropped
            .sort((a, b) => b[1] - a[1])
            .map(([domain, n]) => `${n} ${DOMAIN_LABEL[domain as KgDomain]}`)
            .join(", ")}
          . Narrow the domains or the depth rather than raising the cap — past
          two hundred the picture stops being one.
        </p>
      )}
    </div>
  );
}

/** Merge without duplicating. An expansion can return a node already drawn. */
function mergeNodes(base: KgNode[], added: KgNode[]): KgNode[] {
  const seen = new Map(base.map((node) => [node.id, node]));
  for (const node of added) if (!seen.has(node.id)) seen.set(node.id, node);
  return [...seen.values()];
}

/** Edges, deduplicated, and only where both ends are actually drawn. A line to
 *  a node that is not on screen is a line to nowhere. */
function mergeEdges(base: KgEdge[], added: KgEdge[], nodes: KgNode[]): KgEdge[] {
  const present = new Set(nodes.map((node) => node.id));
  const seen = new Map<string, KgEdge>();
  for (const edge of [...base, ...added]) {
    if (present.has(edge.source) && present.has(edge.target)) {
      seen.set(edge.id, edge);
    }
  }
  return [...seen.values()];
}
