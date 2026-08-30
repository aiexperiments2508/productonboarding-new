import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { A2AAgent, A2ACall, A2ATransport } from "../api";
import { IconDoc, IconRefresh, IconSpark } from "../icons";
import {
  Badge, Button, Code, Panel, SegmentedControl, Skeleton, Tooltip, cn,
  useToast,
} from "../ui";

/* The A2A peers.
 *
 * Four capabilities that are genuinely separable, published as agents another
 * organisation could discover and call: each has an Agent Card at a
 * well-known URL and a JSON-RPC endpoint speaking the A2A task lifecycle.
 *
 * The split is at real seams. The lineage analyst walks the derivation graph,
 * the resolution planner enumerates readings and can enumerate nonsense, the
 * validator has to be reproducible to the digit, and the copywriter writes -
 * four different kinds of work with four different failure modes. A peer can
 * replace any one of them without touching the others, which is the only reason
 * to have a protocol.
 *
 * What is deliberately NOT a peer: the approval gate, and publish. A human
 * decision is not a capability to delegate, and an agent that could publish is
 * an agent that could publish.
 */

const POLL_MS = 2500;

export function A2APanel() {
  const toast = useToast();
  const [agents, setAgents] = useState<A2AAgent[] | null>(null);
  const [transport, setTransport] = useState<A2ATransport | null>(null);
  const [calls, setCalls] = useState<A2ACall[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.a2aAgents()
      .then((r) => { setAgents(r.agents); setTransport(r.transport); })
      .catch(() => setAgents([]));
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    const tick = () => api.a2aCalls(40)
      .then((r) => setCalls(r.calls))
      .catch(() => undefined);
    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => clearInterval(timer);
  }, []);

  async function flip(enabled: boolean) {
    setBusy(true);
    try {
      setTransport(await api.setA2aTransport(enabled));
      toast.notify(
        enabled
          ? "The graph now delegates to its peers over A2A"
          : "The graph now calls its peers in-process");
    } catch (e) {
      toast.error("Could not switch delegation", String(e));
    } finally {
      setBusy(false);
    }
  }

  const overWire = calls.filter((c) => c.transport === "a2a").length;

  return (
    <Panel
      title="A2A peers"
      icon={<IconSpark size={14} />}
      subtitle={agents ? `${agents.length} agents` : undefined}
      actions={
        <Button size="xs" iconOnly aria-label="Refresh"
                icon={<IconRefresh size={13} />} onClick={load} />
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-sm leading-relaxed text-muted">
          Each peer publishes an Agent Card another organisation's agent could
          discover, and answers <Code>message/send</Code> over JSON-RPC. The
          cards are served whether or not this process delegates over the
          protocol — discovery and delegation are different switches.
        </p>

        {/* --- transport ------------------------------------------------- */}
        <div className="flex flex-wrap items-center gap-2 rounded-sm border border-subtle bg-sunken px-2.5 py-2">
          <span className="text-sm text-muted">Graph delegates</span>
          <SegmentedControl
            ariaLabel="A2A delegation"
            value={transport?.enabled ? "a2a" : "in-process"}
            onChange={(v) => flip(v === "a2a")}
            options={[
              { value: "in-process", label: "in-process",
                title: "Call the peer handlers directly" },
              { value: "a2a", label: "over A2A",
                title: "JSON-RPC message/send to each peer" },
            ]}
          />
          {busy && <span className="text-xs text-faint">switching…</span>}
          {transport?.degraded?.length ? (
            <Tooltip content="These peers did not answer, so their work fell back in-process.">
              <Badge tone="warn">{transport.degraded.length} degraded</Badge>
            </Tooltip>
          ) : null}
          {overWire > 0 && <Badge tone="ok" dot>{overWire} over the wire</Badge>}
        </div>

        {/* --- roster ---------------------------------------------------- */}
        {agents === null ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : agents.length === 0 ? (
          <p className="text-sm text-muted">
            No peers mounted. The app runs without them; the graph calls the
            same handlers in-process.
          </p>
        ) : (
          <div className="grid gap-1.5 sm:grid-cols-2">
            {agents.map((agent) => (
              <div
                key={agent.id}
                className="flex flex-col gap-1 rounded-sm border border-subtle bg-sunken p-2.5"
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-medium">{agent.name}</span>
                  <Badge tone="neutral" mono>v{agent.version}</Badge>
                </div>
                <p className="text-xs leading-relaxed text-muted">
                  {agent.description}
                </p>
                <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                  <Tooltip content={agent.skill.description}>
                    <Badge tone="accent" mono>{agent.skill.id}</Badge>
                  </Tooltip>
                  <Tooltip content="The Agent Card another agent would fetch to discover this peer">
                    <a
                      href={agent.card_url}
                      target="_blank"
                      rel="noreferrer"
                      className={cn(
                        "inline-flex items-center gap-1 rounded-xs px-1 py-0.5",
                        "font-mono text-xs text-accent-text",
                        "transition-colors hover:bg-hover"
                      )}
                    >
                      <IconDoc size={11} />
                      agent card
                    </a>
                  </Tooltip>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* --- delegations ----------------------------------------------- */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-caps text-faint">
              Delegations
            </h3>
            <span className="h-px flex-1 bg-subtle" />
            <span className="text-xs text-faint">newest first</span>
          </div>
          {calls.length === 0 ? (
            <p className="text-sm text-muted">
              No delegations yet. Run the correction loop — every lineage walk,
              every scope enumeration and every validation goes to a peer.
            </p>
          ) : (
            <div className="max-h-56 overflow-y-auto rounded-sm border border-subtle">
              {calls.map((call) => (
                <div
                  key={call.seq}
                  className="flex items-center gap-2 border-b border-subtle px-2.5 py-1.5 text-sm last:border-b-0"
                >
                  <Badge
                    tone={call.transport === "a2a" ? "accent" : "neutral"}
                    mono
                  >
                    {call.transport}
                  </Badge>
                  <Code>{call.agent}</Code>
                  <span className="min-w-0 flex-1 truncate text-xs text-faint">
                    {call.skill}
                  </span>
                  <span className="shrink-0 font-mono text-xs text-faint tabular-nums">
                    {call.ms < 1 ? "<1" : call.ms.toFixed(0)}ms
                  </span>
                  {!call.ok && <Badge tone="danger">fell back</Badge>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
