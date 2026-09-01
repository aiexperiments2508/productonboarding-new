import { useCallback, useEffect, useMemo, useState } from "react";
import { api, streamBatchAssess } from "../api";
import type {
  AutonomyThreshold, BatchReport, BatchRow, Suggestion,
} from "../api";
import { IconSpark } from "../icons";
import { PageHeader } from "../app/shell/PageHeader";
import {
  Button, Code, EmptyState, LoadingBody, Panel, SkeletonKpis, SkeletonTable,
  Tab, TabList, TabPanel, Tabs, cn, useToast,
} from "../ui";
import { ArtQuietFeed } from "../art/illustrations";
import { Kpi } from "./common";
import { NARROW_NOTE } from "./verdict";
import { GateTab } from "./onboarding/GateTab";
import { OnboardingTab } from "./onboarding/OnboardingTab";
import { SuggestionsTab } from "./onboarding/SuggestionsTab";
import { DecisionsTab } from "./onboarding/DecisionsTab";

/* Supplier Intake.
 *
 * What one archive turned out to contain, staged the way a product actually
 * moves through the factory:
 *
 *   compliance   may we onboard this at all? Regulation and the retailer's own
 *                policy, checked before anything looks at the record. A product
 *                that fails goes back to its supplier and nothing downstream is
 *                spent on it.
 *   onboarding   is the record complete? Only products that cleared the gate.
 *   suggestions  what could close each gap, and how sure we are - composed from
 *                a passage a model read, the rest of the catalog, and the
 *                reviewer's own past decisions.
 *   decisions    the ones a person has to answer, with the evidence open.
 *
 * The staging is the point of the screen. The previous version ran every check
 * at once and counted the findings, which meant a withdrawal notice and a
 * missing net-content arrived as two rows in one list - and the obvious next
 * action on both of them was to go and find the missing data.
 *
 * Three rules this screen must not break, all inherited rather than invented:
 *
 *   the word "ready"  is `verdict.ts`'s to give. A batch assessed without a
 *                     model has been through seven checks of eleven, and calling
 *                     that clear would be the same omission on forty products
 *                     at once.
 *
 *   "can be fixed"    is two different claims and they are counted separately.
 *                     A *candidate* is a gap with a source passage on file,
 *                     which is deterministic and provable. Whether that passage
 *                     states the value is a reading question.
 *
 *   the confidence    is composed from named parts and is never the model's own
 *                     number. The parts are on the row, because the score is
 *                     what decides whether anybody looks at the value.
 *
 * Nothing here computes a verdict, a count, a score or a bucket. Every figure is
 * one the server already reached.
 */

type TabId = "gate" | "onboarding" | "suggestions" | "decisions";

/** What each decision is called once it has happened.
 *
 *  Spelled out rather than derived. Appending "d" to the verb gives
 *  "rectifyd" and "rejectd", which is the kind of thing a reader assumes is a
 *  bug in the record rather than in the label. */
const DECIDED_LABEL = {
  APPROVE: "approved",
  REJECT: "rejected",
  RECTIFY: "corrected",
} as const;

/** What the threshold is until the server has said. Only ever on screen for the
 *  moment before the first read answers; the server is the authority, and every
 *  row also carries the threshold it was actually judged against. */
const ASSUMED_THRESHOLD = 0.95;

