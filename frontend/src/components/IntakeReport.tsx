import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { BatchProduct, BatchReport, BatchRow, FixableGap } from "../api";
import { IconAlert, IconDoc, IconSpark } from "../icons";
import { PageHeader } from "../app/shell/PageHeader";
import {
  Badge, Button, Code, EmptyState, LoadingBody, Panel, SkeletonKpis,
  SkeletonTable, Tab, TabList, TabPanel, Table, Tabs, Tooltip, cn, useToast,
} from "../ui";
import { ArtAllClear, ArtQuietFeed } from "../art/illustrations";
import { Kpi } from "./common";
import { NARROW_NOTE, verdictBadge } from "./verdict";

/* Supplier Intake.
 *
 * What one archive turned out to contain, and how much of it can be sold.
 *
 * Three numbers are what somebody came for - cleared, back to source, blocked -
 * and a fourth that is more interesting than any of them: how many of the gaps
 * could be closed from a document the retailer already holds, rather than by
 * writing to the supplier and waiting a fortnight.
 *
 * Two rules this screen must not break, both inherited rather than invented:
 *
 *   the word "ready"  is `verdict.ts`'s to give. A batch assessed without a
 *                     model has been through seven checks of ten, and calling
 *                     that clear would be the same omission on forty products
 *                     at once - which is worse, because a number on a summary
 *                     gets repeated by people who never opened a product.
 *
 *   "can be fixed"    is two different claims and they are counted separately.
 *                     A *candidate* is a gap with a source passage on file,
 *                     which is deterministic and provable: `enrich` refuses any
 *                     fill it cannot cite, so no passage means no fill. Whether
 *                     that passage actually states the value is a reading
 *                     question, and until the sources have been read this
 *                     screen says "could be" and not "will be".
 *
 * Nothing here computes a verdict, a count or a bucket. Every figure is one
 * the server already reached with the same arithmetic the product summary uses.
 */

const STATE_LABEL: Record<FixableGap["state"], string> = {
  CANDIDATE: "a source passage is on file",
  NO_SOURCE: "nothing to read it from",
  SAFETY_HELD: "safety - the supplier sends this",
};

type TabId = "summary" | "products" | "fixable";

