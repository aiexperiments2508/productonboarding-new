import { useEffect, useMemo, useState } from "react";
import { api, fmt } from "../api";
import type {
  Action, AttributeDef, AuditEntry, CatalogState, ChangeSummaryLine, Citation,
  PendingApproval, ProvenanceKind, RunSnapshot, SetAttributeAction, SourceRef,
  WithholdChannelAction,
} from "../api";
import { ArtNoDecision } from "../art/illustrations";
import { PageHeader } from "../app/shell/PageHeader";
import {
  IconAlert, IconCheck, IconChevronRight, IconClose, IconRefresh,
} from "../icons";
import {
  Badge, Button, Code, Divider, EmptyState, Field, Panel, Section, Select,
  Skeleton, Table, Td, Th, Tooltip, cn, useToast,
} from "../ui";
import {
  ChannelChip, CitationCard, ImpactedOutputs, KpiStrip, ProvBadge,
  RegulatedTag, SafetyFlag, Severity, SourceCite, ValueDiff, Violations,
  describeAction,
} from "./common";
import type { ChannelState, NameLookup } from "./common";
import { GraphView } from "./GraphView";
import { PlanDiffPanel, RevisionBadge } from "./PlanDiffPanel";
import { Reservations } from "./Reservations";
import { RunHistory } from "./RunHistory";

/* Review and audit.
 *
 * A reviewer arrives here with one question: may this correction go back out to
 * the channels. Answering it needs four things on the same screen, and this
 * view is arranged around them.
 *
 *   1. Per corrected field: the source document it came from, the value it
 *      replaces, the value it sets, and every asset and channel still carrying
 *      the old one. That chain is the brief's requirement and it is a table
 *      rather than four paragraphs, because a chain is a row.
 *   2. What publishes and what is held, per channel, each with its reason. A
 *      channel that cannot publish is shown with what bound it, never dropped.
 *   3. Whether approval is optional. It usually is not: a safety attribute or a
 *      regulated product makes review mandatory, and that is stated in words
 *      rather than implied by a differently-coloured button.
 *   4. Who decided, what they said, and an append-only record afterwards.
 *
 * The graph is genuinely suspended while this view is open - the run is parked
 * at an interrupt() with its state checkpointed, not held in a browser
 * variable. Closing the tab, or restarting the process, does not lose it.
 *
 * This is also the primary proof surface. LangGraph Studio shows the same run
 * more richly, but the demo must not depend on an external service, so
 * everything a judge needs to see is here.
 */

/* --- the reviewer's diff row ---------------------------------------------- */

/** One corrected field, end to end. Assembled from `Recommendation.changes`,
 *  which the graph builds deterministically - the UI never parses prose to
 *  find out what a correction says. */
interface ChangeRow {
  ref: string;
  entity_id: string;
  attribute_path: string;
  old_value?: unknown;
  new_value?: unknown;
  unit?: string | null;
  source?: SourceRef | null;
  confidence?: number | null;
  impacted_assets: string[];
  impacted_channels: string[];
  safety: boolean;
  /** From `AttributeDef.ordered`: an ingredient declaration is ordered by law,
   *  so a reorder is a change and has to draw as one. */
  ordered: boolean;
}

/** What happens to one channel if this is approved, and why. */
interface ChannelRow {
  id: string;
  state: ChannelState;
  why: string;
  fields: number;
}

/** Worst-first, so the reason a reviewer is being asked to look leads. */
const STATE_RANK: Record<ChannelState, number> = {
  ready: 0, rejected: 1, blocked: 2, withheld: 3,
};

const isSetAttribute = (a: Action): a is SetAttributeAction =>
  a.kind === "SET_ATTRIBUTE";
const isWithhold = (a: Action): a is WithholdChannelAction =>
  a.kind === "WITHHOLD_CHANNEL";

/* --- the view ------------------------------------------------------------- */

