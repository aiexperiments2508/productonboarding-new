import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { Facets, Preview, ProductHit, ProductRollup, Readiness } from "../api";
import { IconCheck, IconSpark } from "../icons";
import {
  Badge, Button, Code, Panel, Skeleton, SkeletonTable, Tooltip, cn, useToast,
} from "../ui";
import { PageHeader } from "../app/shell/PageHeader";
import { MediaStrip } from "./MediaStrip";
import { ProductFilters, ProductRollupStrip } from "./ProductFilters";
import type { Filters } from "./ProductFilters";
import { EMPTY_FILTERS } from "./ProductFilters";
import { RootCausePanel } from "./RootCausePanel";
import { StagingDialog } from "./StagingDialog";
import { NARROW_NOTE, tallyVerdicts, verdictBadge } from "./verdict";

/* Product 360.
 *
 * The rest of this system reasons about corrections to things already
 * published. This is the question that comes first and had no home: is this
 * product fit to publish at all.
 *
 * Four things on this screen are deliberate and worth reading the code for.
 *
 * **There is no readiness score.** A product with three open findings is not
 * seventy per cent ready - it is not ready, and the three findings are the
 * thing somebody acts on. A number would invite a threshold and a threshold
 * would invite launching at ninety.
 *
 * **The screen opens on the rule checks alone.** Six of the nine need no model
 * and answer in milliseconds; the other three read a regulation, a piece of
 * internal documentation and the meaning of a sentence, and running them on
 * every click made this page a wait rather than a look. They run when asked.
 * The price of that is stated everywhere it could mislead - see ./verdict.ts,
 * which is the one place allowed to decide whether the word "ready" may be
 * used.
 *
 * **Every finding names a system.** "The data is incomplete" is not something
 * anybody can act on; "the imaging system never sent an ingredient panel" is,
 * because it says who has to fix it. That is what the estate is for, and the
 * root-cause panel is where it pays off.
 *
 * **The preview refuses rather than warns.** A page that renders a blocked
 * product with a banner across the top is a page somebody screenshots.
 */

/** Milliseconds. Long enough that a typed SKU is one request rather than
 *  eleven, short enough that it still feels like typing. Same value the
 *  command palette uses. */
const SEARCH_DEBOUNCE_MS = 220;