export function IntakeReport({ batchId, onOpenBatch }: {
  batchId?: string | null;
  onOpenBatch?: (id: string) => void;
}) {
  const toast = useToast();
  const [batches, setBatches] = useState<BatchRow[] | null>(null);
  const [selected, setSelected] = useState<string | null>(batchId ?? null);
  const [report, setReport] = useState<BatchReport | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [policy, setPolicy] = useState<AutonomyThreshold | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<TabId>("gate");
  const [actor, setActor] = useState("");
  const [working, setWorking] = useState(false);
  const [deciding, setDeciding] = useState<string | null>(null);
  const [walk, setWalk] = useState<{ ordinal: number; total: number } | null>(null);

  useEffect(() => {
    api.batches()
      .then((r) => {
        setBatches(r.batches);
        setSelected((current) => current ?? r.batches[0]?.batch_id ?? null);
      })
      .catch(() => setBatches([]));
    api.autonomyThreshold().then(setPolicy).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (batchId) setSelected(batchId);
  }, [batchId]);

  const load = useCallback((id: string) => {
    setLoading(true);
    Promise.all([
      api.batchReport(id),
      api.suggestions({ submissionId: id })
        .catch(() => ({ suggestions: [] as Suggestion[] })),
    ])
      .then(([found, queue]) => {
        setReport(found);
        setSuggestions(queue.suggestions);
      })
      .catch((e) => toast.error("Could not read the batch", String(e)))
      .finally(() => setLoading(false));
  }, [toast]);

  useEffect(() => {
    if (selected) load(selected);
  }, [selected, load]);

  /* Walk the batch, one product at a time.
   *
   * The report is recomputed on every read, so this changes no figure a plain
   * reload would not have produced. What it adds is the sequence: the gate
   * deciding one product at a time is the only place in this product where the
   * catalog is seen being read rather than having been read.
   */
  const walkBatch = useCallback(() => {
    if (!selected || working) return;
    setWorking(true);
    setWalk(null);
    streamBatchAssess(selected, (event) => {
      if (event.kind === "product") {
        setWalk({ ordinal: event.ordinal, total: event.total });
      }
    }, { paceMs: 160 })
      .then(() => load(selected))
      .catch((e) => toast.error("The pass failed", String(e)))
      .finally(() => { setWorking(false); setWalk(null); });
  }, [selected, working, load, toast]);

  const propose = useCallback(() => {
    if (!selected || !actor.trim()) return;
    setWorking(true);
    api.batchFix(selected, { actor: actor.trim() })
      .then((result) => {
        const { filled, queued, requested } = result.counts;
        toast.notify(
          `${filled} recorded, ${queued} for you to decide, ${requested} back `
          + "to the supplier",
          result.note);
        load(selected);
        if (queued > 0) setTab("decisions");
      })
      .catch((e) => toast.error("Could not propose values", String(e)))
      .finally(() => setWorking(false));
  }, [selected, actor, toast, load]);

  const decide = useCallback(
    (id: string, decision: "APPROVE" | "REJECT" | "RECTIFY",
     value?: unknown, comment?: string) => {
      if (!actor.trim()) return;
      setDeciding(id);
      api.decideSuggestion(id, { actor: actor.trim(), decision, value, comment })
        .then((result) => {
          toast.notify(DECIDED_LABEL[decision], result.note);
          if (selected) load(selected);
        })
        .catch((e) => toast.error("Could not record the decision", String(e)))
        .finally(() => setDeciding(null));
    },
    [actor, selected, toast, load]);

  const current = useMemo(
    () => batches?.find((b) => b.batch_id === selected) ?? null,
    [batches, selected]);

  const pending = useMemo(
    () => suggestions.filter((s) => s.route === "HUMAN" && !s.decision),
    [suggestions]);
  const answered = useMemo(
    () => suggestions.filter((s) => s.decision), [suggestions]);
  const autonomous = useMemo(
    () => suggestions.filter((s) => s.route === "AUTONOMOUS").length,
    [suggestions]);

  const threshold = policy?.threshold ?? ASSUMED_THRESHOLD;
  const stopped = report?.products.filter((p) => !p.gate?.passed).length ?? 0;

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
          on the live feed in System Control, and the report appears here.
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
     * contents scroll. `Tabs fill` carries a floor, and the column below is a
     * scroller of last resort: on a short screen the whole section scrolls
     * instead of collapsing to nothing. */
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader
        section="intake"
        actions={
          <div className="flex items-center gap-2">
            {batches && batches.length > 1 && (
              <select
                aria-label="Which batch to report on"
                className={cn(
                  "rounded-md border border-subtle bg-raised px-2 py-1 text-sm",
                  "transition-colors duration-[var(--dur-fast)] ease-standard",
                  "hover:border-strong"
                )}
                value={selected ?? ""}
                onChange={(e) => {
                  setSelected(e.target.value);
                  onOpenBatch?.(e.target.value);
                }}
              >
                {batches.map((b) => (
                  <option key={b.batch_id} value={b.batch_id}>
                    {b.supplier} — {b.file?.filename ?? b.batch_id} ({b.entities.length})
                  </option>
                ))}
              </select>
            )}
            <Button
              onClick={walkBatch}
              loading={working && !!walk}
              disabled={working || !selected}
              icon={<IconSpark size={14} />}
            >
              {walk ? `${walk.ordinal}/${walk.total}` : "Walk the batch"}
            </Button>
          </div>
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
            <Headline
              report={report}
              current={current}
              stopped={stopped}
              autonomous={autonomous}
              awaiting={pending.length}
            />

            <Tabs fill value={tab} onValueChange={(v) => setTab(v as TabId)}>
              <TabList ariaLabel="The stages this batch moves through">
                <Tab value="gate" count={stopped || undefined}>
                  Compliance gate
                </Tab>
                <Tab value="onboarding" count={report.products.length - stopped}>
                  Onboarding
                </Tab>
                <Tab value="suggestions" count={suggestions.length || undefined}>
                  Suggestions
                </Tab>
                <Tab value="decisions" count={pending.length || undefined}>
                  Decisions
                </Tab>
              </TabList>

              <TabPanel value="gate" scroll>
                <GateTab report={report} />
              </TabPanel>

              <TabPanel value="onboarding" scroll>
                <OnboardingTab report={report} />
              </TabPanel>

              <TabPanel value="suggestions" scroll>
                <SuggestionsTab
                  report={report}
                  suggestions={suggestions}
                  threshold={threshold}
                  minSources={policy?.min_sources ?? 2}
                  actor={actor}
                  setActor={setActor}
                  busy={working}
                  onApply={propose}
                />
              </TabPanel>

              <TabPanel value="decisions" scroll>
                <DecisionsTab
                  suggestions={pending}
                  decided={answered}
                  threshold={threshold}
                  actor={actor}
                  setActor={setActor}
                  busy={deciding}
                  onDecide={decide}
                />
              </TabPanel>
            </Tabs>
          </>
        ) : null}
      </div>
    </div>
  );
}

