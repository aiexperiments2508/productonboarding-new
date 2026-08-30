import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import type { CapabilityDirectory } from "../api";
import { IconRefresh } from "../icons";
import { Badge, Button, Code, Dot, Panel, Skeleton, Tooltip, cn } from "../ui";

/* Everything this estate can do, in one place.
 *
 * Agent Cards were already published one per peer, at the address the A2A
 * specification puts them. That is correct and it is not discoverable: a peer
 * that already knows an identifier can fetch a card, and a peer that knows only
 * the host cannot find out what is here.
 *
 * Two things this panel is careful about.
 *
 * **It keeps peers and systems apart.** A peer is a capability this system
 * implements and another organisation's agent may call. A system is a
 * capability it merely knows how to reach. Showing them as one list would say
 * this estate can do things it can only ask somebody else to do.
 *
 * **It shows what a capability may not do.** The approval gate and publishing
 * are deliberately not peers - a human decision is not something to delegate,
 * and a peer that could publish is a peer that could publish. Leaving that to
 * be inferred from absence invites the reader to conclude they were forgotten.
 */

const POLL_MS = 5000;

export function CapabilityBoard() {
  const [directory, setDirectory] = useState<CapabilityDirectory | null>(null);

  const refresh = useCallback(async () => {
    try {
      setDirectory(await api.capabilities());
    } catch {
      /* A poll that misses is not worth a toast; the next one is 5s away. */
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  if (!directory) {
    return (
      <Panel title="Capabilities" subtitle="What this estate can do">
        <Skeleton className="h-40" />
      </Panel>
    );
  }

  const peers = directory.capabilities.filter((c) => c.kind === "peer");
  const systems = directory.capabilities.filter((c) => c.kind === "system");

  return (
    <Panel
      title="Capabilities"
      subtitle={
        `${directory.counts.peers} implemented here · ` +
        `${directory.counts.systems} reachable · ` +
        `${directory.counts.reachable} answering`
      }
      actions={
        <div className="flex items-center gap-1.5">
          <Tooltip content="The directory a stranger reads. Built from the same cards it lists, so it cannot drift from them.">
            <span><Code>/.well-known/agent-cards.json</Code></span>
          </Tooltip>
          <Button tone="ghost" size="sm" onClick={refresh} icon={<IconRefresh />}>
            Refresh
          </Button>
        </div>
      }
    >
      <section>
        <h4 className="text-2xs uppercase tracking-caps text-faint">
          implemented here · callable over A2A
        </h4>
        <ul className="sc-stagger mt-1.5 grid gap-1.5 md:grid-cols-2">
          {peers.map((peer, i) => (
            <li
              key={peer.id}
              style={{ ["--i" as string]: i }}
              className="rounded-md border border-subtle bg-raised p-2.5"
            >
              <div className="flex items-center gap-2">
                <Dot tone="ok" />
                <span className="min-w-0 truncate font-medium text-fg">
                  {peer.name}
                </span>
                <Badge tone="accent" mono>{peer.protocol}</Badge>
              </div>
              <p className="mt-1 text-xs text-muted">{peer.description}</p>
              {peer.skills?.map((skill) => (
                <p key={skill.id} className="mt-1">
                  <Code>{skill.id}</Code>
                </p>
              ))}
              {/* Stated, not inferred. */}
              {peer.may_not && peer.may_not.length > 0 && (
                <p className="mt-1.5 text-2xs text-faint">
                  may not: {peer.may_not.join(" · ")}
                </p>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section className="mt-4">
        <h4 className="text-2xs uppercase tracking-caps text-faint">
          reachable over MCP · not implemented here
        </h4>
        {systems.length === 0 ? (
          <p className="mt-1.5 text-xs text-muted">
            Nothing connected. Systems appear here as they join.
          </p>
        ) : (
          <ul className="sc-stagger mt-1.5 flex flex-col gap-1">
            {systems.map((system, i) => (
              <li
                key={system.id}
                style={{ ["--i" as string]: i }}
                className={cn(
                  "flex flex-wrap items-center gap-2 rounded-sm border px-2 py-1.5",
                  system.state === "connected"
                    ? "border-subtle bg-raised"
                    : "border-estate-degraded-border bg-estate-degraded-soft",
                )}
              >
                <Dot tone={system.state === "connected" ? "ok" : "warn"} />
                <span className="min-w-0 truncate text-sm text-fg">
                  {system.name}
                </span>
                <Badge tone="neutral" mono>{system.protocol}</Badge>
                <span className="text-2xs text-faint">
                  {(system.tools ?? []).length} tool(s) declared
                </span>
                {/* Discovery is not admission, and the board says which is
                    which - a system can declare ten tools and have none of
                    them callable from inside a run. */}
                <Tooltip content="Tools an operator has allowed a model to call. Connecting a system declares what it can do; it admits nothing.">
                  <span className="ml-auto shrink-0">
                    <Badge
                      tone={(system.admitted ?? []).length ? "warn" : "neutral"}
                    >
                      {(system.admitted ?? []).length} admitted
                    </Badge>
                  </span>
                </Tooltip>
              </li>
            ))}
          </ul>
        )}
      </section>
    </Panel>
  );
}