export function IntakeReport({ batchId, onOpenBatch }: {
  batchId?: string | null;
  onOpenBatch?: (id: string) => void;
}) {
  const toast = useToast();
  const [batches, setBatches] = useState<BatchRow[] | null>(null);
  const [selected, setSelected] = useState<string | null>(batchId ?? null);
  const [report, setReport] = useState<BatchReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<TabId>("summary");
  const [actor, setActor] = useState("");
  const [fixing, setFixing] = useState(false);

  useEffect(() => {
    api.batches()
      .then((r) => {
        setBatches(r.batches);
        setSelected((current) => current ?? r.batches[0]?.batch_id ?? null);
      })
      .catch(() => setBatches([]));
  }, []);

  useEffect(() => {
    if (batchId) setSelected(batchId);
  }, [batchId]);

  const load = useCallback((id: string) => {
    setLoading(true);
    api.batchReport(id)
      .then(setReport)
      .catch((e) => toast.error("Could not read the batch", String(e)))
      .finally(() => setLoading(false));
  }, [toast]);

  useEffect(() => {
    if (selected) load(selected);
  }, [selected, load]);

  const applyFixes = useCallback(() => {
    if (!selected || !actor.trim()) return;
    setFixing(true);
    api.batchFix(selected, { actor: actor.trim() })
      .then((result) => {
        const { filled, requested } = result.counts;
        if (!result.gateway.reachable) {
          toast.error(
            "No model was available",
            "Nothing was filled, and every gap has become a request to the "
            + "supplier. That is the same answer the pipeline gives when the "
            + "gateway is down - it does not guess.");
        } else {
          toast.notify(
            `${filled} filled, ${requested} sent back to the supplier`,
            "Every filled value is recorded as inferred, with the passage it "
            + "was read from. Nothing has been published.");
        }
        load(selected);
      })
      .catch((e) => toast.error("Could not apply the fills", String(e)))
      .finally(() => setFixing(false));
  }, [selected, actor, toast, load]);

  const current = useMemo(
    () => batches?.find((b) => b.batch_id === selected) ?? null,
    [batches, selected]);

  if (batches !== null && batches.length === 0) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <PageHeader section="intake" />
        {/* Centred in the space rather than stacked at the top of it: an empty
            state pushed against the header reads as a paragraph that failed to
            load, not as a screen waiting for something to arrive. */}
        <EmptyState
          className="min-h-0 flex-1"
          art={<ArtQuietFeed />}
          title="No supplier has sent a batch yet"
        >
          A supplier downloads a template from the Vendor Portal, fills it in,
          and sends it back as one archive with its photographs. The rows arrive
          on the live feed in the Ingest Fabric, and the report appears here.
        </EmptyState>
      </div>
    );
  }

  return (
    /* This section owns its height and never lengthens the page.
     *
     * The shell's <main> is `overflow-hidden` on purpose - see the note in
     * App.tsx. A section that hands it a taller-than-viewport column does not
     * get a scrollbar, it gets silently clipped, and the bottom of a
     * forty-product list becomes unreachable.
     *
     * The title, the four figures and the tab bar are pinned; only the tab
     * contents scroll. Letting the summary scroll with them was worse than it
     * sounds: on a normal screen there is about thirty pixels of overflow, so
     * the wheel barely moves - but thirty pixels is exactly enough to slice
     * the top off the summary card, leaving a bordered box with no header. It
     * read as broken while behaving correctly.
     *
     * Pinning it needs a floor, or it fails the other way. `flex-1` on the tab
     * set resolves to zero when the viewport is shorter than the chrome above
     * it, and the contents vanish rather than overflow. So `Tabs fill` carries
     * `min-h-[20rem]`, and the column below is a scroller of last resort: on a
     * short screen the whole section scrolls instead of collapsing. */
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader
        section="intake"
        actions={
          batches && batches.length > 1 ? (
            <select
              aria-label="Which batch to report on"
              className={cn(
                "rounded-md border border-subtle bg-raised px-2 py-1 text-sm",
                "transition-colors duration-[var(--dur-fast)] ease-standard",
                "hover:border-strong"
              )}
              value={selected ?? ""}
              onChange={(e) => { setSelected(e.target.value); onOpenBatch?.(e.target.value); }}
            >
              {batches.map((b) => (
                <option key={b.batch_id} value={b.batch_id}>
                  {b.supplier} — {b.file?.filename ?? b.batch_id} ({b.entities.length})
                </option>
              ))}
            </select>
          ) : undefined
        }
      />

      {/* The scroller of last resort. Idle at any normal height - the tab
          panel does the scrolling - and the reason a short window degrades to
          a scrollbar instead of to an empty screen. */}
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      {loading && !report ? (
        /* Shaped like the thing that replaces it - a row of figures over a
           table - so the screen does not rearrange itself the moment the
           report lands. A single grey slab would. */
        <LoadingBody label="Reading the batch">
          <div className="flex flex-col gap-3">
            <SkeletonKpis count={4} />
            <SkeletonTable rows={8} cols={4} />
          </div>
        </LoadingBody>
      ) : report ? (
        <>
          <Headline report={report} current={current} />

          <Tabs fill value={tab} onValueChange={(v) => setTab(v as TabId)}>
            <TabList ariaLabel="Views of this batch">
              <Tab value="summary">Summary</Tab>
              <Tab value="products" count={report.products.length}>Products</Tab>
              <Tab value="fixable" count={report.fixable.candidates}>
                What AI could fix
              </Tab>
            </TabList>

            <TabPanel value="summary" scroll>
              <Summary report={report} />
            </TabPanel>

            <TabPanel value="products" scroll>
              <Products report={report} />
            </TabPanel>

            <TabPanel value="fixable" scroll>
              <Fixable
                report={report}
                actor={actor}
                setActor={setActor}
                busy={fixing}
                onApply={applyFixes}
              />
            </TabPanel>
          </Tabs>
        </>
      ) : null}
      </div>
    </div>
  );
}

/* --- the three numbers ---------------------------------------------------- */

