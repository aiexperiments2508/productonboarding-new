import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { Arrival, EstateState } from "../api";
import { IconRefresh } from "../icons";
import {
  Badge, Button, Code, Dot, Panel, Skeleton, Tooltip, cn, useToast,
} from "../ui";

/* The external estate.
 *
 * The MVP had four suppliers written as tuples in the generator and no notion
 * of a *system* at all - which collapsed two different things into one. A
 * supplier is who asserts a value; a system is what carried it. A retailer with
 * one supplier still runs eight systems, and "why is this attribute wrong" is
 * answered by the second one at least as often as by the first.
 *
 * So this panel is about the carriers. Ten of them, each with an owner, each
 * declaring what it emits and how badly it behaves, each delivering in batches
 * at intervals it chooses. What a reader should take from it is that several
 * systems are talking at once and that they are not equally trustworthy.
 *
 * Two things here are deliberately not decoration:
 *
 * The **defect count** is not a health score somebody tuned. Every defect was
 * stamped by the system that introduced it, drawn from a closed set, and every
 * member of that set is detected by a deterministic check - so the number is
 * the answer key rather than an impression of one.
 *
 * The **connect field** takes a URL and performs a real MCP handshake. An
 * address that does not answer produces a degraded connection carrying the
 * reason, which is why the failure case is worth showing rather than hiding:
 * the point of a plug-and-play estate is that plugging something in can fail
 * visibly instead of silently.
 */

const POLL_MS = 2000;

/** Recent arrivals to keep on screen. The feed is a pulse, not a ledger - the
 *  audit trail is where anybody goes to read history. */
const FEED_ROWS = 14;

/** How long after its last delivery a system still reads as live. Long enough
 *  to span the widest declared interval, so a slow feed does not flicker
 *  between live and idle while it is behaving perfectly. */
const LIVE_WINDOW_MS = 12_000;

type Health = "live" | "idle" | "degraded";

function healthOf(
  system: EstateState["systems"][number],
  connection: EstateState["connections"][number] | undefined,
): Health {
  if (connection && connection.state !== "connected") return "degraded";
  if (!system.last_seen) return "idle";
  const since = Date.now() - new Date(system.last_seen).getTime();
  return since < LIVE_WINDOW_MS ? "live" : "idle";
}

const HEALTH_LABEL: Record<Health, string> = {
  live: "delivering",
  idle: "quiet",
  degraded: "not answering",
};

