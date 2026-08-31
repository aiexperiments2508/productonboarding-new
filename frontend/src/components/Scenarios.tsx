import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { api, fmt } from "../api";
import type {
  AttributeDef, CatalogState, ChangeScope, ChangeSummaryLine, RunSnapshot,
  ScopeLevel, SetAttributeAction, SimScenario, SourceRef, Violation,
} from "../api";
import { ArtNoOptions } from "../art/illustrations";
import { PageHeader } from "../app/shell/PageHeader";
import { IconAlert, IconRefresh, IconTrace } from "../icons";
import {
  Badge, Button, Code, Divider, EmptyState, Panel, ProgressBar, Section, Table,
  Td, Th, Tooltip, Tr, cn, useToast,
} from "../ui";
import {
  ActionList, ImpactedOutputs, KpiStrip, SafetyFlag, SourceCite, ValueDiff,
  Violations, describeAction,
} from "./common";
import type { NameLookup } from "./common";

/* Readings of the correction.
 *
 * A supplier correction says a number is wrong. It rarely says *whose* number:
 * the AeroPure document names the product and not the variant. So the question
 * this view answers is not "which resolution is cheapest" but "who does
 * this correction apply to" - and the candidates are competing readings of one
 * document, each validated deterministically against the same channel rules.
 *
 * Two or three readings of one sentence is not a frontier, so there is no
 * scatter plot here and no weight sliders: a ranked table with the deciding
 * evidence beside it is the honest form. Every figure comes from the
 * validator; the only ordering this file applies is the safety rule below.
 *
 * Safety is a pre-sort, not a column to trade off. A reading that moves an
 * allergen - or moves a machine-read value the safety gate does not trust -
 * cannot outrank one that does not, whatever it wins on elsewhere. That rule is
 * drawn as a line across the table rather than left implicit in the order.
 */

/* --- scope readings ------------------------------------------------------- */

const LEVEL_PHRASE: Record<ScopeLevel, (n: number) => string> = {
  BASE: () => "base product only",
  VARIANT: (n) => (n === 1 ? "one named variant" : `${n} named variants`),
  ALL: () => "every variant",
};

const LEVEL_MEANING: Record<ScopeLevel, string> = {
  BASE: "The correction is read as applying to the base product. Every other variant keeps the value it has.",
  VARIANT: "The correction is read as applying only to the variants the document names.",
  ALL: "The correction is read as applying to every variant of the product.",
};

/** A product or variant, named, with its id kept - reviewers search by
 *  VAR-01B, not by "the Max". Channels have their own chip in common.tsx. */
function EntityChip({ id, label }: { id: string; label?: string }) {
  const shown = label ?? id;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full",
        "border border-subtle bg-sunken py-px pl-2 pr-1.5 text-xs"
      )}
    >
      <span className="font-medium text-fg">{shown}</span>
      {shown !== id && (
        <span className="font-mono text-2xs text-faint">{id}</span>
      )}
    </span>
  );
}

/** Who the correction is read as applying to. The one thing that actually
 *  differs between candidates, so it leads every row. */
function ScopeReading({ scope, name, max = 3 }: {
  scope?: ChangeScope;
  name: NameLookup;
  max?: number;
}) {
  if (!scope) {
    return <span className="text-sm text-faint">no scope stated</span>;
  }
  const phrase = (LEVEL_PHRASE[scope.level] ?? (() => scope.level))(
    scope.entities.length
  );
  const shown = scope.entities.slice(0, max);
  const rest = scope.entities.length - shown.length;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Tooltip content={LEVEL_MEANING[scope.level] ?? scope.level}>
        <span>
          <Badge tone="info" dot>{phrase}</Badge>
        </span>
      </Tooltip>
      {shown.map((id) => (
        <EntityChip key={id} id={id} label={name(id)} />
      ))}
      {rest > 0 && (
        <Tooltip content={scope.entities.join("\n")} mono>
          <span className="text-xs text-faint">+{rest} more</span>
        </Tooltip>
      )}
    </div>
  );
}

/* --- lineage -------------------------------------------------------------- */

