import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, subscribe } from "../api";
import type {
  DownstreamView, LifecycleBoard, LifecycleLane, LifecycleProduct,
  LifecycleTimeline,
} from "../api";
import { IconAlert, IconCheck, IconClock, IconRefresh } from "../icons";
import {
  Badge, Button, Code, EmptyState, Panel, Skeleton, Tooltip, cn, useToast,
} from "../ui";
import { PageHeader } from "../app/shell/PageHeader";
import { NARROW_NOTE, verdictBadge } from "./verdict";

/* Product Lifecycle.
 *
 * The view that joins the two halves of the system. Every other section answers
 * a question about one thing - this correction, this product, this run. This
 * one answers "where has everything got to", which is the question somebody
 * asks before they know which of the others to open.
 *
 * The lanes are derived on the server and are deliberately not stored - see
 * sc/lifecycle/stages.py. Nothing in this file decides which lane a product is
 * in, and it must stay that way: a client that could place a product would be
 * a second account of the pipeline, and the first thing it would disagree
 * about is the product somebody just corrected.
 *
 * The three connected applications open from the strip at the top. They are
 * genuinely separate processes on their own ports, embedded rather than
 * reimplemented, because the point being made is that they are separate.
 */

const LANE_TONE: Record<string, string> = {
  DRAFT: "border-l-[color:var(--stage-draft)]",
  WITH_SUPPLIER: "border-l-[color:var(--stage-supplier)]",
  CLEARED: "border-l-[color:var(--stage-cleared)]",
  PUSHED_DOWNSTREAM: "border-l-[color:var(--stage-pushed)]",
  LIVE: "border-l-[color:var(--stage-live)]",
  LATE_CHANGE: "border-l-[color:var(--stage-late)]",
};

const LANE_LABEL: Record<string, string> = {
  DRAFT: "Proposed",
  WITH_SUPPLIER: "With the supplier",
  CLEARED: "Cleared",
  PUSHED_DOWNSTREAM: "Pushed downstream",
  LIVE: "On sale",
  LATE_CHANGE: "Late change",
};

/** The three applications this platform is connected to.
 *
 *  Addresses rather than routes: these are other processes, and writing them
 *  as paths would imply this server could serve them. */
const APPS = [
  {
    id: "vendor",
    label: "Vendor Portal",
    side: "upstream" as const,
    url: "http://127.0.0.1:8110",
    blurb: "Where suppliers send corrections, documents and images.",
  },
  {
    id: "storefront",
    label: "Storefront",
    side: "downstream" as const,
    url: "http://127.0.0.1:8120",
    blurb: "What a shopper sees on the web and the two marketplaces.",
  },
  {
    id: "ops",
    label: "Ops Console",
    side: "downstream" as const,
    url: "http://127.0.0.1:8130",
    blurb: "Print, shelf and search. Freeze windows, errata and the ledger.",
  },
];

