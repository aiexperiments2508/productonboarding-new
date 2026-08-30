import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";

/* The peer and toolset call feed, merged.
 *
 * Two logs on the server - `sc/a2a/client.py` records delegations to the four
 * peer agents, and `sc/mcp/_runtime.py` records tool calls at the MCP boundary
 * - and they are kept apart there for a good reason: one is a capability
 * crossing an organisational seam, the other is a lookup into somebody else's
 * system. On the System Control screen each gets its own console and the
 * distinction is worth the space.
 *
 * In the header it is not. What a reviewer wants from a status bar is "is
 * anything running, and what", so the two are merged into one feed here and
 * the `kind` field keeps the distinction available to anything that wants it.
 *
 * Polled rather than streamed. The SSE channel carries released events, and
 * putting tool traffic through it would mean the event plane also delivers
 * observability about itself - the poll is a few hundred bytes and stays out
 * of the way of the thing being observed.
 */

export type ActivityKind = "agent" | "tool";

export interface ActivityCall {
  /** Stable across polls: the two logs number their own sequences. */
  key: string;
  kind: ActivityKind;
  /** What ran - the peer id, or the tool. */
  name: string;
  /** Who owns it - the peer's skill, or the toolset the tool belongs to. */
  owner: string;
  /** Which path it actually took: "a2a"/"stdio" crossed a boundary,
   *  "in-process" did not. Recorded, never inferred. */
  transport: string;
  ms: number;
  ok: boolean;
  /** Epoch seconds, as `time.time()` wrote it. */
  at: number;
}

/** Who exists, as opposed to who has been called.
 *
 *  Read from `/api/a2a/agents` and `/api/mcp/servers` rather than written
 *  here: the peer roster and the toolset partition are the server's to declare,
 *  and a display name hard-coded in the header is a display name that goes
 *  stale the first time a peer is renamed. Every lookup falls back to the id,
 *  so an unknown peer degrades to something a reviewer can still search for. */
export interface ActivityRoster {
  /** Peer id -> the name on its published Agent Card. */
  peerNames: Record<string, string>;
  /** Toolset id -> its title, and the system it stands in for. */
  toolsetNames: Record<string, string>;
  toolsetOwners: Record<string, string>;
  peers: number;
  toolsets: number;
  /** Toolsets retired after a failed spawn; their calls ran in-process. */
  degraded: string[];
}

export interface Activity {
  calls: ActivityCall[];
  /** Newest call, or null before anything has run. */
  latest: ActivityCall | null;
  agentCalls: number;
  toolCalls: number;
  /** How many of the calls crossed a real process or network boundary. */
  crossings: number;
  failures: number;
  roster: ActivityRoster;
}

/** While a run is live the feed is the most interesting thing on the screen,
 *  so it is polled at roughly the rate a node takes to execute. Idle, it is
 *  polled slowly enough that a parked demo costs nothing. */
const POLL_LIVE_MS = 700;
const POLL_IDLE_MS = 3000;

const EMPTY_ROSTER: ActivityRoster = {
  peerNames: {}, toolsetNames: {}, toolsetOwners: {},
  peers: 0, toolsets: 0, degraded: [],
};

interface Feed {
  calls: ActivityCall[];
  latest: ActivityCall | null;
  agentCalls: number;
  toolCalls: number;
  crossings: number;
  failures: number;
}

const EMPTY_FEED: Feed = {
  calls: [], latest: null, agentCalls: 0, toolCalls: 0, crossings: 0,
  failures: 0,
};

export function useActivity(live: boolean, limit = 40): Activity {
  const [feed, setFeed] = useState<Feed>(EMPTY_FEED);
  const [roster, setRoster] = useState<ActivityRoster>(EMPTY_ROSTER);

  // The roster is configuration, not traffic: fetched once, not on the poll.
  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([api.a2aAgents(), api.mcpServers()]).then(([a, m]) => {
      if (cancelled) return;
      const next: ActivityRoster = {
        peerNames: {}, toolsetNames: {}, toolsetOwners: {},
        peers: 0, toolsets: 0, degraded: [],
      };
      if (a.status === "fulfilled") {
        for (const agent of a.value.agents) next.peerNames[agent.id] = agent.name;
        next.peers = a.value.agents.length;
        next.degraded.push(...a.value.transport.degraded);
      }
      if (m.status === "fulfilled") {
        for (const server of m.value.servers) {
          next.toolsetNames[server.id] = server.title;
          next.toolsetOwners[server.id] = server.owner;
        }
        next.toolsets = m.value.servers.length;
        next.degraded.push(...m.value.transport.degraded);
      }
      setRoster(next);
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      const [a, m] = await Promise.allSettled([
        api.a2aCalls(limit), api.mcpCalls(limit),
      ]);
      if (cancelled) return;

      const calls: ActivityCall[] = [];
      if (a.status === "fulfilled") {
        for (const c of a.value.calls) {
          calls.push({
            key: `agent-${c.seq}`, kind: "agent", name: c.agent,
            owner: c.skill, transport: c.transport, ms: c.ms, ok: c.ok,
            at: c.at,
          });
        }
      }
      if (m.status === "fulfilled") {
        for (const c of m.value.calls) {
          calls.push({
            key: `tool-${c.seq}`, kind: "tool", name: c.tool,
            owner: c.toolset, transport: c.transport, ms: c.ms, ok: c.ok,
            at: c.at,
          });
        }
      }

      // Both logs are newest-first already; interleaving them by timestamp is
      // what makes the feed read as one sequence of work rather than two.
      calls.sort((x, y) => y.at - x.at);
      const merged = calls.slice(0, limit);

      setFeed({
        calls: merged,
        latest: merged[0] ?? null,
        agentCalls: merged.filter((c) => c.kind === "agent").length,
        toolCalls: merged.filter((c) => c.kind === "tool").length,
        crossings: merged.filter((c) => c.transport !== "in-process").length,
        failures: merged.filter((c) => !c.ok).length,
      });
    };

    tick().catch(() => undefined);
    const timer = setInterval(
      () => tick().catch(() => undefined),
      live ? POLL_LIVE_MS : POLL_IDLE_MS
    );
    return () => { cancelled = true; clearInterval(timer); };
  }, [live, limit]);

  return useMemo(() => ({ ...feed, roster }), [feed, roster]);
}

/** What to call one row. The peer's Agent Card name where the roster has it,
 *  the tool's own name otherwise - a tool name is already a name. */
export function callTitle(call: ActivityCall, roster: ActivityRoster): string {
  return call.kind === "agent"
    ? roster.peerNames[call.name] ?? call.name
    : call.name;
}

/** The line under it: the peer's id and the skill it was asked for, or the
 *  system the toolset stands in for. */
export function callSubtitle(call: ActivityCall, roster: ActivityRoster): string {
  return call.kind === "agent"
    ? `${call.name} · ${call.owner}`
    : roster.toolsetNames[call.owner] ?? call.owner;
}

/** True while a call landed recently enough to still read as "now".
 *  Generous, because the poll interval is part of the delay. */
export function isRecent(call: ActivityCall | null, withinMs = 2500): boolean {
  return !!call && Date.now() - call.at * 1000 < withinMs;
}