/** What a corrected field is still carrying downstream. Taken from the
 *  recommendation's own change diff where it has one, and from the catalog's
 *  derivation index otherwise - never inferred here. */
interface Impacted {
  assets: string[];
  channels: string[];
  unknown?: boolean;
}

/** One row of the reviewer's diff, assembled from a SET_ATTRIBUTE action and
 *  whatever the catalog knows about the attribute it names. */
interface ChangeRow {
  ref: string;
  entity_id: string;
  attribute_path: string;
  old_value?: unknown;
  new_value?: unknown;
  unit?: string | null;
  source?: SourceRef | null;
  confidence?: number | null;
  safety: boolean;
  ordered: boolean;
}

interface Recheck {
  scenario_id: string;
  hash: string;
  agrees: boolean;
  ms: number;
}

const flagsOn = (s: SimScenario) => Number(s.kpis?.safety_flags ?? 0);
const firstHard = (violations: Violation[]): Violation | undefined =>
  violations.find((v) => v.severity === "HARD") ?? violations[0];

/* --- the view ------------------------------------------------------------- */

export function Scenarios({ run, onRefresh, catalog }: {
  run: RunSnapshot | null;
  onRefresh: () => void;
  /** Passed by the shell where it already holds the catalog; fetched here when
   *  it does not. Used only to turn ids into names and to read an attribute's
   *  unit, order and safety class. */
  catalog?: CatalogState | null;
}) {
  const toast = useToast();
  const ranked = run?.values.ranked ?? [];
  const recommendation = run?.values.recommendation;
  const recommendedId = recommendation?.scenario_id;

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [fetched, setFetched] = useState<CatalogState | null>(null);
  const [lineage, setLineage] = useState<Record<string, Impacted>>({});
  const [recheck, setRecheck] = useState<Recheck | null>(null);
  const [busy, setBusy] = useState(false);
  const asked = useRef(new Set<string>());

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

  const attrs = useMemo(
    () => new Map<string, AttributeDef>(
      (cat?.attributes ?? []).map((a) => [a.path, a] as const)
    ),
    [cat]
  );

  const name = useMemo<NameLookup>(() => (key) => names.get(key), [names]);

  /* The safety pre-sort. Within each group the validator's own ranking is
   * preserved - this reorders, it does not re-score. */
  const ordered = useMemo(
    () =>
      ranked
        .map((r, i) => ({ r, i }))
        .sort((a, b) => (flagsOn(a.r) > 0 ? 1 : 0) - (flagsOn(b.r) > 0 ? 1 : 0)
                        || a.i - b.i)
        .map((x) => x.r),
    [ranked]
  );
  const safetyLine = ordered.findIndex((r) => flagsOn(r) > 0);

  const selected = useMemo(
    () => ordered.find((r) => r.scenario_id === selectedId) ?? ordered[0],
    [ordered, selectedId]
  );

  /* Whatever the reviewer is measuring against: the reading that changes
   * nothing, where the graph generated one. */
  const compare = useMemo(
    () => ordered.find((r) => r.delta.actions.length === 0)?.kpis,
    [ordered]
  );

  /* The recommendation's change diff is the authoritative one, and a field's
   * lineage does not depend on which reading proposes it - so it seeds the
   * impacted-output map for every candidate that touches the same field. */
  const recLines = useMemo(
    () => new Map<string, ChangeSummaryLine>(
      (recommendation?.changes ?? []).map(
        (c) => [`${c.entity_id}:${c.attribute_path}`, c] as const
      )
    ),
    [recommendation]
  );
  const seeded = useMemo(() => {
    const m = new Map<string, Impacted>();
    for (const [ref, c] of recLines) {
      m.set(ref, {
        assets: c.impacted_assets ?? [],
        channels: c.impacted_channels ?? [],
      });
    }
    return m;
  }, [recLines]);

  const changes = useMemo<ChangeRow[]>(() => {
    const sets = (selected?.delta.actions ?? []).filter(
      (a): a is SetAttributeAction => a.kind === "SET_ATTRIBUTE"
    );
    return sets.map((a) => {
      const ref = `${a.entity_id}:${a.attribute_path}`;
      const def = attrs.get(a.attribute_path);
      const line = recLines.get(ref);
      return {
        ref,
        entity_id: a.entity_id,
        attribute_path: a.attribute_path,
        old_value: a.old_value,
        new_value: a.new_value,
        unit: a.unit ?? def?.unit ?? line?.unit ?? null,
        source: a.source ?? line?.source ?? null,
        confidence: a.confidence ?? line?.confidence ?? null,
        safety: def?.safety_class ?? line?.safety ?? false,
        ordered: def?.ordered ?? true,
      };
    });
  }, [selected, attrs, recLines]);

  /* Impacted outputs the recommendation did not already name, read off the
   * catalog's derivation index one field at a time. */
  useEffect(() => {
    const wanted = changes
      .map((c) => c.ref)
      .filter((ref) => !seeded.has(ref) && !asked.current.has(ref))
      .slice(0, 8);
    if (wanted.length === 0) return;
    for (const ref of wanted) asked.current.add(ref);

    let live = true;
    (async () => {
      for (const ref of wanted) {
        let found: Impacted;
        try {
          const d = await api.derivation(ref);
          found = {
            assets: d.assets.map((a) => a.id),
            channels: d.channels,
          };
        } catch {
          found = { assets: [], channels: [], unknown: true };
        }
        if (!live) return;
        setLineage((prev) => ({ ...prev, [ref]: found }));
      }
    })();
    return () => { live = false; };
  }, [changes, seeded]);

  const impactOf = (ref: string): Impacted | undefined =>
    seeded.get(ref) ?? lineage[ref];

  /* Validate the same change set against the same catalog a second time. The
   * trace hash either agrees or it does not, which is the determinism claim
   * made checkable rather than asserted. */
  async function revalidate(s: SimScenario) {
    setBusy(true);
    try {
      const again = await api.simulate(s.delta, run?.values.as_of);
      setRecheck({
        scenario_id: s.scenario_id,
        hash: again.trace_hash,
        agrees: again.trace_hash === s.trace_hash,
        ms: again.runtime_ms,
      });
    } catch (e) {
      toast.error("Re-validation failed", String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!run || ordered.length === 0) {
    return (
      <>
        <PageHeader section="scenarios" />
        <Panel>
          <EmptyState art={<ArtNoOptions />} title="No readings yet">
            Start a correction run from the Ingest Fabric. Every reading of the
            supplier document — base only, a named variant, all variants — is
            validated against the channel rules and lands here with what it
            would change and what it would block.
          </EmptyState>
        </Panel>
      </>
    );
  }

  const blocking = selected ? firstHard(selected.violations) : undefined;

  return (
    <>
      <PageHeader
        section="scenarios"
        actions={
          <Button
            onClick={onRefresh}
            icon={<IconRefresh size={14} />}
            iconOnly
            aria-label="Refresh"
          />
        }
      />

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
        {/* First thing on the page, not the last thing in the corner. Every
            figure below comes out of the validator, and this is the control
            that lets a sceptic watch it produce them a second time. */}
        {selected && (
          <Determinism
            scenario={selected}
            recheck={
              recheck?.scenario_id === selected.scenario_id ? recheck : null
            }
            busy={busy}
            onRevalidate={() => revalidate(selected)}
          />
        )}

        <Panel
          title={`Readings of this correction (${ordered.length})`}
          subtitle="safety first — an open safety flag never outranks a clean reading"
          flush
          style={{ ["--table-min-w" as string]: "1080px" }}
        >
          <Table scroll>
            <thead>
              <tr>
                <Th num>#</Th>
                <Th>Reading</Th>
                <Th>Evidence</Th>
                <Th num>Fields</Th>
                <Th num>Assets stale</Th>
                <Th num>Channels blocked</Th>
                <Th num>Listings ready</Th>
                <Th>Safety</Th>
                <Th>Publishable</Th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((r, i) => {
                const flags = flagsOn(r);
                const confidence = r.delta.scope?.confidence;
                const hard = firstHard(r.violations);
                return (
                  <Fragment key={r.scenario_id}>
                    {i === safetyLine && safetyLine > 0 && <SafetyLine />}
                    <Tr
                      selected={selected?.scenario_id === r.scenario_id}
                      onClick={() => setSelectedId(r.scenario_id)}
                    >
                      <Td num className="text-faint">{i + 1}</Td>
                      <Td>
                        <div className="flex flex-wrap items-center gap-1.5">
                          {r.scenario_id === recommendedId && (
                            <Badge tone="ok">PICK</Badge>
                          )}
                          <span className="font-medium">{r.name}</span>
                          <span className="font-mono text-2xs text-faint">
                            {r.scenario_id}
                          </span>
                        </div>
                        <div className="mt-1">
                          <ScopeReading scope={r.delta.scope} name={name} />
                        </div>
                      </Td>
                      <Td>
                        <Tooltip
                          content={
                            r.delta.scope?.rationale ||
                            "No rationale recorded for this reading."
                          }
                        >
                          <div className="flex w-[92px] flex-col gap-1">
                            <span className="font-mono text-sm tabular-nums">
                              {typeof confidence === "number"
                                ? `${(confidence * 100).toFixed(0)}%`
                                : "—"}
                            </span>
                            {typeof confidence === "number" && (
                              <ProgressBar
                                value={confidence * 100}
                                ariaLabel="evidence confidence"
                              />
                            )}
                          </div>
                        </Tooltip>
                      </Td>
                      <Td num>{fmt.count(r.kpis.fields_affected)}</Td>
                      <Td num>{fmt.count(r.kpis.assets_stale)}</Td>
                      <Td num>{fmt.count(r.kpis.channels_blocked)}</Td>
                      <Td num>{r.kpis.listings_ready_pct.toFixed(1)}%</Td>
                      <Td>
                        {flags > 0 ? (
                          <SafetyFlag count={flags} />
                        ) : (
                          <span className="text-sm text-faint">none</span>
                        )}
                      </Td>
                      <Td>
                        {r.feasible ? (
                          <Badge tone="ok">can publish</Badge>
                        ) : (
                          <Tooltip
                            content={
                              hard?.detail ??
                              "A hard channel rule fails under this reading."
                            }
                          >
                            <div className="flex max-w-[240px] flex-col gap-0.5">
                              <span>
                                <Badge tone="danger" dot>cannot publish</Badge>
                              </span>
                              <span className="truncate text-xs text-faint">
                                {hard?.detail ?? "a hard rule fails"}
                              </span>
                            </div>
                          </Tooltip>
                        )}
                      </Td>
                    </Tr>
                  </Fragment>
                );
              })}
            </tbody>
          </Table>
        </Panel>

        {selected && (
          <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(340px,1fr)]">
            <Panel
              title={`Detail — ${selected.name}`}
              subtitle={selected.scenario_id}
            >
              <div className="flex flex-col gap-3">
                <p className="text-sm leading-relaxed text-muted">
                  {selected.summary}
                </p>

                <ScopeEvidence scope={selected.delta.scope} name={name} />

                <KpiStrip kpis={selected.kpis} compare={compare} />

                <Divider />

                <Section label={`Changes (${changes.length})`}>
                  {changes.length === 0 ? (
                    <p className="text-sm leading-relaxed text-muted">
                      This reading moves no stored value.
                      {selected.delta.actions.length > 0
                        ? " It only changes what publishes."
                        : " Nothing would be republished."}
                    </p>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {changes.map((c) => (
                        <ChangeCard
                          key={c.ref}
                          change={c}
                          impact={impactOf(c.ref)}
                          name={name}
                        />
                      ))}
                    </div>
                  )}
                </Section>

                <Divider />

                <Section label="What it would do">
                  {selected.delta.actions.length === 0 ? (
                    <p className="text-sm leading-relaxed text-muted">
                      No change — this is the reading every other one is
                      measured against.
                    </p>
                  ) : (
                    <div className="flex flex-col gap-2">
                      <ActionList
                        actions={selected.delta.actions}
                        name={name}
                      />
                      <ol className="flex flex-col gap-1.5">
                        {selected.delta.actions.map((a, i) => (
                          <li
                            key={a.id ?? i}
                            className="flex items-start gap-2 text-sm"
                          >
                            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-faint" />
                            <span className="min-w-0 flex-1 text-muted">
                              {describeAction(a, name)}
                            </span>
                            {a.source && <SourceCite source={a.source} />}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}
                </Section>
              </div>
            </Panel>

            <Panel
              title={selected.feasible ? "Rules checked" : "Why it cannot publish"}
              tone={selected.feasible ? undefined : "danger"}
            >
              <div className="flex flex-col gap-3">
                {!selected.feasible && (
                  <p className="text-sm leading-relaxed text-muted">
                    This reading is kept on the list with its reason.
                    {blocking
                      ? ` ${blocking.channel_id ?? blocking.entity_id} is what binds.`
                      : ""}
                  </p>
                )}
                <Violations violations={selected.violations} />
              </div>
            </Panel>
          </div>
        )}
      </div>
    </>
  );
}

/* --- the safety rule, drawn ----------------------------------------------- */

/** The line the ranking may not cross.
 *
 * Everything below it moves an allergen or another safety-class value. Sorting
 * them down is a decision, and a decision the reviewer cannot see is a decision
 * they cannot check - so it is stated in the table rather than hidden in a
 * comparator.
 */
function SafetyLine() {
  return (
    <tr className="bg-danger-soft">
      <td colSpan={9} className="border-y border-danger-border px-2.5 py-1.5">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <IconAlert size={13} className="shrink-0 text-danger-text" />
          <span className="font-semibold uppercase tracking-caps text-danger-text">
            safety line
          </span>
          <span className="text-muted">
            Everything below moves a safety-class value. It cannot outrank
            anything above, whatever else it wins on.
          </span>
        </div>
      </td>
    </tr>
  );
}

/* --- detail pieces --------------------------------------------------------- */

/** Why this reading, in the words of the evidence that produced it. */
function ScopeEvidence({ scope, name }: {
  scope?: ChangeScope;
  name: NameLookup;
}) {
  const confidence = scope?.confidence;
  return (
    <div className="flex flex-col gap-1.5 rounded-sm border border-subtle bg-sunken px-2.5 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-2xs uppercase tracking-caps text-faint">
          reads the correction as
        </span>
        <ScopeReading scope={scope} name={name} max={6} />
        {typeof confidence === "number" && (
          <Tooltip content="How sure the evidence is that the correction applies to exactly these entities.">
            <span className="ml-auto font-mono text-xs text-muted">
              evidence {(confidence * 100).toFixed(0)}%
            </span>
          </Tooltip>
        )}
      </div>
      {scope?.rationale && (
        <p className="text-sm leading-relaxed text-muted">{scope.rationale}</p>
      )}
      {scope?.evidence && scope.evidence.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-2xs uppercase tracking-caps text-faint">
            from
          </span>
          {scope.evidence.map((e) => (
            <Code key={e}>{e}</Code>
          ))}
        </div>
      )}
    </div>
  );
}

/** One corrected field, end to end: source document → old value → new value →
 *  what is still carrying the old one. The brief asks for exactly this chain on
 *  every generated change, so it is one card rather than four columns that can
 *  drift apart. */
function ChangeCard({ change, impact, name }: {
  change: ChangeRow;
  impact?: Impacted;
  name: NameLookup;
}) {
  const c = change;
  const label = name(c.attribute_path);
  const entity = name(c.entity_id);
  return (
    <div className="flex flex-col gap-1.5 rounded-sm border border-subtle bg-sunken px-2.5 py-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <EntityChip id={c.entity_id} label={entity} />
        <span className="text-sm font-medium text-fg">
          {label ?? c.attribute_path}
        </span>
        {label && label !== c.attribute_path && <Code>{c.attribute_path}</Code>}
        {c.safety && <SafetyFlag count={1} className="ml-auto" />}
      </div>

      <ValueDiff
        oldValue={c.old_value}
        newValue={c.new_value}
        unit={c.unit}
        ordered={c.ordered}
      />

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="inline-flex items-center gap-1.5">
          <span className="text-2xs uppercase tracking-caps text-faint">
            source
          </span>
          <SourceCite source={c.source} />
        </span>
        {typeof c.confidence === "number" && (
          <Tooltip content="How sure the model was of this value when it read it out of the document. A safety-class value read below the gate withholds the listing rather than publishing it.">
            <span className="font-mono text-xs text-faint">
              read at {(c.confidence * 100).toFixed(0)}%
            </span>
          </Tooltip>
        )}
        <span className="inline-flex items-center gap-1.5">
          <span className="text-2xs uppercase tracking-caps text-faint">
            impacts
          </span>
          {!impact ? (
            <span className="text-sm text-faint">checking lineage…</span>
          ) : impact.unknown ? (
            <span className="text-sm text-faint">lineage unavailable</span>
          ) : (
            <ImpactedOutputs
              assets={impact.assets}
              channels={impact.channels}
            />
          )}
        </span>
      </div>
    </div>
  );
}

/** The determinism claim, made checkable.
 *
 * Two validations of the same change set against the same catalog must produce
 * the same trace hash. The button runs the second one, in front of the person
 * being asked to trust the first.
 *
 * It used to sit under the violations list in the bottom-right panel. For a
 * technical audience that live re-validation is the most persuasive thing in
 * the product and it was reading as a footnote, so it now leads the page: full
 * width, hashes at a size that can be compared across a room, and the button
 * that produces the second one in the panel's own header.
 */
function Determinism({ scenario, recheck, busy, onRevalidate }: {
  scenario: SimScenario;
  recheck: Recheck | null;
  busy: boolean;
  onRevalidate: () => void;
}) {
  return (
    <Panel
      tone="accent"
      icon={<IconTrace size={14} />}
      title="Same change set, same catalog, same hash"
      subtitle={selectedLine(scenario)}
      actions={
        <Button tone="primary" size="md" loading={busy} onClick={onRevalidate}>
          Validate again
        </Button>
      }
    >
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <HashRead
            label="validated"
            hash={scenario.trace_hash}
            ms={scenario.runtime_ms}
          />
          {recheck && (
            <>
              <span aria-hidden="true" className="text-faint">→</span>
              <div className="animate-rise-in">
                <HashRead
                  label="validated again"
                  hash={recheck.hash}
                  ms={recheck.ms}
                  agrees={recheck.agrees}
                />
              </div>
              <Badge tone={recheck.agrees ? "ok" : "danger"} dot>
                {recheck.agrees ? "same verdict" : "verdict moved"}
              </Badge>
            </>
          )}
        </div>
        <p className="text-sm leading-relaxed text-muted">
          {recheck
            ? recheck.agrees
              ? "Validated twice against the same catalog, same hash both times."
              : "The catalog has moved since this reading was validated. The verdict above no longer stands."
            : "Run the same validation again — the hash should not move."}
        </p>
      </div>
    </Panel>
  );
}

/** Which reading the hash belongs to. The band sits above the table, so it has
 *  to say what it re-validated rather than leaving it to the selected row. */
const selectedLine = (s: SimScenario) => `${s.name} · ${s.scenario_id}`;

/** One trace hash, at a size two of them can be compared at. */
function HashRead({ label, hash, ms, agrees }: {
  label: string;
  hash: string;
  ms: number;
  /** Set on the second read only; colours the hash by whether it moved. */
  agrees?: boolean;
}) {
  return (
    <Tooltip content={`${hash}\nThe validator's trace hash, in ${ms}ms.`} mono>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="text-2xs uppercase tracking-caps text-faint">
          {label}
        </span>
        <span
          className={cn(
            "truncate font-mono text-md tabular-nums",
            agrees === undefined ? "text-fg"
              : agrees ? "text-ok-text" : "text-danger-text"
          )}
        >
          {hash.slice(0, 16)}
        </span>
        <span className="font-mono text-2xs text-faint tabular-nums">
          {ms}ms
        </span>
      </div>
    </Tooltip>
  );
}
