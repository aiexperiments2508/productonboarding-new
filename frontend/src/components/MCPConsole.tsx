import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { MCPCall, MCPServer, MCPTransport } from "../api";
import { IconRefresh, IconTrace } from "../icons";
import {
  Badge, Button, Code, Panel, SegmentedControl, Skeleton, Tooltip, cn,
  useToast,
} from "../ui";

/* The MCP toolsets, and traffic crossing them.
 *
 * The brief is sceptical about MCP and says so plainly: it is justified "only
 * if several independently owned systems are exposed as reusable tools;
 * otherwise ordinary APIs are simpler". One server with eighteen flat tools
 * does not pass that test, so the toolset is partitioned the way product
 * information is actually owned in a retailer - the PIM, the channel
 * integration layer, the DAM, the document system, the bus and the publishing
 * pipeline - and only the last of those can change what a channel sees.
 *
 * This panel exists because a partition nobody can see is a claim. The switch
 * flips the transport mid-run, and the log below records which path each call
 * actually took rather than which one was configured.
 */

const POLL_MS = 2500;

export function MCPConsole() {
  const toast = useToast();
  const [servers, setServers] = useState<MCPServer[] | null>(null);
  const [transport, setTransport] = useState<MCPTransport | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [calls, setCalls] = useState<MCPCall[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.mcpServers()
      .then((r) => {
        setServers(r.servers);
        setTransport(r.transport);
        setCounts(r.counts ?? {});
      })
      .catch(() => setServers([]));
  }, []);

  useEffect(load, [load]);

  // The log only moves while something is calling tools, so a slow poll is
  // enough and an idle tab costs almost nothing.
  useEffect(() => {
    const tick = () => api.mcpCalls(40)
      .then((r) => { setCalls(r.calls); setCounts(r.counts ?? {}); })
      .catch(() => undefined);
    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => clearInterval(timer);
  }, []);

  async function flip(enabled: boolean) {
    setBusy(true);
    try {
      setTransport(await api.setMcpTransport(enabled));
      toast.notify(
        enabled
          ? "Evidence lookups now cross a process boundary over stdio"
          : "Evidence lookups now run in-process");
    } catch (e) {
      toast.error("Could not switch the transport", String(e));
    } finally {
      setBusy(false);
    }
  }

  const overWire = calls.filter((c) => c.transport === "stdio").length;
  // Read off the registry rather than restated here: a toolset renamed, split or
  // reclassified on the server should not leave a stale sentence below it.
  const readOnly = servers?.filter((s) => s.read_only).length ?? 0;
  const example = servers?.[0]?.command;

  return (
    <Panel
      title="MCP toolsets"
      icon={<IconTrace size={14} />}
      subtitle={servers ? `${servers.length} servers` : undefined}
      actions={
        <Button size="xs" iconOnly aria-label="Refresh"
                icon={<IconRefresh size={13} />} onClick={load} />
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-sm leading-relaxed text-muted">
          Partitioned by owning system rather than by convenience. Each server
          runs on its own{example ? <> — <Code>{example}</Code></> : null} — and{" "}
          {servers?.length
            ? `${readOnly} of the ${servers.length} are read-only`
            : "most of them are read-only"}
          , so an operator can hand those out and withhold the ones that write.
          <Code>commit_plan</Code> still refuses without a recorded approval:
          exposing a tool over MCP does not exempt it from the safeguards.
        </p>

        {/* --- transport ------------------------------------------------- */}
        <div className="flex flex-wrap items-center gap-2 rounded-sm border border-subtle bg-sunken px-2.5 py-2">
          <span className="text-sm text-muted">Evidence lookups run</span>
          <SegmentedControl
            ariaLabel="MCP transport"
            value={transport?.enabled ? "stdio" : "in-process"}
            onChange={(v) => flip(v === "stdio")}
            options={[
              { value: "in-process", label: "in-process",
                title: "Call the functions directly" },
              { value: "stdio", label: "over MCP",
                title: "Spawn each toolset and call it over stdio" },
            ]}
          />
          {busy && <span className="text-xs text-faint">switching…</span>}
          {transport?.degraded?.length ? (
            <Tooltip content={
              "These toolsets could not be spawned, so their calls fall back "
              + "in-process. A protocol demonstration is not worth losing a run over."
            }>
              <Badge tone="warn">
                {transport.degraded.length} degraded
              </Badge>
            </Tooltip>
          ) : null}
          {overWire > 0 && (
            <Badge tone="ok" dot>{overWire} over the wire</Badge>
          )}
        </div>

        {/* --- servers --------------------------------------------------- */}
        {servers === null ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : (
          <div className="grid gap-1.5 sm:grid-cols-2">
            {servers.map((server) => (
              <div
                key={server.id}
                className={cn(
                  "flex flex-col gap-1 rounded-sm border p-2.5",
                  server.read_only
                    ? "border-subtle bg-sunken"
                    : "border-danger-border bg-danger-soft/30"
                )}
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <Code>{server.id}</Code>
                  {server.read_only ? (
                    <Badge tone="ok">read-only</Badge>
                  ) : (
                    <Tooltip content={
                      `Mutating: ${server.mutating.join(", ")}. `
                      + "commit_plan still refuses without a recorded approval."
                    }>
                      <Badge tone="danger">
                        {server.mutating.length} mutating
                      </Badge>
                    </Tooltip>
                  )}
                  {counts[server.id] ? (
                    <Badge tone="neutral" mono>{counts[server.id]}</Badge>
                  ) : null}
                </div>
                <span className="text-sm font-medium">{server.title}</span>
                <span className="text-xs text-faint">
                  stands in for {server.owner}
                </span>
                <p className="text-xs leading-relaxed text-muted">
                  {server.why}
                </p>
                <div className="flex flex-wrap gap-1 pt-0.5">
                  {server.tools.map((tool) => (
                    <Badge
                      key={tool}
                      tone={server.mutating.includes(tool) ? "danger" : "neutral"}
                      mono
                    >
                      {tool}
                    </Badge>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* --- live calls ------------------------------------------------ */}
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-caps text-faint">
              Tool calls
            </h3>
            <span className="h-px flex-1 bg-subtle" />
            <span className="text-xs text-faint">newest first</span>
          </div>
          {calls.length === 0 ? (
            <p className="text-sm text-muted">
              No calls yet. Run the correction loop — the investigator's
              evidence lookups appear here as they cross the boundary.
            </p>
          ) : (
            <div className="max-h-56 overflow-y-auto rounded-sm border border-subtle">
              {calls.map((call) => (
                <div
                  key={call.seq}
                  className="flex items-center gap-2 border-b border-subtle px-2.5 py-1.5 text-sm last:border-b-0"
                >
                  <Badge
                    tone={call.transport === "stdio" ? "accent" : "neutral"}
                    mono
                  >
                    {call.transport}
                  </Badge>
                  <Code>{call.tool}</Code>
                  <span className="min-w-0 flex-1 truncate text-xs text-faint">
                    {call.toolset}
                  </span>
                  <span className="shrink-0 font-mono text-xs text-faint tabular-nums">
                    {call.ms < 1 ? "<1" : call.ms.toFixed(0)}ms
                  </span>
                  {!call.ok && <Badge tone="danger">failed</Badge>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}