function Headline({ report, current }: {
  report: BatchReport; current: BatchRow | null;
}) {
  const t = report.totals;
  return (
    <Panel
      className="mb-3 shrink-0"
      title={`${report.supplier} sent ${t.assessed} product${t.assessed === 1 ? "" : "s"}`}
      subtitle={
        current?.file
          ? `${current.file.filename} · ${Math.round(current.file.bytes / 1024)} KB · ${report.doc_ref}`
          : report.doc_ref
      }
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Kpi
          label="Went through clean"
          value={t.cleared}
          tone="good"
          sub={report.checks_complete
            ? "no findings against any check"
            : "no findings against the checks that ran"}
        />
        <Kpi
          label="Back to the source"
          value={t.returned}
          sub="something is missing or will not parse"
        />
        <Kpi
          label="Blocked"
          value={t.blocked}
          tone={t.blocked ? "bad" : undefined}
          sub="may not be sold as it stands"
        />
        <Kpi
          label="A source is on file"
          value={report.fixable.candidates}
          sub={`of ${report.fixable.gaps.length} gaps — could be read from a document we hold`}
        />
      </div>

      {report.proposals.length > 0 && (
        <p className="mt-3 border-l-2 border-accent-border pl-3 text-sm text-muted">
          <strong className="text-default">
            {report.proposals.length} more row
            {report.proposals.length === 1 ? " is" : "s are"}
          </strong>{" "}
          proposed new lines, and {report.proposals.length === 1 ? "is" : "are"}{" "}
          not counted above. The catalogue does not take a line until a reviewer
          accepts it, so there is nothing to assess yet — they are waiting in
          Product Lifecycle.
        </p>
      )}

      {!report.checks_complete && (
        <p className="mt-3 border-l-2 border-warn-border pl-3 text-sm text-muted">
          {report.caveat ?? NARROW_NOTE}
        </p>
      )}
    </Panel>
  );
}

/* --- summary -------------------------------------------------------------- */