export function Lifecycle() {
  const toast = useToast();
  const [board, setBoard] = useState<LifecycleBoard | null>(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<LifecycleProduct | null>(null);
  const [embedded, setEmbedded] = useState<string | null>(null);

  // A monotonic ticket, so a slow early response cannot overwrite a later one.
  // The same guard Product 360 uses, for the same reason.
  const ticket = useRef(0);

  const load = useCallback(async (q: string) => {
    const mine = ++ticket.current;
    setBusy(true);
    try {
      const next = await api.lifecycle({ q });
      if (mine === ticket.current) setBoard(next);
    } catch (error) {
      if (mine === ticket.current) {
        toast.error("Could not read the board", String(error));
      }
    } finally {
      if (mine === ticket.current) setBusy(false);
    }
  }, [toast]);

  useEffect(() => {
    const timer = setTimeout(() => load(query), 220);
    return () => clearTimeout(timer);
  }, [query, load]);

  // A submission or a redaction moves a product between lanes, and both arrive
  // on the same stream every other view already listens to. Coalesced, because
  // a burst of arrivals is one re-read rather than forty.
  useEffect(() => {
    let timer: number | undefined;
    return subscribe((message) => {
      const kind = String((message as { kind?: string }).kind ?? "");
      if (!["events", "signal", "redaction", "commit", "approval"].includes(kind)) {
        return;
      }
      window.clearTimeout(timer);
      timer = window.setTimeout(() => load(query), 700);
    });
  }, [load, query]);

  const lanes = useMemo(
    () => (board?.lanes ?? []).filter((lane) => lane.count > 0 || lane.stage !== "DRAFT"),
    [board],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader
        section="lifecycle"
        actions={
          <>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter by name, SKU or supplier"
              className="h-8 w-64 rounded border border-subtle bg-raised px-2 text-sm text-fg placeholder:text-muted"
            />
            <Button tone="ghost" onClick={() => load(query)} disabled={busy}>
              <IconRefresh /> Refresh
            </Button>
          </>
        }
      />

      <ConnectedApps embedded={embedded} onOpen={setEmbedded} />

      {embedded ? (
        <EmbeddedApp id={embedded} onClose={() => setEmbedded(null)} />
      ) : (
        <div className="flex min-h-0 flex-1 flex-col gap-3">
          {board?.caveat ? (
            <p className="shrink-0 rounded border border-subtle bg-raised px-3 py-2 text-xs text-muted">
              {board.caveat}
            </p>
          ) : null}

          <div className="grid min-h-0 flex-1 gap-3 overflow-x-auto"
               style={{ gridTemplateColumns: `repeat(${lanes.length || 1}, minmax(240px, 1fr))` }}>
            {!board ? (
              <Skeleton className="h-full" />
            ) : (
              lanes.map((lane) => (
                <Lane key={lane.stage} lane={lane} onOpen={setOpen} />
              ))
            )}
          </div>
        </div>
      )}

      {open ? <ProductDrawer product={open} onClose={() => setOpen(null)} /> : null}
    </div>
  );
}

/* --- the connected systems strip ----------------------------------------- */

function ConnectedApps({ embedded, onOpen }: {
  embedded: string | null;
  onOpen: (id: string | null) => void;
}) {
  return (
    <div className="mb-3 flex shrink-0 flex-wrap items-center gap-2 rounded border border-subtle bg-raised px-3 py-2">
      <span className="text-xs font-medium uppercase tracking-wide text-muted">
        Connected systems
      </span>
      {APPS.map((app) => (
        <Tooltip key={app.id} content={`${app.blurb} — ${app.url}`}>
          <Button
            tone={embedded === app.id ? "primary" : "ghost"}
            onClick={() => onOpen(embedded === app.id ? null : app.id)}
          >
            <span className={cn(
              "mr-1.5 inline-block h-1.5 w-1.5 rounded-full",
              app.side === "upstream"
                ? "bg-[color:var(--stage-supplier)]"
                : "bg-[color:var(--stage-live)]",
            )} />
            {app.label}
          </Button>
        </Tooltip>
      ))}
      <span className="ml-auto text-xs text-muted">
        separate processes, reached only over MCP
      </span>
    </div>
  );
}

function EmbeddedApp({ id, onClose }: { id: string; onClose: () => void }) {
  const app = APPS.find((a) => a.id === id)!;
  return (
    <Panel
      title={app.label}
      subtitle={`${app.blurb} Running at ${app.url}.`}
      flush
      actions={
        <>
          <a
            href={app.url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-accent underline"
          >
            open in a tab
          </a>
          <Button tone="ghost" onClick={onClose}>Close</Button>
        </>
      }
      className="min-h-0 flex-1"
    >
      <iframe
        title={app.label}
        src={app.url}
        className="h-full min-h-[520px] w-full border-0 bg-canvas"
      />
    </Panel>
  );
}

/* --- lanes ---------------------------------------------------------------- */

function Lane({ lane, onOpen }: {
  lane: LifecycleLane;
  onOpen: (product: LifecycleProduct) => void;
}) {
  return (
    <div className="flex min-h-0 flex-col rounded border border-subtle bg-raised">
      <div className="shrink-0 border-b border-subtle px-3 py-2">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold text-fg">
            {LANE_LABEL[lane.stage] ?? lane.stage}
          </h2>
          <span className="font-mono text-sm text-muted">{lane.count}</span>
        </div>
        <p className="mt-0.5 text-xs leading-snug text-muted">{lane.description}</p>
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-2">
        {lane.products.length === 0 ? (
          <p className="px-1 py-6 text-center text-xs text-muted">nothing here</p>
        ) : (
          lane.products.map((product) => (
            <Card key={product.product_id} product={product} onOpen={onOpen} />
          ))
        )}
      </div>
    </div>
  );
}

function Card({ product, onOpen }: {
  product: LifecycleProduct;
  onOpen: (product: LifecycleProduct) => void;
}) {
  const badge = verdictBadge(product.verdict, false);
  const skus = product.variants.map((v) => v.sku).filter(Boolean);

  return (
    <button
      onClick={() => onOpen(product)}
      className={cn(
        "w-full rounded border border-subtle border-l-2 bg-canvas p-2.5 text-left",
        "transition-colors hover:border-strong",
        LANE_TONE[product.stage],
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium leading-snug text-fg">
          {product.name}
        </span>
        {product.regulated ? <Badge tone="warn">regulated</Badge> : null}
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-1">
        {skus.slice(0, 3).map((sku) => <Code key={sku}>{sku}</Code>)}
        <span className="text-xs text-muted">{product.supplier}</span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Badge tone={badge.tone}>{badge.label}</Badge>
        {Object.entries(product.listings).map(([status, count]) => (
          <span key={status} className="text-xs text-muted">
            {count} {status.toLowerCase()}
          </span>
        ))}
      </div>

      {product.correction ? (
        <p className="mt-2 flex items-start gap-1.5 rounded bg-[color:var(--stage-late-soft)] px-2 py-1.5 text-xs leading-snug text-fg">
          <IconAlert className="mt-0.5 shrink-0 text-[color:var(--stage-late)]" />
          <span>
            {product.correction.summary}
            {product.correction.awaiting_extraction ? (
              <em className="ml-1 not-italic text-muted">— not yet read</em>
            ) : null}
          </span>
        </p>
      ) : null}

      {product.redactions.length ? (
        <p className="mt-1.5 text-xs text-[color:var(--stage-late)]">
          {product.redactions.length} field(s) held back downstream
        </p>
      ) : null}

      {product.systems.length ? (
        <p className="mt-1.5 truncate text-xs text-muted">
          to fix: {product.systems.join(", ")}
        </p>
      ) : null}
    </button>
  );
}

/* --- the drawer ------------------------------------------------------------ */

function ProductDrawer({ product, onClose }: {
  product: LifecycleProduct;
  onClose: () => void;
}) {
  const [timeline, setTimeline] = useState<LifecycleTimeline | null>(null);
  const [downstream, setDownstream] = useState<DownstreamView | null>(null);

  useEffect(() => {
    let live = true;
    Promise.allSettled([
      api.lifecycleTimeline(product.product_id),
      api.downstream(product.product_id),
    ]).then(([t, d]) => {
      if (!live) return;
      if (t.status === "fulfilled") setTimeline(t.value);
      if (d.status === "fulfilled") setDownstream(d.value);
    });
    return () => { live = false; };
  }, [product.product_id]);

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/40"
      onClick={onClose}
    >
      <aside
        className="flex h-full w-full max-w-2xl flex-col overflow-y-auto border-l border-subtle bg-raised p-4"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-fg">{product.name}</h2>
            <p className="text-sm text-muted">
              {product.category} · {product.supplier} ·{" "}
              {LANE_LABEL[product.stage] ?? product.stage}
            </p>
          </div>
          <Button tone="ghost" onClick={onClose}>Close</Button>
        </div>

        {product.findings.length ? (
          <Panel title="What is holding it" className="mb-3">
            <ul className="space-y-1.5 text-sm">
              {product.findings.map((finding, index) => (
                <li key={index} className="flex items-start gap-2">
                  <IconAlert className="mt-0.5 shrink-0 text-warn" />
                  <span>
                    {finding.detail}
                    {finding.system ? (
                      <em className="ml-1 not-italic text-muted">
                        — {finding.system}
                      </em>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        ) : null}

        <Panel title="Downstream" subtitle="Where it is carried, and what each system is doing with it."
               className="mb-3">
          {!downstream ? <Skeleton className="h-24" /> : (
            <table className="w-full text-sm">
              <tbody>
                {downstream.listings.map((row) => (
                  <tr key={row.listing_id} className="border-b border-subtle last:border-0">
                    <td className="py-1.5 pr-2">
                      <div className="text-fg">{row.channel}</div>
                      <Code>{row.sku}</Code>
                    </td>
                    <td className="py-1.5 pr-2">
                      <Badge tone={row.status === "LIVE" ? "ok"
                                 : row.status === "WITHHELD" ? "danger" : "neutral"}>
                        {row.status.toLowerCase()}
                      </Badge>
                    </td>
                    <td className="py-1.5 text-xs text-muted">
                      {row.recallable ? "recallable" : (
                        <span className="text-danger">
                          cannot be recalled
                          {row.freeze_days ? ` · ${row.freeze_days}-day freeze` : ""}
                        </span>
                      )}
                      {row.redactions.length ? (
                        <div className="text-[color:var(--stage-late)]">
                          {row.redactions.length} field(s) held back
                        </div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {downstream?.obligations.length ? (
            <div className="mt-3 rounded border border-subtle bg-canvas p-2.5">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
                Owed to the world
              </h3>
              {downstream.obligations.map((obligation) => (
                <p key={obligation.id} className="mt-1 text-sm">
                  <Badge tone={obligation.kind === "ERRATUM" ? "danger" : "warn"}>
                    {obligation.kind.toLowerCase()}
                  </Badge>{" "}
                  <span className="text-muted">
                    {obligation.channel_id} · {obligation.attribute_path} · due{" "}
                    {(obligation.due_by ?? "").slice(0, 10)}
                  </span>
                </p>
              ))}
            </div>
          ) : null}
        </Panel>

        <Panel title="What has happened" subtitle="Joined from the tables that each own a part of it." flush>
          {!timeline ? <Skeleton className="h-40" /> : timeline.events.length === 0 ? (
            <EmptyState title="Nothing recorded yet" />
          ) : (
            <ol className="divide-y divide-subtle">
              {timeline.events.slice().reverse().map((event, index) => (
                <li key={index} className="flex items-start gap-2.5 px-3 py-2">
                  <TimelineMark kind={event.kind} />
                  <div className="min-w-0">
                    <div className="text-sm text-fg">{event.title}</div>
                    {event.detail ? (
                      <div className="text-xs leading-snug text-muted">{event.detail}</div>
                    ) : null}
                    <div className="font-mono text-[11px] text-muted">
                      {String(event.at).slice(0, 19).replace("T", " ")}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Panel>

        <p className="mt-3 text-xs text-muted">{NARROW_NOTE}</p>
      </aside>
    </div>
  );
}

function TimelineMark({ kind }: { kind: string }) {
  if (kind === "approval" || kind === "release") {
    return <IconCheck className="mt-0.5 shrink-0 text-ok" />;
  }
  if (kind === "obligation") {
    return <IconAlert className="mt-0.5 shrink-0 text-danger" />;
  }
  if (kind === "ledger") {
    return <IconCheck className="mt-0.5 shrink-0 text-muted" />;
  }
  return <IconClock className="mt-0.5 shrink-0 text-muted" />;
}