export function EstatePanel() {
  const toast = useToast();
  const [estate, setEstate] = useState<EstateState | null>(null);
  const [feed, setFeed] = useState<Arrival[]>([]);
  const [url, setUrl] = useState("");
  const [connecting, setConnecting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [next, landed] = await Promise.all([
        api.estate(),
        api.arrivals(FEED_ROWS),
      ]);
      setEstate(next);
      setFeed(landed.arrivals);
    } catch {
      /* A poll that misses is not worth a toast; the next one is 2s away. */
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const connect = useCallback(async () => {
    const address = url.trim();
    if (!address) return;
    setConnecting(true);
    try {
      const record = await api.connectSystem(address);
      // A degraded connection is a successful request. Reporting it as an
      // error would be wrong twice: the call worked, and the operator needs the
      // reason rather than a red banner saying something went wrong.
      toast.push({
        tone: record.state === "connected" ? "ok" : "warn",
        title:
          record.state === "connected"
            ? `Connected ${record.title}`
            : `${record.title} did not answer`,
        detail:
          record.state === "connected"
            ? `${record.discovered_tools.length} tool(s) declared`
            : record.detail,
      });
      setUrl("");
      refresh();
    } catch (e) {
      toast.error("Could not reach that address", String(e));
    } finally {
      setConnecting(false);
    }
  }, [refresh, toast, url]);

  const disconnect = useCallback(
    async (id: string) => {
      try {
        await api.disconnectSystem(id);
        toast.push({
          tone: "ok",
          title: `Disconnected ${id}`,
          // Said out loud, because it is the surprising and correct behaviour.
          detail: "what it delivered stays on the record",
        });
        refresh();
      } catch (e) {
        toast.error("Could not disconnect", String(e));
      }
    },
    [refresh, toast],
  );

  if (!estate) {
    return (
      <Panel title="The estate" subtitle="Systems feeding the catalog">
        <Skeleton className="h-40" />
      </Panel>
    );
  }

  const connectionById = new Map(estate.connections.map((c) => [c.id, c]));
  const delivering = estate.systems.filter(
    (s) => healthOf(s, connectionById.get(s.id)) === "live",
  ).length;
  const defective = Object.values(estate.defect_counts).reduce((a, b) => a + b, 0);

  return (
    <Panel
      title="The estate"
      subtitle={
        `${estate.systems.length} systems · ${delivering} delivering · ` +
        `${defective} arrival(s) carrying a named defect`
      }
      actions={
        <Button tone="ghost" size="sm" onClick={refresh} icon={<IconRefresh />}>
          Refresh
        </Button>
      }
    >
      <div className="grid gap-2 md:grid-cols-2">
        {estate.systems.map((system) => {
          const connection = connectionById.get(system.id);
          const health = healthOf(system, connection);
          return (
            <article
              key={system.id}
              className={cn(
                "flex flex-col gap-1.5 rounded-md border p-2.5",
                health === "degraded"
                  ? "border-estate-degraded-border bg-estate-degraded-soft"
                  : "border-subtle bg-raised",
              )}
            >
              <header className="flex items-center gap-2">
                <Dot
                  tone={
                    health === "live" ? "ok" : health === "degraded" ? "warn" : "neutral"
                  }
                  pulse={health === "live"}
                />
                <span className="min-w-0 truncate font-medium text-fg">
                  {system.title}
                </span>
                <Tooltip content={HEALTH_LABEL[health]}>
                  <span className="ml-auto shrink-0">
                    <Badge tone={system.well_behaved ? "ok" : "warn"}>
                      {system.well_behaved ? "conforms" : `${system.defects.length} defect kind(s)`}
                    </Badge>
                  </span>
                </Tooltip>
              </header>

              <p className="text-2xs uppercase tracking-caps text-faint">
                {system.owner}
              </p>

              <div className="flex flex-wrap items-center gap-1">
                {system.emits.map((kind) => (
                  <Code key={kind}>{kind}</Code>
                ))}
              </div>

              <footer className="flex items-center gap-2 text-xs text-muted">
                <span>
                  {system.arrivals ?? 0} delivered in {system.batches ?? 0} batch
                  {(system.batches ?? 0) === 1 ? "" : "es"}
                </span>
                {(system.defective ?? 0) > 0 && (
                  <Badge tone="warn">{system.defective} defective</Badge>
                )}
                {connection && (
                  <Button
                    tone="ghost"
                    size="sm"
                    className="ml-auto"
                    onClick={() => disconnect(system.id)}
                  >
                    Disconnect
                  </Button>
                )}
              </footer>
            </article>
          );
        })}
      </div>

      {/* Connecting something new. A URL and a handshake - no registration, no
          restart, and a failure that says what went wrong. */}
      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-subtle pt-3">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") connect(); }}
          placeholder="http://host/mcp — connect another system"
          aria-label="Address of a system to connect"
          className={cn(
            "min-w-0 flex-1 rounded-sm border border-line bg-canvas px-2 py-1",
            "font-mono text-xs text-fg placeholder:text-faint",
            "focus:outline-none focus:ring-2 focus:ring-focus",
          )}
        />
        <Button size="sm" onClick={connect} disabled={connecting || !url.trim()}>
          {connecting ? "Handshaking…" : "Connect"}
        </Button>
      </div>

      {estate.connections.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {estate.connections.map((c) => (
            <li
              key={c.id}
              className="flex items-center gap-2 text-xs text-muted"
            >
              <Badge tone={c.state === "connected" ? "ok" : "warn"} dot>
                {c.state}
              </Badge>
              <Code>{c.url}</Code>
              <span className="min-w-0 truncate">{c.detail}</span>
              {c.collisions.length > 0 && (
                <Tooltip content="A built-in toolset already owns this name; the built-in keeps it.">
                  <span className="shrink-0">
                    <Badge tone="danger">shadowing {c.collisions.join(", ")}</Badge>
                  </span>
                </Tooltip>
              )}
              <Button
                tone="ghost"
                size="sm"
                className="ml-auto"
                onClick={() => disconnect(c.id)}
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}

      {/* The pulse. Batches landing, with the system that sent each one - this
          is where "several systems at once" stops being a claim. */}
      {feed.length > 0 && (
        <ol className="sc-stagger mt-3 flex flex-col gap-1 border-t border-subtle pt-3">
          {feed.map((arrival, i) => (
            <li
              key={arrival.id}
              style={{ ["--i" as string]: i }}
              className="flex items-baseline gap-2 text-xs"
            >
              <span className="shrink-0 font-mono text-2xs text-faint">
                {arrival.system_id}
              </span>
              <span className="shrink-0 font-mono text-2xs text-faint">
                #{arrival.seq}
              </span>
              {arrival.defects.length > 0 ? (
                <Badge tone="warn">{arrival.defects.join(", ")}</Badge>
              ) : (
                <span className="text-muted">clean</span>
              )}
              <span className="ml-auto shrink-0 font-mono text-2xs text-faint">
                {arrival.batch_id}
              </span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}