/** End a sentence that is about to have another one written after it.
 *
 *  The server's caveats are written to stand alone and do not carry a full
 *  stop. Appending to one produced "...rather than a cleaner one That includes
 *  the compliance gate", which reads as a rendering fault rather than as two
 *  sentences. */
function stop(sentence: string): string {
  const text = sentence.trim();
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

/* --- the four numbers ----------------------------------------------------- */

/** What somebody came for, in the order the product moves.
 *
 * "Stopped at the gate" is first because it means something categorically
 * different from the other three: those products are not behind, they are not
 * coming.
 */
function Headline({ report, current, stopped, autonomous, awaiting }: {
  report: BatchReport;
  current: BatchRow | null;
  stopped: number;
  autonomous: number;
  awaiting: number;
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
          label="Stopped at the gate"
          value={stopped}
          tone={stopped ? "bad" : undefined}
          sub="a regulation or a policy refused them"
        />
        <Kpi
          label="Went through clean"
          value={t.cleared}
          tone="good"
          sub={report.checks_complete
            ? "no findings against any check"
            : "no findings against the checks that ran"}
        />
        <Kpi
          label="Recorded autonomously"
          value={autonomous}
          sub="cleared the threshold with corroboration"
        />
        <Kpi
          label="Awaiting your decision"
          value={awaiting}
          tone={awaiting ? "bad" : undefined}
          sub="proposals a person has to answer"
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
          {stop(report.caveat ?? NARROW_NOTE)} That includes the compliance
          gate: the checks that read <Code>REG-*</Code> and <Code>POL-*</Code>
          need a model, so a product shown as cleared here cleared the
          deterministic half of it.
        </p>
      )}
    </Panel>
  );
}
