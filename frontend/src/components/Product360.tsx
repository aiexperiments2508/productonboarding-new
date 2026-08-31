import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { Facets, Preview, ProductHit, ProductRollup, Readiness } from "../api";
import { IconCheck, IconSpark } from "../icons";
import {
  Badge, Button, Code, Panel, SegmentedControl, Skeleton, SkeletonTable,
  Table, Td, Th, Tooltip, cn, useToast,
} from "../ui";
import { RegulatedTag } from "./common";
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

/** The four things a record is made of, in the order somebody reads them:
 *  what is wrong, why, what we hold, what we are missing a picture of. */
type SectionKey = "findings" | "cause" | "record" | "media";

const SECTIONS: { value: SectionKey; label: string; title: string }[] = [
  { value: "findings", label: "Findings", title: "What has to move before this launches" },
  { value: "cause", label: "Root cause", title: "Why it happened, and who has to fix it" },
  { value: "record", label: "The record", title: "What the estate has said, and who said it" },
  { value: "media", label: "Imagery", title: "What this category cannot launch without" },
];

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

  /* --- moving around one record ------------------------------------------ */

  // A record is now four sections deep - what is wrong with it, why, what the
  // estate holds, and what imagery it needs - and the demo script used to say
  // "scroll down to THE RECORD". An instruction to scroll is a control the
  // page did not have, so here it is.
  const paneRef = useRef<HTMLDivElement | null>(null);
  const sectionRefs = {
    findings: useRef<HTMLDivElement | null>(null),
    cause: useRef<HTMLDivElement | null>(null),
    record: useRef<HTMLDivElement | null>(null),
    media: useRef<HTMLDivElement | null>(null),
  };
  const [section, setSection] = useState<SectionKey>("findings");

  const jumpTo = useCallback((next: SectionKey) => {
    setSection(next);
    sectionRefs[next].current?.scrollIntoView({
      // Follows the viewer's own motion setting, because a page that animates
      // for somebody who asked it not to is worse than one that jumps.
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto" : "smooth",
      block: "start",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Back to the top of the record whenever a different product is chosen -
  // otherwise the pane keeps the last one's scroll position and opens
  // halfway down a record nobody has read the top of yet.
  useEffect(() => {
    paneRef.current?.scrollTo({ top: 0 });
    setSection("findings");
  }, [selected]);

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

      {/* Two panes, and three widths rather than one.
       *
       * There used to be a single `xl:` rule, which meant that below 1280px
       * the two columns stacked inside a shell that does not scroll and then
       * fought each other for one viewport of height. `lg:` splits them a
       * breakpoint earlier, and `2xl:` gives the reading pane the extra room
       * on a wide monitor instead of growing the list - a list is scanned and
       * a record is read, and only one of them benefits from being wider. */}
      <div
        className={cn(
          "grid min-h-0 flex-1 gap-3",
          "lg:grid-cols-[minmax(300px,1fr)_minmax(0,2fr)]",
          "2xl:grid-cols-[minmax(340px,1fr)_minmax(0,2.6fr)]",
        )}
      >
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


        {/* The reading pane. One scroller, and the two things a reviewer needs
         *  at all times - what the verdict is, and what they can do about it -
         *  pinned to the top of it rather than scrolling away with the
         *  evidence they belong to. */}
        <div
          ref={paneRef}
          className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto [&>*]:shrink-0"
        >
          {!readiness && !busy ? (
            <Panel title="Readiness" subtitle="Select a product">
              <p className="py-10 text-center text-sm text-muted">
                Choose a product on the left to see what every system has said
                about it.
              </p>
            </Panel>
          ) : busy || !readiness ? (
            <Panel title="Readiness" subtitle="assessing">
              <Skeleton className="h-40" />
            </Panel>
          ) : (
            <>
              {/* --- the header bar, sticky ------------------------------ */}
              <div
                className={cn(
                  "sticky top-0 z-10 -mx-px rounded-md border border-subtle",
                  "bg-raised px-3 py-2.5 shadow-e1",
                )}
              >
                <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
                  <div className="min-w-0 flex-1">
                    <h2 className="truncate text-md font-semibold text-fg">
                      {readiness.record?.name ?? selected}
                    </h2>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      <Badge tone={badge.tone} dot>{badge.label}</Badge>
                      <Code>{readiness.record?.sku}</Code>
                      {readiness.record?.product.regulated && <RegulatedTag />}
                      <span className="truncate text-xs text-faint">
                        {readiness.findings.length === 0
                          ? "nothing open"
                          : `${readiness.findings.length} open finding${
                              readiness.findings.length === 1 ? "" : "s"}`}
                      </span>
                    </div>
                  </div>

                  {/* Every primary action, in one place, always on screen.
                   *  These used to live in a panel header beside a title that
                   *  truncated, and below a scroll position - so the demo
                   *  script had to tell a presenter where to find the button
                   *  and warn them about the field next to it. */}
                  <div className="flex shrink-0 flex-col items-end gap-1.5">
                    <div className="flex items-center gap-1.5">
                      {narrow && (
                        <Button
                          size="sm"
                          tone="primary"
                          onClick={deepen}
                          loading={deepening}
                          icon={<IconSpark size={13} />}
                        >
                          Run the reading checks
                        </Button>
                      )}
                      <Button
                        size="sm"
                        tone={canStage ? "primary" : "default"}
                        onClick={openPreview}
                        loading={previewBusy}
                        disabled={!canStage}
                      >
                        Open staging page
                      </Button>
                    </div>

                    {/* The name, with a label on it. Unpublished commercial
                     *  content is shown against a name in the ledger, and the
                     *  field that collects it was a 112px box with a
                     *  placeholder - which is why the demo guide had to carry
                     *  a line about forgetting to type one. */}
                    {canStage && (
                      <label className="flex items-center gap-1.5 text-xs text-faint">
                        Viewing as
                        <input
                          value={actor}
                          onChange={(e) => setActor(e.target.value)}
                          aria-label="Who is viewing this unpublished content"
                          placeholder="your name"
                          className={cn(
                            "w-32 rounded-sm border px-2 py-1 text-xs",
                            "bg-canvas text-fg placeholder:text-faint",
                            "focus:outline-none focus:ring-2 focus:ring-focus",
                            actor.trim() ? "border-line" : "border-warn-border",
                          )}
                        />
                      </label>
                    )}
                    {!canStage && (
                      <span className="max-w-[15rem] text-right text-xs text-faint">
                        {readiness.ready && narrow
                          ? "Six checks of nine is a narrower clearance, not a clean one."
                          : "A staging page is offered once the record is ready to launch."}
                      </span>
                    )}
                  </div>
                </div>

                {/* Jump to a section. On a screen a presenter has to drive,
                 *  "scroll down to the record" is an instruction; this is a
                 *  control. */}
                <div className="mt-2.5 flex items-center gap-2 border-t border-subtle pt-2">
                  <SegmentedControl
                    ariaLabel="Jump to a section of this record"
                    value={section}
                    onChange={jumpTo}
                    // Every section, always. A record with nothing open still
                    // has a Findings panel saying so, and a nav that dropped
                    // the entry would leave the panel below it unreachable by
                    // the control that exists to reach it.
                    options={SECTIONS}
                  />
                </div>
              </div>

              {/* --- what is wrong with it ------------------------------- */}
              <div ref={sectionRefs.findings} className="scroll-mt-[9.5rem]">
              <Panel
                title="Findings"
                subtitle={
                  readiness.findings.length === 0
                    ? "nothing open"
                    : "what has to move before this launches"
                }
                tone={readiness.findings.length > 0 ? "warn" : undefined}
              >
                {narrow && (
                  <div
                    className={cn(
                      "mb-3 flex flex-wrap items-center gap-2 rounded-sm",
                      "border border-warn-border bg-warn-soft px-2.5 py-2",
                    )}
                  >
                    <p className="min-w-0 flex-1 text-sm leading-relaxed text-warn-text">
                      {NARROW_NOTE}
                    </p>
                  </div>
                )}

                {readiness.findings.length === 0 ? (
                  <p className="flex items-start gap-2 text-sm leading-relaxed text-muted">
                    <IconCheck size={15} className="mt-0.5 shrink-0 text-ok-text" />
                    {narrow
                      ? "No rule check found anything. The three that read prose "
                        + "have not run."
                      : "Nothing open. Every applicable attribute is held, the "
                        + "imagery this category needs is present, and no claim "
                        + "outruns the record."}
                  </p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {readiness.findings.map((finding) => (
                      <li
                        key={`${finding.check}-${finding.subject}`}
                        className={cn(
                          "rounded-sm border-l-2 bg-sunken px-3 py-2",
                          finding.severity === "BLOCKING"
                            ? "border-danger"
                            : "border-warn",
                        )}
                      >
                        <div className="flex flex-wrap items-baseline gap-2">
                          <Code>{finding.check}</Code>
                          <span className="font-mono text-xs text-faint">
                            {finding.subject}
                          </span>
                          {/* Who has to fix it. A return that names nobody is
                              not a return. */}
                          {finding.system && (
                            <Badge tone="info">{finding.system}</Badge>
                          )}
                          <Tooltip content="The rule or passage this rests on">
                            <span className="ml-auto shrink-0 font-mono text-xs text-faint">
                              {finding.basis}
                            </span>
                          </Tooltip>
                        </div>
                        <p className="mt-1 max-w-prose text-sm leading-relaxed text-muted">
                          {finding.detail}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
              </div>

              {/* --- why it happened, and whose it is --------------------- */}
              {selected && (
                <div ref={sectionRefs.cause} className="scroll-mt-[9.5rem]">
                  <RootCausePanel
                    key={selected}
                    entityId={selected}
                    findings={readiness.findings.length}
                  />
                </div>
              )}

              {/* --- what the estate has said ---------------------------- */}
              {readiness.record && (
                <div ref={sectionRefs.record} className="scroll-mt-[9.5rem]">
                <Panel
                  title="The record"
                  subtitle="What the estate has said, and who said it"
                  flush
                >
                  {/* `Table scroll` rather than a bare `w-full`: a dense table
                   *  with `w-full` and no minimum compresses its columns to
                   *  fit rather than overflowing, which silently squeezes the
                   *  rightmost ones instead of handing them to a scroller.
                   *  With the compliance attributes this record is now twelve
                   *  to eighteen rows across five columns and it shows. */}
                  <Table scroll>
                    <thead>
                      <tr>
                        <Th>Attribute</Th>
                        <Th>Value</Th>
                        <Th>Carried by</Th>
                        <Th>Document</Th>
                        <Th>Notes</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {readiness.record.attributes.map((row) => (
                        <tr key={row.path} className="border-b border-subtle">
                          <Td>
                            <span className="text-fg">{row.label}</span>
                            <span className="mt-0.5 block font-mono text-xs text-faint">
                              {row.path}
                            </span>
                          </Td>
                          <Td>
                            <span className="font-mono text-fg">
                              {String(row.value)}
                              {row.unit ? ` ${row.unit}` : ""}
                            </span>
                          </Td>
                          <Td>
                            {row.system ? (
                              <Badge tone="neutral">{row.system}</Badge>
                            ) : (
                              <span className="text-faint">carrier unknown</span>
                            )}
                          </Td>
                          <Td>
                            <span className="font-mono text-xs text-faint">
                              {row.source ?? ""}
                            </span>
                          </Td>
                          <Td>
                            {/* A disagreement precedence settled is settled,
                                not absent. This used to be a hover tooltip,
                                which meant the half of the record this page
                                was built to show was the half nobody saw. */}
                            {row.superseded.length > 0 && (
                              <div className="flex flex-col gap-0.5">
                                {row.superseded.map((s, i) => (
                                  <span
                                    key={`${row.path}-superseded-${i}`}
                                    className="whitespace-nowrap text-xs text-warn-text"
                                  >
                                    {s.system ?? "unknown"} said{" "}
                                    <span className="font-mono">
                                      {String(s.value)}
                                    </span>
                                  </span>
                                ))}
                              </div>
                            )}
                            {row.defects.length > 0 && (
                              <div className="mt-0.5 flex flex-wrap gap-1">
                                {row.defects.map((d) => (
                                  <Badge key={d} tone="danger">{d}</Badge>
                                ))}
                              </div>
                            )}
                          </Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </Panel>
                </div>
              )}

              {/* --- what the category needs to show ---------------------- */}
              <div ref={sectionRefs.media} className="scroll-mt-[9.5rem]">
              <Panel
                title="Imagery"
                subtitle="What this category cannot launch without"
              >
                <MediaStrip media={readiness.media} />
              </Panel>
              </div>
            </>
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