export function Product360() {
  const toast = useToast();

  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [hits, setHits] = useState<ProductHit[] | null>(null);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [rollup, setRollup] = useState<ProductRollup | null>(null);
  const [countingBusy, setCountingBusy] = useState(false);

  const [selected, setSelected] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [busy, setBusy] = useState(false);
  /** The reading checks are running for the selected product. */
  const [deepening, setDeepening] = useState(false);

  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);

  // Who is looking. The same thing the approval gate asks for and no more -
  // neither is authenticated, and inventing a login here would protect
  // unpublished copy more carefully than the decision to publish it. What it
  // buys is a name in the ledger against "who saw this before it launched".
  const [actor, setActor] = useState("reviewer");

  /* --- the list ---------------------------------------------------------- */

  // Debounced, with a staleness guard. Every keystroke used to be one request
  // and one full server-side assessment per row, and a fast typist could have
  // an early response land after a later one and overwrite it.
  const live = useRef(0);
  useEffect(() => {
    const ticket = ++live.current;
    const timer = setTimeout(() => {
      api.products({
        q: filters.q, limit: 200,
        suppliers: filters.suppliers, categories: filters.categories,
        start: filters.start, end: filters.end,
        includeUntouched: filters.includeUntouched,
      })
        .then((answer) => {
          if (ticket !== live.current) return;
          setHits(answer.results);
          // Keep the detail pane populated as somebody types. An empty
          // right-hand side beside a full left-hand one reads as a page that
          // failed rather than one waiting.
          setSelected((current) =>
            current && answer.results.some((r) => r.entity_id === current)
              ? current
              : answer.results[0]?.entity_id ?? null);
        })
        .catch((e) => {
          if (ticket === live.current) {
            toast.error("Could not search products", String(e));
          }
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [filters, toast]);

  // The counting question, asked of the same filters as the list. Its own
  // request because it walks every match rather than a page of them.
  const counting = useRef(0);
  useEffect(() => {
    const ticket = ++counting.current;
    setCountingBusy(true);
    const timer = setTimeout(() => {
      api.productSummary({
        q: filters.q, suppliers: filters.suppliers,
        categories: filters.categories,
        start: filters.start, end: filters.end,
        includeUntouched: filters.includeUntouched,
      })
        .then((answer) => { if (ticket === counting.current) setRollup(answer); })
        .catch(() => { if (ticket === counting.current) setRollup(null); })
        .finally(() => { if (ticket === counting.current) setCountingBusy(false); });
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [filters]);

  // What there is to filter by. Read once from the map's facet derivation,
  // which counts the catalog rather than being configured beside it.
  useEffect(() => {
    api.networkMap({ limit: 1 })
      .then((view) => setFacets(view.facets))
      .catch(() => setFacets(null));
  }, []);

  /* --- the selected product ---------------------------------------------- */

  useEffect(() => {
    if (!selected) { setReadiness(null); setPreview(null); return; }
    let cancelled = false;
    setBusy(true);
    setPreview(null);
    setPreviewOpen(false);
    // The rule checks only. This is the change that made the page open: the
    // three reading checks are three model round trips, and they now run when
    // a reviewer asks rather than on every click.
    api.readiness(selected, false)
      .then((r) => { if (!cancelled) setReadiness(r); })
      .catch(() => { if (!cancelled) setReadiness(null); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [selected]);

  /** Run the three checks that need a model, for this product only. */
  const deepen = useCallback(async () => {
    if (!selected) return;
    setDeepening(true);
    try {
      setReadiness(await api.readiness(selected, true));
    } catch (e) {
      toast.error("Could not run the reading checks", String(e));
    } finally {
      setDeepening(false);
    }
  }, [selected, toast]);

  const openPreview = useCallback(async () => {
    if (!selected) return;
    if (!actor.trim()) {
      toast.error("A name is required",
                  "Unpublished content is viewed under a name, the same as an "
                  + "approval decision is taken under one.");
      return;
    }
    // Opened first, filled second. The click has to change something on screen
    // immediately or it reads as a click that did nothing.
    setPreviewOpen(true);
    setPreviewBusy(true);
    setPreview(null);
    try {
      setPreview(await api.preview(selected, actor.trim(), true));
    } catch (e) {
      toast.error("Could not build the staging page", String(e));
      setPreviewOpen(false);
    } finally {
      setPreviewBusy(false);
    }
  }, [actor, selected, toast]);

  const counts = useMemo(() => tallyVerdicts(hits ?? []), [hits]);
  const badge = verdictBadge(readiness?.verdict, readiness?.checks_complete);
  const narrow = readiness != null && !readiness.checks_complete;
  // A staging page is the last surface before publication, and a record
  // cleared by six checks of nine has not been cleared by the three that read
  // the regulation. So it is offered only once the assessment is complete.
  const canStage = Boolean(readiness?.ready && readiness?.checks_complete);

  return (
    <>
      <PageHeader
        section="product360"
        actions={
          <div className="flex items-center gap-2">
            {counts.map((entry) => (
              <Badge key={entry.label} tone={entry.tone} dot>
                {entry.n} {entry.label}
              </Badge>
            ))}
          </div>
        }
      />

      <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(340px,1fr)_minmax(0,2fr)]">
        <div className="flex min-h-0 min-w-0 flex-col gap-3">
          <ProductRollupStrip rollup={rollup} loading={countingBusy} />

          <Panel
            title="Products"
            subtitle={
              rollup ? `${rollup.assessed} in scope` : "Search by SKU, identifier or name"
            }
            flush
            scroll
            className="min-h-0 flex-1"
          >
            <ProductFilters
              filters={filters}
              onChange={setFilters}
              facets={facets}
            />

            {hits === null ? (
              <SkeletonTable rows={8} cols={2} />
            ) : hits.length === 0 ? (
              <p className="p-4 text-sm text-muted">
                Nothing matches these filters.
              </p>
            ) : (
              <ul className="flex flex-col">
                {hits.map((hit) => {
                  const row = verdictBadge(hit.verdict, hit.checks_complete);
                  return (
                    <li key={hit.entity_id}>
                      <button
                        onClick={() => setSelected(hit.entity_id)}
                        className={cn(
                          "flex w-full items-center gap-2 border-b border-subtle",
                          "px-3 py-2 text-left transition-colors",
                          selected === hit.entity_id
                            ? "bg-accent-soft"
                            : "hover:bg-hover",
                        )}
                      >
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm text-fg">
                            {hit.name}
                          </span>
                          <span className="block truncate font-mono text-2xs text-faint">
                            {hit.sku} · {hit.entity_id}
                            {hit.last_seen
                              ? ` · last arrived ${hit.last_seen.slice(0, 10)}`
                              : ""}
                          </span>
                        </span>
                        <Tooltip content={row.label}>
                          <span>
                            <Badge tone={row.tone}>
                              {hit.findings ? `${hit.findings}` : "clear"}
                            </Badge>
                          </span>
                        </Tooltip>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </Panel>
        </div>

        <div className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
          <Panel
            title={readiness?.record?.name ?? "Readiness"}
            subtitle={
              readiness
                ? `${readiness.findings.length} finding(s) · ${badge.label}`
                : "Select a product"
            }
            actions={
              readiness ? (
                <div className="flex items-center gap-1.5">
                  {canStage ? (
                    <>
                      <input
                        value={actor}
                        onChange={(e) => setActor(e.target.value)}
                        aria-label="Who is viewing this unpublished content"
                        placeholder="your name"
                        className={cn(
                          "w-28 rounded-sm border border-line bg-canvas px-2 py-1",
                          "text-xs text-fg placeholder:text-faint",
                          "focus:outline-none focus:ring-2 focus:ring-focus",
                        )}
                      />
                      <Button size="sm" tone="primary" onClick={openPreview}
                              loading={previewBusy}>
                        Open staging page
                      </Button>
                    </>
                  ) : readiness.ready && narrow ? (
                    <Tooltip content="A staging page cleared by six checks of nine is a narrower clearance, not a clean one. Run the reading checks first.">
                      <span>
                        <Button size="sm" disabled>Open staging page</Button>
                      </span>
                    </Tooltip>
                  ) : undefined}
                </div>
              ) : undefined
            }
          >
            {busy || !readiness ? (
              <Skeleton className="h-40" />
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={badge.tone} dot>{badge.label}</Badge>
                  <Code>{readiness.record?.sku}</Code>
                  {readiness.record?.product.regulated && (
                    <Badge tone="warn">regulated</Badge>
                  )}
                </div>

                {/* The admission of narrowness, and the control that ends it,
                    in the same box. An assessment that has found fewer things
                    is narrower rather than cleaner, and the button is the
                    answer to the sentence rather than a feature elsewhere. */}
                {narrow && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 rounded-sm border border-warn-border bg-warn-soft px-2 py-1.5">
                    <p className="min-w-0 flex-1 text-xs text-warn-text">
                      {NARROW_NOTE}
                    </p>
                    <Button size="xs" tone="primary" onClick={deepen}
                            loading={deepening} icon={<IconSpark size={12} />}>
                      Run the reading checks
                    </Button>
                  </div>
                )}

                {/* What imagery this category needs, and what turned up. */}
                <div className="mt-3">
                  <MediaStrip media={readiness.media} compact />
                </div>

                {readiness.findings.length === 0 ? (
                  <p className="mt-3 flex items-center gap-2 text-sm text-muted">
                    <IconCheck size={14} className="text-ok-text" />
                    {narrow
                      ? "No rule check found anything. The three that read "
                        + "prose have not run."
                      : "Nothing open. Every applicable attribute is held, the "
                        + "imagery this category needs is present, and no claim "
                        + "outruns the record."}
                  </p>
                ) : (
                  <ul className="mt-3 flex flex-col gap-1.5">
                    {readiness.findings.map((finding) => (
                      <li
                        key={`${finding.check}-${finding.subject}`}
                        className={cn(
                          "rounded-sm border-l-2 bg-sunken px-2 py-1.5",
                          finding.severity === "BLOCKING"
                            ? "border-danger"
                            : "border-warn",
                        )}
                      >
                        <div className="flex flex-wrap items-baseline gap-2">
                          <Code>{finding.check}</Code>
                          <span className="font-mono text-2xs text-faint">
                            {finding.subject}
                          </span>
                          {/* Who has to fix it. A return that names nobody is
                              not a return. */}
                          {finding.system && (
                            <Badge tone="info">{finding.system}</Badge>
                          )}
                          <Tooltip content="The rule or passage this rests on">
                            <span className="ml-auto shrink-0 font-mono text-2xs text-faint">
                              {finding.basis}
                            </span>
                          </Tooltip>
                        </div>
                        <p className="mt-0.5 text-xs text-muted">
                          {finding.detail}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}

                {selected && (
                  <RootCausePanel
                    key={selected}
                    entityId={selected}
                    findings={readiness.findings.length}
                  />
                )}
              </>
            )}
          </Panel>

          {readiness?.record && (
            <Panel
              title="The record"
              subtitle="What the estate has said, and who said it"
              flush
              scroll
              className="max-h-[46vh]"
            >
              <table className="w-full text-xs">
                <tbody>
                  {readiness.record.attributes.map((row) => (
                    <tr key={row.path} className="border-b border-subtle">
                      <td className="px-3 py-1.5 text-muted">{row.label}</td>
                      <td className="px-3 py-1.5 font-mono text-fg">
                        {String(row.value)}
                        {row.unit ? ` ${row.unit}` : ""}
                      </td>
                      <td className="px-3 py-1.5">
                        {row.system ? (
                          <Badge tone="neutral">{row.system}</Badge>
                        ) : (
                          <span className="text-faint">carrier unknown</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-2xs text-faint">
                        {row.source ?? ""}
                      </td>
                      <td className="px-3 py-1.5">
                        {/* A disagreement precedence settled is settled, not
                            absent. Hiding the loser would make the record look
                            like everybody agreed. */}
                        {row.superseded.length > 0 && (
                          <Tooltip
                            content={row.superseded
                              .map((s) => `${s.system ?? "unknown"} said ${String(s.value)}`)
                              .join("; ")}
                          >
                            <span>
                              <Badge tone="warn">
                                {row.superseded.length} superseded
                              </Badge>
                            </span>
                          </Tooltip>
                        )}
                        {row.defects.map((d) => (
                          <Badge key={d} tone="danger">{d}</Badge>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </div>
      </div>

      <StagingDialog
        open={previewOpen}
        onOpenChange={(open) => { if (!open) setPreviewOpen(false); }}
        preview={preview}
        loading={previewBusy}
        title={readiness?.record?.name ?? selected ?? "this product"}
      />
    </>
  );
}