export function Approvals({
  run, onDecided, onReplan, replanning, catalog, onOpenCitation,
  pending = [], onOpenThread, onRefreshPending,
}: {
  run: RunSnapshot | null;
  onDecided: (snapshot: RunSnapshot) => void;
  onReplan: (reason: string) => void;
  replanning: boolean;
  /** The catalog, where the shell already holds it. Fetched here when it does
   *  not: every row names a variant, an attribute or a channel, and a page of
   *  bare identifiers is not reviewable. */
  catalog?: CatalogState | null;
  onOpenCitation?: (citation: Citation) => void;
  /** Everything suspended at the gate, from the server. The same array the rail
   *  badge counts - this screen exists to action it, so it has to be able to
   *  see all of it and not only what this browser raised. */
  pending?: PendingApproval[];
  /** Adopt a case from the queue: load its checkpoint and make it the run this
   *  screen is deciding. */
  onOpenThread?: (snapshot: RunSnapshot) => void;
  onRefreshPending?: () => void;
}) {
  const toast = useToast();
  const [comment, setComment] = useState("");
  const [actor, setActor] = useState("reviewer");
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [audit, setAudit] = useState<AuditEntry[] | null>(null);
  const [fetched, setFetched] = useState<CatalogState | null>(null);

  useEffect(() => {
    api.audit(60)
      .then((r) => setAudit(r.entries))
      .catch(() => setAudit([]));
  }, [run?.status]);

  useEffect(() => {
    if (catalog) return;
    let live = true;
    api.network()
      .then((c) => { if (live) setFetched(c); })
      .catch(() => undefined);   // names fall back to ids; nothing else breaks
    return () => { live = false; };
  }, [catalog]);

  const cat = catalog ?? fetched;

  const names = useMemo(() => {
    const m = new Map<string, string>();
    for (const n of cat?.nodes ?? []) m.set(n.id, n.name);
    for (const p of cat?.products ?? []) m.set(p.id, p.name);
    for (const v of cat?.variants ?? []) m.set(v.id, v.name);
    for (const c of cat?.channels ?? []) m.set(c.id, c.name);
    for (const a of cat?.attributes ?? []) m.set(a.path, a.label);
    return m;
  }, [cat]);
  const name = useMemo<NameLookup>(() => (key) => names.get(key), [names]);

  const attrs = useMemo(
    () => new Map<string, AttributeDef>(
      (cat?.attributes ?? []).map((a) => [a.path, a] as const)
    ),
    [cat]
  );

  /** Products the law binds, and the variants underneath them. Approval on one
   *  of these is mandatory whatever else the change looks like. */
  const regulated = useMemo(() => {
    const s = new Set<string>();
    for (const p of cat?.products ?? []) if (p.regulated) s.add(p.id);
    for (const v of cat?.variants ?? []) if (s.has(v.product_id)) s.add(v.id);
    return s;
  }, [cat]);

  const rec = run?.values.recommendation;
  const ranked = run?.values.ranked ?? [];
  const selectedId = scenarioId ?? rec?.scenario_id;
  const chosen = ranked.find((r) => r.scenario_id === selectedId);
  /** The reading that changes nothing, where the graph generated one. It is
   *  what every figure is measured against. */
  const compare = ranked.find((r) => r.delta.actions.length === 0)?.kpis;
  const diff = run?.values.plan_diff;
  const revision = run?.values.revision;

  const kpis = chosen?.kpis ?? rec?.kpis;
  const violations = chosen?.violations ?? rec?.violations ?? [];
  const feasible = chosen?.feasible ?? rec?.feasible ?? true;
  const actions = chosen?.delta.actions ?? rec?.delta.actions ?? [];
  const onRecommended = selectedId === rec?.scenario_id;

  /* The recommendation's own diff, keyed for lookup. It is authoritative for
   * the recommended reading; where a reviewer switches to another option, it
   * still supplies the lineage, because what a field feeds does not depend on
   * which reading proposes to change it. */
  const recLines = useMemo(
    () => new Map<string, ChangeSummaryLine>(
      (rec?.changes ?? []).map(
        (c) => [`${c.entity_id}:${c.attribute_path}`, c] as const
      )
    ),
    [rec]
  );

  const rows = useMemo<ChangeRow[]>(() => {
    const fromLine = (c: ChangeSummaryLine): ChangeRow => ({
      ref: `${c.entity_id}:${c.attribute_path}`,
      entity_id: c.entity_id,
      attribute_path: c.attribute_path,
      old_value: c.old_value,
      new_value: c.new_value,
      unit: c.unit ?? attrs.get(c.attribute_path)?.unit ?? null,
      source: c.source ?? null,
      confidence: c.confidence ?? null,
      impacted_assets: c.impacted_assets ?? [],
      impacted_channels: c.impacted_channels ?? [],
      safety: c.safety || (attrs.get(c.attribute_path)?.safety_class ?? false),
      ordered: attrs.get(c.attribute_path)?.ordered ?? true,
    });

    if (onRecommended) return (rec?.changes ?? []).map(fromLine);

    // A reviewer looking at a different option gets the same four columns,
    // built from that option's own value changes.
    return (chosen?.delta.actions ?? [])
      .filter(isSetAttribute)
      .map((a) => {
        const ref = `${a.entity_id}:${a.attribute_path}`;
        const line = recLines.get(ref);
        const def = attrs.get(a.attribute_path);
        return {
          ref,
          entity_id: a.entity_id,
          attribute_path: a.attribute_path,
          old_value: a.old_value,
          new_value: a.new_value,
          unit: a.unit ?? def?.unit ?? line?.unit ?? null,
          source: a.source ?? line?.source ?? null,
          confidence: a.confidence ?? line?.confidence ?? null,
          impacted_assets: line?.impacted_assets ?? [],
          impacted_channels: line?.impacted_channels ?? [],
          safety: def?.safety_class ?? line?.safety ?? false,
          ordered: def?.ordered ?? true,
        };
      });
  }, [onRecommended, rec, chosen, recLines, attrs]);

  /* Per-channel readiness. Every channel a corrected field feeds is ready
   * unless something says otherwise: a hard rule that fails blocks it, and a
   * deliberate hold outranks both. The count of blocked channels comes from the
   * validator's KPI - this table is the itemisation of that figure, never a
   * second opinion about it. */
  const channelRows = useMemo<ChannelRow[]>(() => {
    const fields = new Map<string, number>();
    for (const r of rows) {
      for (const id of r.impacted_channels) {
        fields.set(id, (fields.get(id) ?? 0) + 1);
      }
    }

    const state = new Map<string, { state: ChannelState; why: string }>();
    const put = (id: string, next: ChannelState, why: string) => {
      const prev = state.get(id);
      if (!prev || STATE_RANK[next] > STATE_RANK[prev.state]) {
        state.set(id, { state: next, why });
      }
    };

    for (const [id, n] of fields) {
      put(id, "ready",
        `${n} corrected ${n === 1 ? "field" : "fields"} republish here.`);
    }
    for (const v of violations) {
      if (!v.channel_id) continue;
      if (v.severity === "HARD") {
        put(v.channel_id, "blocked",
          v.detail || `${v.constraint.replace(/_/g, " ")} fails here.`);
      } else if (!state.has(v.channel_id)) {
        put(v.channel_id, "ready",
          v.detail || `${v.constraint.replace(/_/g, " ")} — advisory only.`);
      }
    }
    for (const a of actions) {
      if (isWithhold(a)) {
        put(a.channel_id, "withheld",
          a.reason || "Held back until a reviewer approves the correction.");
      } else if (a.kind === "SET_FACET" && !state.has(a.channel_id)) {
        put(a.channel_id, "ready", describeAction(a, name));
      }
    }

    return [...state.entries()]
      .map(([id, s]) => ({ id, ...s, fields: fields.get(id) ?? 0 }))
      .sort((a, b) =>
        STATE_RANK[b.state] - STATE_RANK[a.state] || a.id.localeCompare(b.id));
  }, [rows, violations, actions, name]);

  /** Why approval is mandatory, in the words that make it mandatory. Both
   *  conditions are read off flags the API already set - the UI is naming them,
   *  not deciding them. */
  const mandatoryBecause = useMemo(() => {
    const why: string[] = [];
    if (rows.some((r) => r.safety)) {
      why.push(
        "A safety-class value moved — an allergen declaration, or a value the "
        + "safety gate does not trust at the confidence it was read."
      );
    }
    const bound = [...new Set(rows.map((r) => r.entity_id))]
      .filter((id) => regulated.has(id));
    if (bound.length > 0) {
      why.push(
        `Regulated product: ${bound
          .map((id) => `${names.get(id) ?? id} (${id})`)
          .join(", ")}. Its declarations are legally binding.`
      );
    }
    return why;
  }, [rows, regulated, names]);

  async function decide(decision: "APPROVE" | "REJECT") {
    if (!run) return;
    setBusy(true);
    try {
      const next = await api.decide(run.thread_id, {
        decision, actor, comment, scenario_id: selectedId,
      });
      onDecided(next);
      setComment("");
      toast.push({
        tone: decision === "APPROVE" ? "ok" : "warn",
        title:
          decision === "APPROVE"
            ? "Approved — the correction republishes"
            : "Rejected — nothing republished",
        detail: next.values.commit_result?.error ?? undefined,
      });
    } catch (e) {
      toast.error("Decision could not be recorded", String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        section="approvals"
        actions={
          <>
            <RevisionBadge revision={revision} />
            {run && (
              <Tooltip content={
                "Re-read this correction against everything that has arrived "
                + "since the recommendation was written. Same incident, next "
                + "revision — the previous readings are carried forward and "
                + "validated again rather than thrown away."
              }>
                <span>
                  <Button
                    onClick={() => onReplan("a reviewer asked for a revision")}
                    loading={replanning}
                    icon={<IconRefresh size={14} />}
                  >
                    Re-plan on new evidence
                  </Button>
                </span>
              </Tooltip>
            )}
          </>
        }
      />

      {/* The diff is cleared when a revision starts and refilled by `rank`, so
          the test is for the superseded reading rather than for the object -
          an empty diff is still an object, and still truthy. */}
      {diff?.previous && (
        <div className="mb-3">
          <PlanDiffPanel diff={diff} narrative={rec?.change} />
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(360px,1fr)]">
        <div className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
          {/* The queue first, because on this screen the first question is
              which decision, and only then what it says. It is drawn whenever
              anything is waiting - including when the case on screen is the
              only one, so a reviewer can always see whether it is. */}
          {pending.length > 0 && onOpenThread && (
            <PendingQueue
              queue={pending}
              openThreadId={run?.thread_id ?? null}
              onOpen={onOpenThread}
              onRefresh={onRefreshPending}
              name={name}
            />
          )}

          {run?.awaiting_approval && rec ? (
            <Panel
              title="Decision required"
              tone={rec.requires_review ? "danger" : "warn"}
              subtitle={rec.scenario_id}
            >
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="warn" dot>graph suspended at approval</Badge>
                  <ProvBadge provenance={rec.provenance} />
                  <Tooltip content="How sure the recommender is of this reading of the correction. It is not the confidence of any individual value — those sit on the rows below.">
                    <span className="text-sm text-faint">
                      confidence {(rec.confidence * 100).toFixed(0)}%
                    </span>
                  </Tooltip>
                  <SafetyFlag count={kpis?.safety_flags} />
                </div>

                {rec.requires_review && (
                  <MandatoryReview reasons={mandatoryBecause} />
                )}

                <div>
                  <strong className="text-md">{rec.scenario_name}</strong>
                  <p className="mt-1 text-base leading-relaxed">
                    {rec.narrative}
                  </p>
                </div>

                {kpis && <KpiStrip kpis={kpis} compare={compare} />}

                <Divider />

                {/* --- the chain the brief asks for --------------------- */}
                <Section
                  label={`Changes to publish (${rows.length})`}
                  actions={
                    !onRecommended && (
                      <span className="text-xs text-faint">
                        showing the option you selected, not the recommendation
                      </span>
                    )
                  }
                >
                  {rows.length === 0 ? (
                    <p className="text-sm leading-relaxed text-muted">
                      This option moves no stored value.
                      {actions.length > 0
                        ? " It only changes what publishes and what is held."
                        : " Nothing would be republished."}
                    </p>
                  ) : (
                    <div style={{ ["--table-min-w" as string]: "880px" }}>
                      <Table scroll>
                        <thead>
                          <tr>
                            <Th>Source document</Th>
                            <Th>Field</Th>
                            <Th>Old value → new value</Th>
                            <Th>Impacted outputs</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((r) => (
                            <ChangeRowCells
                              key={r.ref}
                              row={r}
                              name={name}
                              regulated={regulated.has(r.entity_id)}
                            />
                          ))}
                        </tbody>
                      </Table>
                    </div>
                  )}
                </Section>

                <Divider />

                {/* --- per-channel readiness ---------------------------- */}
                <Section
                  label="Channel readiness"
                  actions={
                    kpis && (
                      <span className="font-mono text-xs text-faint tabular-nums">
                        {fmt.count(kpis.channels_blocked)} blocked ·{" "}
                        {kpis.listings_ready_pct.toFixed(1)}% of listings ready
                      </span>
                    )
                  }
                >
                  {channelRows.length === 0 ? (
                    <p className="text-sm leading-relaxed text-muted">
                      No channel is touched by this option. Nothing republishes
                      and nothing is held.
                    </p>
                  ) : (
                    <>
                      <div className="flex flex-col gap-1.5">
                        {channelRows.map((c) => (
                          <ChannelReadiness
                            key={c.id}
                            row={c}
                            name={names.get(c.id)}
                          />
                        ))}
                      </div>
                      <p className="text-xs leading-relaxed text-faint">
                        Channels not listed carry none of the corrected fields
                        and are left exactly as they are.
                      </p>
                    </>
                  )}
                </Section>

                {rec.trade_offs.length > 0 && (
                  <>
                    <Divider />
                    <Section label="Trade-offs">
                      <Table>
                        <thead>
                          <tr>
                            <Th>Dimension</Th>
                            <Th>Gain</Th>
                            <Th>Cost</Th>
                          </tr>
                        </thead>
                        <tbody>
                          {rec.trade_offs.map((t, i) => (
                            <tr key={i} className="border-b border-subtle">
                              <Td className="text-sm">{t.dimension}</Td>
                              {/* Not coloured. The columns are headed Gain and
                                  Cost, so a green column and a red one restate
                                  the header on every row - and a table painted
                                  end to end in the two status hues is the
                                  loudest thing on a panel whose actual
                                  warnings need to out-shout it. */}
                              <Td className="text-sm">{t.gain}</Td>
                              <Td className="text-sm">{t.cost}</Td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </Section>
                  </>
                )}

                {rec.assumptions.length > 0 && (
                  <>
                    <Divider />
                    <Section label="Assumptions">
                      <ul className="flex list-disc flex-col gap-1 pl-4 text-sm text-muted">
                        {rec.assumptions.map((a, i) => <li key={i}>{a}</li>)}
                      </ul>
                      <p className="text-sm text-faint">
                        Each of these would change the answer if it turned out
                        to be wrong.
                      </p>
                    </Section>
                  </>
                )}

                {rec.rejected_alternatives.length > 0 && (
                  <>
                    <Divider />
                    <Section label="Why not the other readings">
                      <div className="flex flex-col gap-1.5">
                        {rec.rejected_alternatives.map((r, i) => (
                          <div key={i} className="text-sm">
                            <Code>
                              {ranked.find((s) => s.scenario_id === r.scenario_id)?.name
                                ?? r.scenario_id}
                            </Code>
                            <span className="text-muted"> — {r.why}</span>
                          </div>
                        ))}
                      </div>
                    </Section>
                  </>
                )}

                <Divider />
                <Section label="What gets written if you approve">
                  {actions.length === 0 ? (
                    <p className="text-sm leading-relaxed text-muted">
                      Nothing. Approving accepts the catalog as it stands — a
                      decision, and recorded as one.
                    </p>
                  ) : (
                    <div className="flex flex-col gap-1">
                      {actions.map((a, i) => (
                        <div
                          key={a.id ?? i}
                          className={cn(
                            "flex items-start gap-2 rounded-sm border",
                            isWithhold(a)
                              ? "border-warn-border bg-warn-soft text-warn-text"
                              : "border-ok-border bg-ok-soft text-ok-text",
                            "px-2 py-1 text-sm"
                          )}
                        >
                          <span className="font-mono font-bold">
                            {isWithhold(a) ? "!" : "+"}
                          </span>
                          <span className="min-w-0 flex-1">
                            {describeAction(a, name)}
                          </span>
                          {a.source && <SourceCite source={a.source} />}
                        </div>
                      ))}
                    </div>
                  )}
                </Section>

                {!feasible && (
                  <>
                    <Divider />
                    <div className="flex items-start gap-2 rounded-sm border border-danger-border bg-danger-soft p-2.5 text-sm text-danger-text">
                      <IconAlert size={15} className="mt-0.5 shrink-0" />
                      <span>
                        This option still breaks a hard channel rule. Approving
                        it publishes what it can and leaves the rest blocked.
                      </span>
                    </div>
                    <Violations violations={violations} />
                  </>
                )}

                <Divider />
                <div className="flex flex-col gap-2.5">
                  <Field label="Reading" width={72}>
                    <Select
                      ariaLabel="Reading to publish"
                      value={selectedId}
                      onValueChange={setScenarioId}
                      className="w-full"
                      options={ranked.map((r) => ({
                        value: r.scenario_id,
                        label:
                          r.name +
                          (r.scenario_id === rec.scenario_id
                            ? "  (recommended)" : ""),
                        hint: `${r.kpis.listings_ready_pct.toFixed(1)}% ready · `
                              + `${r.kpis.channels_blocked} blocked`,
                      }))}
                    />
                  </Field>
                  <Field label="Reviewer" width={72}>
                    <input
                      type="text"
                      value={actor}
                      onChange={(e) => setActor(e.target.value)}
                      className={cn(
                        "h-[var(--control-h-sm)] w-full rounded-sm border",
                        "border-strong bg-raised px-2.5 text-base",
                        "transition-colors focus:border-focus"
                      )}
                    />
                  </Field>
                  <textarea
                    rows={2}
                    placeholder="Comment (recorded in the audit trail)"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    className={cn(
                      "w-full resize-y rounded-sm border border-strong bg-raised",
                      "px-2.5 py-1.5 text-base transition-colors focus:border-focus"
                    )}
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      tone="primary"
                      size="md"
                      loading={busy}
                      icon={<IconCheck size={15} />}
                      onClick={() => decide("APPROVE")}
                    >
                      Approve and republish
                    </Button>
                    <Button
                      tone="danger"
                      size="md"
                      disabled={busy}
                      icon={<IconClose size={15} />}
                      onClick={() => decide("REJECT")}
                    >
                      Reject
                    </Button>
                  </div>
                  <p className="text-xs leading-relaxed text-faint">
                    {rec.requires_review
                      ? "This correction cannot publish without a decision "
                        + "recorded here, and the decision is recorded against "
                        + "the name above."
                      : "This correction touches no safety value and no "
                        + "regulated product, so review is not mandatory — but "
                        + "the run stays suspended here until you decide."}
                  </p>
                </div>
              </div>
            </Panel>
          ) : run?.values.approval ? (
            <Panel
              title="Decision recorded"
              tone={run.values.approval.decision === "APPROVE" ? undefined : "danger"}
            >
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge
                    tone={run.values.approval.decision === "APPROVE" ? "ok" : "danger"}
                  >
                    {run.values.approval.decision === "APPROVE"
                      ? "approved" : run.values.approval.decision.toLowerCase()}
                  </Badge>
                  <ProvBadge provenance={{ kind: "DECIDED" }} showConfidence={false} />
                  <span className="text-sm text-faint">
                    by {run.values.approval.actor} at{" "}
                    {fmt.stamp(run.values.approval.decided_at)}
                  </span>
                </div>
                {run.values.approval.comment && (
                  <blockquote className="border-l-2 border-accent-border pl-2.5 text-sm italic text-muted">
                    {run.values.approval.comment}
                  </blockquote>
                )}
                {run.values.commit_result && (
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    {run.values.commit_result.committed ? (
                      <>
                        <Badge tone="ok" dot>published</Badge>
                        <span className="text-muted">
                          {(run.values.commit_result.actions ?? []).length}{" "}
                          change(s) written to the catalog
                        </span>
                      </>
                    ) : (
                      <>
                        <Badge tone="danger">
                          {run.values.commit_result.error ?? "not published"}
                        </Badge>
                        <span className="text-muted">
                          {run.values.commit_result.detail}
                        </span>
                      </>
                    )}
                  </div>
                )}
                {run.values.commit_result?.committed && (
                  <RollbackControl
                    incidentId={run.values.incident_id}
                    scenarioId={run.values.recommendation?.scenario_id}
                    onDone={onReplan}
                  />
                )}
              </div>
            </Panel>
          ) : pending.length > 0 ? (
            /* The queue is not empty, so this screen must not say it is. What
               is missing is a selection, not work. */
            <Panel>
              <EmptyState
                art={<ArtNoDecision />}
                title={
                  pending.length === 1
                    ? "One correction is waiting on a decision"
                    : `${pending.length} corrections are waiting on a decision`
                }
              >
                None of them is open on this screen yet. Choose one from the
                queue above to see the fields it corrects, what would republish
                and what would be held, and to approve or reject it.
              </EmptyState>
            </Panel>
          ) : (
            <Panel>
              <EmptyState
                art={<ArtNoDecision />}
                title="Nothing awaiting a decision"
              >
                Start a correction run from the Ingest Fabric — it stops here
                once it knows what the supplier document changes and what that
                would republish, with the graph genuinely suspended at the
                interrupt.
              </EmptyState>
            </Panel>
          )}

          {rec?.citations && rec.citations.length > 0 && (
            <Panel
              title="Evidence cited"
              subtitle={`${rec.citations.length} passages`}
            >
              <div className="flex flex-col gap-2">
                {rec.citations.slice(0, 6).map((c) => (
                  <CitationCard
                    key={c.chunk_id}
                    c={c}
                    onOpen={
                      onOpenCitation ? () => onOpenCitation(c) : undefined
                    }
                  />
                ))}
              </div>
            </Panel>
          )}
        </div>

        <div className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
          <GraphView run={run} />

          <Panel title="Run trace" flush>
            {(run?.values.trace ?? []).length === 0 ? (
              <EmptyState compact title="No trace yet">
                Each node the graph executes appends a step here.
              </EmptyState>
            ) : (
              <div className="sc-stagger max-h-[340px] overflow-y-auto">
                {(run?.values.trace ?? []).map((t, i) => (
                  <div
                    key={i}
                    style={{ ["--i" as string]: i }}
                    className="flex gap-2.5 border-b border-subtle px-3 py-2"
                  >
                    <span className="w-[100px] shrink-0 font-mono text-xs font-semibold text-accent-text">
                      {t.node}
                    </span>
                    <span className="min-w-0 flex-1 text-sm">{t.summary}</span>
                    {typeof t.elapsed_ms === "number" && (
                      <Tooltip content="Time since the previous step - the work between the two lines.">
                        <span className="shrink-0 font-mono text-2xs tabular-nums text-faint">
                          {Math.round(t.elapsed_ms)}ms
                        </span>
                      </Tooltip>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Reservations
            refreshKey={`${run?.status}-${run?.values.revision ?? 0}`}
          />

          <RunHistory threadId={run?.thread_id} status={run?.status} />

          <AuditLedger entries={audit} />
        </div>
      </div>
    </>
  );
}

/* --- the parts ------------------------------------------------------------ */

/* The shared work queue.
 *
 * An approval gate is a queue or it is nothing. The count has always been
 * server-backed - `/api/approvals/pending` reads the checkpoint behind every
 * suspended thread - but the only case this screen could ever show was the one
 * the current browser had started, held in a `thread_id` in local storage. So a
 * correction raised at the end of one shift was counted on the rail at the
 * start of the next and could not be opened by the person who came in to work
 * it, and a second reviewer could not see the first one's cases at all. The
 * decision existed, the route to take it existed, and no interface reached it.
 *
 * This is that list. Selecting a row loads that thread's checkpoint and makes
 * it the run the screen is deciding, which is the whole of the missing step:
 * everything below already works on whatever run it is handed.
 *
 * Rows carry the reason to pick one over another - severity, whether review is
 * mandatory, how many fields move - so a reviewer with two waiting decisions
 * chooses on the facts rather than by opening both.
 */
function PendingQueue({ queue, openThreadId, onOpen, onRefresh, name }: {
  queue: PendingApproval[];
  /** The case already on screen, marked rather than hidden - a queue that drops
   *  the row you are working reads as though it lost it. */
  openThreadId: string | null;
  onOpen: (snapshot: RunSnapshot) => void;
  onRefresh?: () => void;
  name: NameLookup;
}) {
  const toast = useToast();
  const [opening, setOpening] = useState<string | null>(null);

  async function open(row: PendingApproval) {
    if (row.thread_id === openThreadId || opening) return;
    setOpening(row.thread_id);
    try {
      // The checkpoint is the authority on what this decision says. Nothing is
      // reconstructed from the queue row, which carries only enough to choose.
      onOpen(await api.run(row.thread_id));
    } catch (e) {
      toast.error("That decision could not be opened", String(e));
    } finally {
      setOpening(null);
    }
  }

  return (
    <Panel
      tone="warn"
      title="Waiting on a decision"
      subtitle={
        queue.length === 1
          ? "1 correction, suspended at the approval gate"
          : `${queue.length} corrections, suspended at the approval gate`
      }
      actions={
        onRefresh && (
          <Tooltip content="Re-read the queue. Another reviewer may have taken one of these since the page loaded.">
            <span>
              <Button
                size="xs"
                tone="ghost"
                iconOnly
                aria-label="Re-read the approval queue"
                icon={<IconRefresh size={14} />}
                onClick={onRefresh}
              />
            </span>
          </Tooltip>
        )
      }
      flush
    >
      <ul className="flex flex-col">
        {queue.map((row) => {
          const isOpen = row.thread_id === openThreadId;
          const changes = row.interrupt?.changes ?? [];
          const mandatory = row.interrupt?.requires_review ?? false;
          const subject = changes[0]?.entity_id;
          return (
            <li key={row.thread_id} className="border-b border-subtle last:border-b-0">
              <button
                type="button"
                onClick={() => void open(row)}
                aria-current={isOpen ? "true" : undefined}
                /* aria-disabled rather than disabled: the row a reviewer is
                   working is the one they are most likely to tab back to, and
                   a disabled button leaves the tab order entirely. It is
                   inert either way - `open` returns early on it. */
                aria-disabled={isOpen || opening != null ? "true" : undefined}
                className={cn(
                  "flex w-full items-start gap-2.5 px-3 py-2.5 text-left",
                  "focus-visible:outline focus-visible:-outline-offset-2",
                  isOpen
                    ? "bg-accent-soft"
                    : "hover:bg-hover active:bg-active"
                )}
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Severity level={row.severity} />
                    {mandatory && (
                      <Badge tone="danger" dot>review mandatory</Badge>
                    )}
                    <span className="min-w-0 truncate text-sm font-medium">
                      {row.title}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 font-mono text-2xs text-faint">
                    <span>{row.id}</span>
                    {row.opened_at && <span>{fmt.stamp(row.opened_at)}</span>}
                    <span>
                      {changes.length === 1
                        ? "1 field"
                        : `${changes.length} fields`}
                    </span>
                    {subject && (
                      <span className="truncate">{name(subject) ?? subject}</span>
                    )}
                  </div>
                </div>
                {isOpen ? (
                  <Badge tone="accent" className="mt-0.5 shrink-0">open below</Badge>
                ) : (
                  <span className="mt-0.5 flex shrink-0 items-center gap-1 text-xs font-medium text-accent-text">
                    {opening === row.thread_id ? "opening…" : "Open"}
                    <IconChevronRight size={13} />
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}


/** Approval is not optional here, and the UI says so in words.
 *
 * `requires_review` is a decision the graph already made: a safety attribute
 * moved, or the product is regulated. Rendering that as a slightly different
 * button colour would leave the most consequential fact on the screen to be
 * inferred from styling, so it is a sentence instead, with the reason named.
 */
function MandatoryReview({ reasons }: { reasons: string[] }) {
  return (
    <div className="flex items-start gap-2 rounded-sm border border-danger-border bg-danger-soft p-2.5">
      <IconAlert size={16} className="mt-0.5 shrink-0 text-danger-text" />
      <div className="min-w-0 text-sm">
        <div className="font-semibold text-danger-text">
          Approval is mandatory. Nothing republishes until someone decides here.
        </div>
        {reasons.length > 0 ? (
          <ul className="mt-1 flex list-disc flex-col gap-0.5 pl-4 text-muted">
            {reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        ) : (
          <p className="mt-1 text-muted">
            The graph marked this correction for mandatory review.
          </p>
        )}
        <p className="mt-1 text-muted">
          There is no automatic path for this change. Rejecting leaves every
          channel exactly as it is.
        </p>
      </div>
    </div>
  );
}

/** One row of the reviewer's diff: source document → old value → new value →
 *  impacted outputs. Four cells, in that order, because the brief asks for the
 *  chain and a chain reads left to right. */
function ChangeRowCells({ row, name, regulated }: {
  row: ChangeRow;
  name: NameLookup;
  regulated: boolean;
}) {
  const label = name(row.attribute_path);
  const entity = name(row.entity_id);
  return (
    <tr className="border-b border-subtle last:border-b-0">
      <Td>
        <SourceCite source={row.source} />
        {typeof row.confidence === "number" && (
          <Tooltip content="How sure the model was of this value when it read it out of the document. A safety-class value read below the gate withholds the listing rather than publishing it.">
            <div className="mt-1 font-mono text-2xs text-faint">
              read at {(row.confidence * 100).toFixed(0)}%
            </div>
          </Tooltip>
        )}
      </Td>
      <Td>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-sm font-medium text-fg">
            {entity ?? row.entity_id}
          </span>
          {entity && entity !== row.entity_id && (
            <span className="font-mono text-2xs text-faint">{row.entity_id}</span>
          )}
          {regulated && <RegulatedTag />}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
          <span className="text-sm text-muted">{label ?? row.attribute_path}</span>
          {label && label !== row.attribute_path && (
            <Code>{row.attribute_path}</Code>
          )}
          {row.safety && <SafetyFlag count={1} />}
        </div>
      </Td>
      <Td>
        <ValueDiff
          oldValue={row.old_value}
          newValue={row.new_value}
          unit={row.unit}
          ordered={row.ordered}
        />
      </Td>
      <Td>
        <ImpactedOutputs
          assets={row.impacted_assets}
          channels={row.impacted_channels}
        />
      </Td>
    </tr>
  );
}

/** What happens to one channel, and why. A blocked channel is never dropped
 *  from the list - the reason it cannot publish is the thing the reviewer came
 *  here to read. */
function ChannelReadiness({ row, name }: { row: ChannelRow; name?: string }) {
  const verb =
    row.state === "withheld" ? "held back"
    : row.state === "blocked" ? "cannot publish"
    : row.state === "rejected" ? "rejected by the channel"
    : "republishes";
  return (
    <div
      className={cn(
        "flex flex-wrap items-start gap-x-2.5 gap-y-1 rounded-sm border",
        "px-2.5 py-1.5",
        row.state === "ready"
          ? "border-subtle bg-sunken"
          : row.state === "withheld"
          ? "border-warn-border bg-warn-soft"
          : "border-danger-border bg-danger-soft"
      )}
    >
      <ChannelChip channelId={row.id} state={row.state} name={name} />
      <span className="text-sm font-medium text-fg">{verb}</span>
      <span className="min-w-0 flex-1 text-sm text-muted">{row.why}</span>
    </div>
  );
}

/** The append-only record, with the provenance mix on top.
 *
 * The mix is the proof, not decoration: "we keep what was observed separate
 * from what was inferred and from what a person chose" is a claim, and a ledger
 * whose classes are countable at a glance is the evidence for it.
 */
function AuditLedger({ entries }: { entries: AuditEntry[] | null }) {
  const mix = useMemo(() => {
    const m = new Map<ProvenanceKind, number>();
    for (const e of entries ?? []) {
      const kind = e.provenance?.kind;
      if (kind) m.set(kind, (m.get(kind) ?? 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [entries]);

  return (
    <Panel
      title="Audit ledger"
      flush
      subtitle={entries ? `${entries.length} entries` : undefined}
      actions={<span className="text-sm text-faint">append only</span>}
    >
      {entries === null ? (
        <div className="flex flex-col gap-2 p-3">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      ) : entries.length === 0 ? (
        <EmptyState compact title="Nothing recorded yet">
          Every decision, publication and rollback lands here with the class of
          evidence behind it.
        </EmptyState>
      ) : (
        <>
          {mix.length > 0 && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-subtle px-3 py-2">
              {mix.map(([kind, n]) => (
                <span key={kind} className="inline-flex items-center gap-1.5">
                  <ProvBadge provenance={{ kind }} showConfidence={false} />
                  <span className="font-mono text-xs text-faint tabular-nums">
                    {n}
                  </span>
                </span>
              ))}
            </div>
          )}
          <div className="max-h-[420px] overflow-y-auto">
            {entries.map((e) => (
              <div
                key={e.id}
                className="flex items-start gap-2 border-b border-subtle px-3 py-2 hover:bg-hover"
              >
                <span className="shrink-0 font-mono text-xs text-faint tabular-nums">
                  {fmt.stamp(e.ts)}
                </span>
                <ProvBadge provenance={e.provenance} showConfidence={false} />
                <div className="min-w-0 flex-1 text-sm">
                  <span className="font-mono">{e.action}</span>{" "}
                  <span className="text-muted">{e.entity_type}</span>{" "}
                  <Code>{e.entity_id}</Code>
                  <div className="truncate text-xs text-faint">
                    by {e.actor}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </Panel>
  );
}

/** Undo a published correction.
 *
 * Sits with the recorded decision rather than anywhere near the approve button,
 * because it answers a different question: not "should we do this" but "that
 * was wrong, take it back". Releasing the publish locks is the part that
 * matters - a published batch holds its channels exclusively, and without a
 * release the only way to free them is a database edit.
 *
 * It asks first. A rollback is cheap to perform and expensive to have performed
 * by accident.
 */
function RollbackControl({ incidentId, scenarioId, onDone }: {
  incidentId?: string;
  scenarioId?: string;
  onDone: (reason: string) => void;
}) {
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  if (!incidentId || !scenarioId) return null;

  async function doRollback() {
    setBusy(true);
    try {
      const r = await api.rollback(
        incidentId!, scenarioId!, "rolled back by the reviewer");
      if (r.rolled_back) {
        toast.push({
          tone: "warn",
          title: "Publication rolled back",
          detail: `${r.actions_reversed ?? 0} change(s) reversed, `
                  + "publish locks released",
        });
        onDone("the published correction was rolled back");
      } else {
        toast.error("Rollback refused", r.error ?? r.detail);
      }
    } catch (e) {
      toast.error("Rollback failed", String(e));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  if (!confirming) {
    return (
      <div className="flex items-center gap-2">
        <Tooltip content="Reverse the committed changes and release the publish locks this batch holds">
          <span>
            <Button size="xs" tone="danger" onClick={() => setConfirming(true)}>
              Roll back this publication
            </Button>
          </span>
        </Tooltip>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-sm border border-danger-border bg-danger-soft px-2.5 py-2 text-sm">
      <IconAlert size={15} className="shrink-0 text-danger-text" />
      <span className="flex-1 text-danger-text">
        Reverse every change this publication wrote and release the channels it
        holds?
      </span>
      <Button size="xs" tone="danger" loading={busy} onClick={doRollback}>
        Roll back
      </Button>
      <Button size="xs" disabled={busy} onClick={() => setConfirming(false)}>
        Cancel
      </Button>
    </div>
  );
}

/** Provenance mix - the five classes, with what each one means.
 *
 * Shown because "we keep observations separate from inferences" is a claim, and
 * this is the key to the evidence for it. Imported by System Control as well as
 * used here, so the vocabulary is defined once.
 */
export function ProvenanceLegend() {
  const kinds = ["RECORDED", "INFERRED", "DECIDED", "SIMULATED", "COMMITTED"] as const;
  const meaning: Record<string, string> = {
    RECORDED: "read straight off a supplier feed or document",
    INFERRED: "a model read it out of prose, with a confidence",
    DECIDED: "chosen by a person",
    SIMULATED: "produced by the validator, never observed",
    COMMITTED: "published to the channels",
  };
  return (
    <div className="flex flex-col gap-2">
      {kinds.map((k) => (
        <div className="flex items-center gap-2" key={k}>
          <ProvBadge provenance={{ kind: k }} showConfidence={false} />
          <span className="text-sm text-muted">{meaning[k]}</span>
        </div>
      ))}
    </div>
  );
}
