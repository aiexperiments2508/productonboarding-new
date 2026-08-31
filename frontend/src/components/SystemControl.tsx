import { useEffect, useState } from "react";
import { api, fmt } from "../api";
import type { Health, IndexStatus, ModelListing, ReplayState } from "../api";
import { PageHeader } from "../app/shell/PageHeader";
import {
  IconJump, IconPause, IconPlay, IconRefresh, IconReset, IconStep,
} from "../icons";
import {
  Badge, Button, Code, Divider, Dot, Field, Panel, ProgressBar, Section,
  SegmentedControl, Select, Skeleton, Stat, Tooltip, cn, useToast,
} from "../ui";
import { ProvenanceLegend } from "./Approvals";
import { EvidenceAllowlist } from "./EvidenceLog";
import { A2APanel } from "./A2APanel";
import { CapabilityBoard } from "./CapabilityBoard";
import { FactLineage } from "./FactLineage";
import { MCPConsole } from "./MCPConsole";

/* System control.
 *
 * The machinery under the factory: the replay transport that releases supplier
 * documents, the model the graph reads them with, and the response cache that
 * makes a rehearsal deterministic and survivable when the venue's network is
 * not.
 *
 * The transport is also in the status strip, deliberately duplicated. This is
 * the full panel - speed, progress, the reset - and the strip is the subset
 * you need while watching the catalog. Neither is the other's shortcut.
 */

const SPEEDS = [1, 5, 10, 50];

