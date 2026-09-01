/* What one node is, and where to go to do something about it.
 *
 * The quick links are the point. A graph that can show you a connection and
 * never take you to the screen that acts on it is a diagram; this one hands
 * the reader back to the record or the imagery they were already looking at,
 * with the section already scrolled to.
 *
 * Four of the seven domains have no such screen, because four of them are
 * generated data with no counterpart in the product record. Those say so
 * rather than offering a link into a panel that will not mention what was
 * clicked - see DOMAIN_SECTION.
 */

import type { KgEdge, KgNode } from "../../api";
import { fmt } from "../../api";
import { Badge, Button, EmptyState, cn } from "../../ui";
import { DOMAIN_LABEL, DOMAIN_SECTION, DOMAIN_TEXT, labelNoun } from "./domains";

/** Properties nobody needs to read in a panel: the graph's own bookkeeping,
 *  and the two that are already the heading. */
const HIDDEN = new Set([
  "kgId", "kgLabel", "kgDegree", "loadedAt", "name", "id",
  "requiredMedia", "missingMedia",
]);

export interface GraphSidePanelProps {
  node: KgNode | null;
  edges: KgEdge[];
  nodesById: Map<string, KgNode>;
  onSelect: (id: string) => void;
  onExpand: (id: string) => void;
  /** Jump the record to one of its own sections. Wired to Product 360's own
   *  `jumpTo`, so the link lands where the reader expects. */
  onJumpTo: (section: "findings" | "cause" | "record" | "media") => void;
}

export function GraphSidePanel({
  node, edges, nodesById, onSelect, onExpand, onJumpTo,
}: GraphSidePanelProps) {
  if (!node) {
    return (
      <EmptyState compact title="Nothing selected">
        Click a node to see what it is and what it connects to. Double-click one
        to pull in its own neighbours.
      </EmptyState>
    );
  }

  const touching = edges.filter(
    (edge) => edge.source === node.id || edge.target === node.id);
  const section = DOMAIN_SECTION[node.domain];
  const properties = Object.entries(node.props)
    .filter(([key, value]) =>
      !HIDDEN.has(key) && value !== null && value !== undefined && value !== "")
    .slice(0, 14);

  const missing = node.props.missingMedia as string[] | undefined;

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div>
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-base font-medium leading-snug text-fg">
            {node.name}
          </h3>
          {node.synthetic && (
            <Badge tone="neutral">generated</Badge>
          )}
        </div>
        <p className={cn("mt-0.5 text-xs", DOMAIN_TEXT[node.domain])}>
          {DOMAIN_LABEL[node.domain]} · {labelNoun(node.label)} ·{" "}
          {node.degree} connection{node.degree === 1 ? "" : "s"}
        </p>
      </div>

      {node.synthetic && (
        <p className="rounded-sm border border-subtle bg-sunken px-2.5 py-2
                      text-xs leading-relaxed text-muted">
          This domain has no source data in the catalogue. Everything on this
          node is generated from the seed, and is here so the shape of the
          question is visible — not as a figure to act on.
        </p>
      )}

      {missing && missing.length > 0 && (
        <div className="rounded-sm border border-warn-border bg-warn-soft
                        px-2.5 py-2">
          <p className="text-xs leading-relaxed text-warn-text">
            Missing {missing.join(" and ")} — this category cannot launch
            without {missing.length === 1 ? "it" : "them"}.
          </p>
        </div>
      )}

      {properties.length > 0 && (
        <dl className="grid grid-cols-[minmax(0,auto)_minmax(0,1fr)] gap-x-3
                       gap-y-1 text-xs">
          {properties.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="truncate text-faint">{humanise(key)}</dt>
              <dd className="min-w-0 break-words font-mono text-2xs text-fg">
                {fmt.value(value as never)}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {section && (
        <div className="flex flex-wrap gap-2">
          <Button size="xs" tone="subtle" onClick={() => onJumpTo(section)}>
            {section === "media" ? "Open Imagery" : "Open the record"}
          </Button>
          <Button size="xs" onClick={() => onExpand(node.id)}>
            Expand this node
          </Button>
        </div>
      )}
      {!section && (
        <div className="flex flex-wrap gap-2">
          <Button size="xs" onClick={() => onExpand(node.id)}>
            Expand this node
          </Button>
          <span className="self-center text-2xs text-faint">
            No record section — this domain is not part of launch readiness.
          </span>
        </div>
      )}

      <div className="min-h-0 flex-1">
        <p className="mb-1 text-2xs uppercase tracking-caps text-faint">
          Connected to
        </p>
        <ul className="flex flex-col gap-0.5">
          {touching.slice(0, 24).map((edge) => {
            const otherId = edge.source === node.id ? edge.target : edge.source;
            const other = nodesById.get(otherId);
            if (!other) return null;
            const outward = edge.source === node.id;
            return (
              <li key={edge.id}>
                <button
                  onClick={() => onSelect(otherId)}
                  className={cn(
                    "flex w-full items-baseline gap-2 rounded-xs px-1.5 py-1",
                    "text-left text-xs hover:bg-hover",
                  )}
                >
                  <span className="shrink-0 font-mono text-2xs text-faint">
                    {outward ? "→" : "←"}
                  </span>
                  <span className="shrink-0 font-mono text-2xs text-muted">
                    {edge.type.toLowerCase().replace(/_/g, " ")}
                  </span>
                  <span className={cn("min-w-0 flex-1 truncate",
                                      DOMAIN_TEXT[other.domain])}>
                    {other.name}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        {touching.length > 24 && (
          <p className="mt-1 px-1.5 text-2xs text-faint">
            and {touching.length - 24} more
          </p>
        )}
      </div>
    </div>
  );
}

/** `onHandQty` -> `on hand qty`. The graph's property names are camelCase
 *  because Cypher's are; a reader should not have to be. */
function humanise(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/^./, (c) => c.toUpperCase());
}