function Summary({ report }: { report: BatchReport }) {
  const t = report.totals;
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {report.proposals.length > 0 && (
        <Panel
          className="lg:col-span-2"
          title="Lines we do not have yet"
          subtitle="held as proposals until a reviewer accepts them"
        >
          <Table>
            <thead>
              <tr>
                <th>Proposed</th>
                <th>Category</th>
                <th>Reference</th>
              </tr>
            </thead>
            <tbody>
              {report.proposals.map((p) => (
                <tr key={p.submission_id}>
                  <td>{p.name}</td>
                  <td className="text-muted">{p.category}</td>
                  <td><Code>{p.draft_id}</Code></td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
      <Panel title="What is missing" subtitle="by the check that found it">
        {t.by_check.length === 0 ? (
          <EmptyState art={<ArtAllClear />} title="Nothing to fix">
            Every product in this batch passed every check that ran.
          </EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <th>Check</th>
                <th className="text-right">Products</th>
                <th className="text-right">Findings</th>
              </tr>
            </thead>
            <tbody>
              {t.by_check.map((row) => (
                <tr key={row.check}>
                  <td><Code>{row.check}</Code></td>
                  <td className="text-right tabular-nums">{row.products}</td>
                  <td className="text-right tabular-nums">{row.findings}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <Panel
        title="Who has to fix it"
        subtitle="the system that supplied the problem, and the team that owns it"
      >
        {t.by_system.length === 0 ? (
          <p className="p-3 text-sm text-muted">Nothing is owed by anybody.</p>
        ) : (
          <Table>
            <thead>
              <tr>
                <th>System</th>
                <th>Owner</th>
                <th className="text-right">Products</th>
              </tr>
            </thead>
            <tbody>
              {t.by_system.map((row) => (
                <tr key={row.system}>
                  <td><Code>{row.system}</Code></td>
                  <td className="text-muted">{row.owner ?? "—"}</td>
                  <td className="text-right tabular-nums">{row.products}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <Panel title="By category" className="lg:col-span-2">
        <Table>
          <thead>
            <tr>
              <th>Category</th>
              <th className="text-right">Assessed</th>
              <th className="text-right">Cleared</th>
              <th className="text-right">Back to source</th>
              <th className="text-right">Blocked</th>
            </tr>
          </thead>
          <tbody>
            {t.by_category.map((row) => (
              <tr key={row.prefix}>
                <td>{row.label}</td>
                <td className="text-right tabular-nums">{row.assessed}</td>
                <td className="text-right tabular-nums">{row.cleared}</td>
                <td className="text-right tabular-nums">{row.returned}</td>
                <td className="text-right tabular-nums">{row.blocked}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Panel>
    </div>
  );
}

/* --- products ------------------------------------------------------------- */

function Products({ report }: { report: BatchReport }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Panel flush title="Every product in the batch, in the order it was sent">
      <div className="divide-y divide-subtle">
        {report.products.map((p) => (
          <ProductRow
            key={p.entity_id}
            product={p}
            complete={report.checks_complete}
            open={open === p.entity_id}
            onToggle={() => setOpen(open === p.entity_id ? null : p.entity_id)}
          />
        ))}
      </div>
    </Panel>
  );
}

function ProductRow({ product, complete, open, onToggle }: {
  product: BatchProduct; complete: boolean; open: boolean;
  onToggle: () => void;
}) {
  const badge = verdictBadge(product.verdict, complete);
  return (
    <div>
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-3 py-2 text-left transition-colors hover:bg-hover"
      >
        <span className="w-8 shrink-0 text-right font-mono text-xs text-faint tabular-nums">
          {product.ordinal}
        </span>
        <Code className="shrink-0">{product.sku}</Code>
        <span className="min-w-0 flex-1 truncate text-sm">{product.name}</span>
        {product.gaps > 0 && (
          <Badge tone="neutral">
            {product.gaps} gap{product.gaps === 1 ? "" : "s"}
          </Badge>
        )}
        <Badge tone={badge.tone} dot={badge.narrow}>{badge.label}</Badge>
      </button>
      {open && (
        <div className="border-t border-subtle bg-sunken px-3 py-2">
          {product.findings.length === 0 ? (
            <p className="text-sm text-muted">
              Nothing was found against the checks that ran.
            </p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {product.findings.map((f, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  {f.severity === "BLOCKING"
                    ? <IconAlert size={14} className="mt-0.5 shrink-0 text-danger-text" />
                    : <IconDoc size={14} className="mt-0.5 shrink-0 text-faint" />}
                  <span>
                    {f.detail}
                    {f.system && (
                      <span className="ml-1 text-muted">
                        — <Code>{f.system}</Code> has to fix it
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

/* --- what AI could fix ---------------------------------------------------- */

function Fixable({ report, actor, setActor, busy, onApply }: {
  report: BatchReport; actor: string; setActor: (v: string) => void;
  busy: boolean; onApply: () => void;
}) {
  const { gaps, candidates, held_safety, no_source } = report.fixable;
  const grouped = useMemo(() => {
    const order: FixableGap["state"][] = ["CANDIDATE", "SAFETY_HELD", "NO_SOURCE"];
    return order
      .map((state) => ({ state, rows: gaps.filter((g) => g.state === state) }))
      .filter((g) => g.rows.length > 0);
  }, [gaps]);

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="What a model could close, and what it may not"
        tone={candidates ? "accent" : undefined}
      >
        <p className="text-sm text-muted">
          {report.fixable.label}
        </p>
        <div className="mt-3 grid grid-cols-3 gap-3">
          <Kpi label="A source is on file" value={candidates} />
          <Kpi label="Held — safety class" value={held_safety} />
          <Kpi label="Nothing to read it from" value={no_source} />
        </div>

        {candidates > 0 && (
          <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-subtle pt-3">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted">Who is asking</span>
              <input
                value={actor}
                onChange={(e) => setActor(e.target.value)}
                placeholder="your name"
                className="rounded-md border border-subtle bg-raised px-2 py-1"
              />
            </label>
            <Button
              onClick={onApply}
              disabled={busy || !actor.trim()}
              icon={<IconSpark size={14} />}
            >
              {busy ? "Reading the sources…" : "Read the sources and fill what can be cited"}
            </Button>
            <p className="w-full text-sm text-muted">
              Every value filled is recorded as <em>inferred</em>, with the
              passage it was read from beside it. A gap whose passage turns out
              not to state the value becomes a request to the supplier rather
              than a guess. <strong>Nothing is published</strong> — a product
              with no findings left is ready to launch, and launching it still
              needs a reviewer.
            </p>
          </div>
        )}
      </Panel>

      {grouped.map(({ state, rows }) => (
        <Panel
          key={state}
          flush
          title={STATE_LABEL[state]}
          subtitle={`${rows.length} gap${rows.length === 1 ? "" : "s"}`}
        >
          <Table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Field</th>
                <th>Why</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((g, i) => (
                <tr key={`${g.entity_id}-${g.attribute_path}-${i}`}>
                  <td><Code>{g.entity_id}</Code></td>
                  <td>
                    <Code>{g.attribute_path}</Code>
                    {g.safety_class && (
                      <Badge tone="danger" className="ml-1.5">safety</Badge>
                    )}
                  </td>
                  <td className="max-w-[28rem] text-muted">{g.why}</td>
                  <td>
                    {g.citation ? (
                      <Tooltip content={g.citation.heading ?? g.citation.doc_id}>
                        <Code>{g.citation.doc_id}</Code>
                      </Tooltip>
                    ) : (
                      <span className="text-faint">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        </Panel>
      ))}
    </div>
  );
}