export function SystemControl({ health, replay, onReplay, busy, onRefresh }: {
  health: Health | null;
  replay: ReplayState | null;
  onReplay: (body: { action: string; steps?: number; speed?: number; to_seq?: number }) => void;
  busy: boolean;
  onRefresh: () => Promise<void>;
}) {
  const toast = useToast();
  const [models, setModels] = useState<ModelListing | null>(null);
  const [index, setIndex] = useState<IndexStatus | null>(null);
  const [usage, setUsage] = useState<Awaited<ReturnType<typeof api.usage>> | null>(null);
  const [allowlist, setAllowlist] =
    useState<Awaited<ReturnType<typeof api.evidenceTools>> | null>(null);
  const [working, setWorking] = useState<string | null>(null);

  const refresh = () => {
    api.models().then(setModels).catch(() => undefined);
    api.sopStatus().then(setIndex).catch(() => undefined);
    api.usage().then(setUsage).catch(() => undefined);
    api.evidenceTools().then(setAllowlist).catch(() => undefined);
  };
  useEffect(refresh, []);

  // Outcomes go to a toast rather than to a panel at the bottom of the column.
  // The old "last action" panel reported the result of a button several hundred
  // pixels away from the button, which is a place nobody looks.
  async function act(label: string, fn: () => Promise<string>) {
    setWorking(label);
    try {
      toast.notify(await fn());
    } catch (e) {
      toast.error("Action failed", String(e));
    } finally {
      setWorking(null);
      refresh();
    }
  }

  const progress = replay && replay.total_events
    ? (replay.cursor_seq / replay.total_events) * 100 : 0;
  const running = !!replay?.running;

  return (
    <>
      <PageHeader
        section="system"
        actions={
          <Button
            onClick={() => { onRefresh(); refresh(); }}
            icon={<IconRefresh size={14} />}
          >
            Refresh
          </Button>
        }
      />

      <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-2">
        <div className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
          <Panel
            title="Replay transport"
            actions={
              replay && (
                <span className="font-mono text-sm text-faint tabular-nums">
                  {replay.cursor_seq}/{replay.total_events}
                </span>
              )
            }
          >
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="font-mono text-md tabular-nums">
                  {replay?.sim_clock ? fmt.stamp(replay.sim_clock) : "not started"}
                </span>
                <Badge tone={running ? "ok" : "neutral"} dot={running}>
                  {running ? `running ${replay.speed}x` : "paused"}
                </Badge>
              </div>

              <ProgressBar value={progress} ariaLabel="Replay progress" />

              <div className="flex flex-wrap items-center gap-1.5">
                <Button
                  disabled={busy}
                  icon={running ? <IconPause size={14} /> : <IconPlay size={14} />}
                  onClick={() => onReplay({ action: running ? "PAUSE" : "START" })}
                >
                  {running ? "Pause" : "Start"}
                </Button>
                <Button
                  disabled={busy}
                  icon={<IconStep size={14} />}
                  onClick={() => onReplay({ action: "STEP", steps: 1 })}
                >
                  Step 1
                </Button>
                <Button
                  disabled={busy}
                  icon={<IconStep size={14} />}
                  onClick={() => onReplay({ action: "STEP", steps: 10 })}
                >
                  Step 10
                </Button>
                <Tooltip content="Release every event up to the finale inject">
                  <Button
                    tone="primary"
                    disabled={busy}
                    icon={<IconJump size={14} />}
                    onClick={() => onReplay({ action: "JUMP" })}
                  >
                    Jump to inject
                  </Button>
                </Tooltip>
                <Button
                  tone="danger"
                  disabled={busy}
                  icon={<IconReset size={14} />}
                  onClick={() => onReplay({ action: "RESET" })}
                >
                  Reset
                </Button>
              </div>

              <Field label="Speed" width={52}>
                <SegmentedControl
                  ariaLabel="Replay speed"
                  value={String(replay?.speed ?? 1)}
                  onChange={(v) => onReplay({ action: "SPEED", speed: Number(v) })}
                  options={SPEEDS.map((s) => ({
                    value: String(s), label: `${s}x`,
                  }))}
                />
              </Field>

              <p className="text-sm leading-relaxed text-muted">
                Stepping one event at a time is the way to narrate the
                correction — the portal feed that certified the old value, the
                corrected spec sheet, and the marketplace rejection that follows
                arrive as separate events. The same controls are in the status
                bar, so you can step the tape without leaving the Ingest Fabric.
              </p>
            </div>
          </Panel>

          <Panel
            title="Model gateway"
            actions={
              <Button
                size="xs"
                icon={<IconRefresh size={13} />}
                onClick={() =>
                  act("models", async () => {
                    const m = await api.models(true);
                    setModels(m);
                    return `${m.models.length} models from ${m.source}`;
                  })
                }
              >
                refresh
              </Button>
            }
          >
            {!models ? (
              <div className="flex flex-col gap-2">
                <Skeleton className="h-4 w-2/5" />
                <Skeleton className="h-7 w-full" />
                <Skeleton className="h-7 w-full" />
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <Badge tone={models.source === "gateway" ? "ok" : "warn"}>
                    {models.source === "gateway"
                      ? "live from gateway" : "config fallback"}
                  </Badge>
                  <span className="truncate font-mono text-xs text-faint">
                    {models.gateway_url}
                  </span>
                </div>
                {models.error && (
                  <div className="text-sm text-warn-text">{models.error}</div>
                )}

                <p className="text-sm leading-relaxed text-muted">
                  What this model is asked for is bounded: read the corrected
                  values out of supplier prose, argue which variants they apply
                  to, flag copy the correction has made untrue, and rewrite the
                  sentences. Every figure, verdict and publish decision comes
                  from the validator instead, so changing the model here cannot
                  change what the factory publishes.
                </p>

                <Field label="Chat model">
                  <Select
                    ariaLabel="Chat model"
                    className="w-full"
                    value={models.active}
                    onValueChange={(v) =>
                      act("model", async () => {
                        const r = await api.setModel({ model: v });
                        setModels(r);
                        const p = r.persisted?.updated ?? r.persisted?.created ?? {};
                        return `active model is ${r.active}` +
                          (Object.keys(p).length ? " — written back to .env" : "");
                      })
                    }
                    options={(["reasoning", "fast"] as const).flatMap((tier) =>
                      (models.by_tier[tier] ?? []).map((id) => ({
                        value: id, label: id, group: tier,
                      }))
                    )}
                  />
                </Field>

                <Field label="Embeddings">
                  <Select
                    ariaLabel="Embedding model"
                    className="w-full"
                    value={models.embed}
                    onValueChange={(v) =>
                      act("embed", async () => {
                        const r = await api.setModel({ embed_model: v });
                        setModels(r);
                        return `embedding model is ${r.embed} — re-index to apply`;
                      })
                    }
                    options={(models.by_tier.embedding ?? [models.embed]).map(
                      (id) => ({ value: id, label: id })
                    )}
                  />
                </Field>

                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    loading={working === "test"}
                    onClick={() =>
                      act("test", async () => {
                        const r = await api.testModel();
                        return r.ok
                          ? `${r.model} replied in ${r.latency_ms}ms: "${r.response}"`
                          : `${r.model} failed — ${r.error}`;
                      })
                    }
                  >
                    Test model
                  </Button>
                  <label className="flex cursor-pointer items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={models.cache_enabled}
                      className="size-3.5 accent-[var(--accent-solid)]"
                      onChange={(e) =>
                        act("cache", async () => {
                          const r = await api.setModel({
                            cache_enabled: e.target.checked,
                          });
                          setModels(r);
                          return `response cache ${r.cache_enabled ? "on" : "off"}`;
                        })
                      }
                    />
                    response cache
                  </label>
                </div>

                <p className="text-sm leading-relaxed text-muted">
                  With the cache on, a repeated call is served from SQLite: the
                  run is deterministic, instant, and unaffected by the network.
                  Turn it off to prove the calls are real.
                </p>

                {usage && (
                  <>
                    <Divider />
                    <div className="grid grid-cols-[repeat(auto-fit,minmax(110px,1fr))] gap-2">
                      <Stat
                        label="Calls"
                        value={String(usage.calls)}
                        sub={`${usage.cache_hits} cache hits`}
                      />
                      <Stat
                        label="Tokens"
                        value={(
                          usage.prompt_tokens + usage.completion_tokens
                        ).toLocaleString()}
                      />
                      <Stat
                        label="Cost"
                        value={`$${usage.cost_usd.toFixed(4)}`}
                        sub={`${usage.avg_latency_ms.toFixed(0)}ms avg`}
                      />
                    </div>
                  </>
                )}
              </div>
            )}
          </Panel>
        </div>

        <div className="flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto [&>*]:shrink-0">
          <Panel title="Service health">
            {!health ? (
              <div className="flex flex-col gap-2">
                {Array.from({ length: 4 }, (_, i) => (
                  <Skeleton key={i} className="h-4 w-full" />
                ))}
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <HealthRow label="API" ok={health.ok}
                           detail="one process, no containers" />
                <HealthRow
                  label="Gateway"
                  ok={health.gateway.ok}
                  detail={health.gateway.circuit?.open
                    ? `circuit open — retrying in ${health.gateway.circuit.retry_in_seconds}s`
                    : health.gateway.url}
                />
                <HealthRow
                  label="Event tape"
                  ok={health.data.events > 0}
                  detail={`${health.data.events} events, ingested to ${health.ingest_cursor}`}
                />
                <HealthRow
                  label="Catalog"
                  ok={health.data.nodes > 0}
                  detail={`${health.data.nodes} catalog nodes, ${health.data.listings} listings, ${health.data.assets} content assets`}
                />
                {!health.gateway.ok && (
                  <p className="text-sm leading-relaxed text-muted">
                    The gateway is unreachable. Every model step falls back to a
                    deterministic path, so the loop still runs — narrative
                    quality degrades, the decision does not.
                  </p>
                )}
              </div>
            )}
          </Panel>

          <Panel
            title="Retrieval index"
            actions={
              <div className="flex items-center gap-1.5">
                <Button
                  size="xs"
                  loading={working === "reindex-lex"}
                  onClick={() =>
                    act("reindex-lex", async () => {
                      const r = await api.reindex(false);
                      return `${r.chunks} chunks, lexical only`;
                    })
                  }
                >
                  re-index (BM25)
                </Button>
                <Button
                  size="xs"
                  loading={working === "reindex"}
                  onClick={() =>
                    act("reindex", async () => {
                      const r = await api.reindex(true);
                      return r.embedded
                        ? `${r.chunks} chunks embedded at ${r.dimensions} dims`
                        : `${r.chunks} chunks, embeddings failed: ${r.embed_error}`;
                    })
                  }
                >
                  re-index (full)
                </Button>
              </div>
            }
          >
            {!index ? (
              <div className="flex flex-col gap-2">
                <Skeleton className="h-5 w-3/5" />
                <Skeleton className="h-4 w-full" />
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge tone="neutral">{index.chunks} chunks</Badge>
                  <Badge tone="neutral">{index.documents} documents</Badge>
                  <Badge tone={index.vectors ? "ok" : "warn"}>
                    {index.vectors ? `dense ${index.dimensions}d` : "lexical only"}
                  </Badge>
                </div>
                <div className="flex flex-wrap items-center gap-2 text-sm text-faint">
                  {Object.entries(index.by_type).map(([k, v]) => (
                    <span key={k} className="flex items-center gap-1">
                      <Code>{k}</Code> {v}
                    </span>
                  ))}
                </div>
                {index.embed_model && (
                  <div className="text-sm text-faint">
                    embedded with {index.embed_model}
                  </div>
                )}
                <p className="text-sm leading-relaxed text-muted">
                  The reference library behind the loop: content standards,
                  channel specifications, policy and postmortems. Retrieval
                  fuses BM25 with dense search, and BM25 alone still answers a
                  query naming a product or an attribute path, so a missing
                  matrix degrades quality rather than breaking search. Press{" "}
                  <Code>⌘K</Code> to search it directly.
                </p>
              </div>
            )}
          </Panel>

          {/* The directory first: it is the answer to "what can this do",
              and the two panels below it are the detail of how. */}
          <CapabilityBoard />

          <A2APanel />

          <MCPConsole />

          <Panel title="Investigator tool allowlist">
            {allowlist ? (
              <EvidenceAllowlist
                tools={allowlist.tools}
                maxPasses={allowlist.max_passes}
                maxPerPass={allowlist.max_requests_per_pass}
              />
            ) : (
              <div className="flex flex-col gap-2">
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/5" />
              </div>
            )}
          </Panel>

          <FactLineage />

          <Panel title="Provenance classes">
            <Section label="The five kinds of knowledge">
              <ProvenanceLegend />
            </Section>
          </Panel>
        </div>
      </div>
    </>
  );
}

function HealthRow({ label, ok, detail }: {
  label: string; ok: boolean; detail: string;
}) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <Dot tone={ok ? "ok" : "danger"} />
      <strong className={cn("w-[84px] shrink-0")}>{label}</strong>
      <span className="min-w-0 truncate text-muted">{detail}</span>
    </div>
  );
}
