import { useEffect, useState } from "react";
import { api } from "../api";
import { IconClock } from "../icons";
import { Badge, Code, Panel, Skeleton, Tooltip, cn } from "../ui";

/* Checkpoint history.
 *
 * The durability claim in one panel. Every superstep the graph completed wrote
 * a checkpoint, and this is that list read back out of the saver - which is
 * what makes "kill the process mid-run and resume" inspectable rather than
 * asserted.
 *
 * It is also where a revision proves it was a revision. A re-plan re-enters
 * the same thread, so its checkpoints continue this list instead of starting a
 * second one; a full restart would show up here as an empty history against a
 * new thread id.
 */

interface Checkpoint {
  checkpoint_id: string;
  next: string[];
  status?: string;
  created_at?: string;
}

export function RunHistory({ threadId, status }: {
  threadId?: string;
  /** Re-read when the run moves. The history only grows as nodes complete. */
  status?: string;
}) {
  const [checkpoints, setCheckpoints] = useState<Checkpoint[] | null>(null);

  useEffect(() => {
    if (!threadId) {
      setCheckpoints([]);
      return;
    }
    let live = true;
    api.history(threadId, 60)
      .then((r) => { if (live) setCheckpoints(r.checkpoints); })
      .catch(() => { if (live) setCheckpoints([]); });
    return () => { live = false; };
  }, [threadId, status]);

  if (!threadId) return null;

  return (
    <Panel
      title="Checkpoint history"
      icon={<IconClock size={14} />}
      subtitle={checkpoints ? `${checkpoints.length} supersteps` : undefined}
      flush
      actions={
        <Tooltip content="Each entry is a durable checkpoint. The run can be killed at any of them and resumed from that point.">
          <span className="text-sm text-faint">durable</span>
        </Tooltip>
      }
    >
      {checkpoints === null ? (
        <div className="flex flex-col gap-2 p-3">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))}
        </div>
      ) : checkpoints.length === 0 ? (
        <p className="p-3 text-sm text-muted">
          No checkpoints yet. They appear as the graph completes each step.
        </p>
      ) : (
        <div className="max-h-[280px] overflow-y-auto">
          {checkpoints.map((cp, i) => {
            // The history comes back newest-first, so the last row is the
            // start of the run and the first is where it stands now.
            const isCurrent = i === 0;
            const nextNode = cp.next?.[0];
            return (
              <div
                key={cp.checkpoint_id || i}
                className={cn(
                  "flex items-baseline gap-2 border-b border-subtle px-3 py-1.5",
                  "text-sm last:border-b-0",
                  isCurrent && "bg-accent-soft/50"
                )}
              >
                <span className="w-6 shrink-0 font-mono text-xs text-faint tabular-nums">
                  {checkpoints.length - i}
                </span>
                {cp.status ? (
                  <Badge tone={isCurrent ? "accent" : "neutral"} mono>
                    {cp.status}
                  </Badge>
                ) : (
                  <Badge tone="neutral">—</Badge>
                )}
                <span className="min-w-0 flex-1 truncate text-muted">
                  {nextNode ? (
                    <>next <Code>{nextNode}</Code></>
                  ) : (
                    <span className="text-faint">complete</span>
                  )}
                </span>
                {cp.created_at && (
                  <span className="shrink-0 font-mono text-xs text-faint tabular-nums">
                    {cp.created_at.slice(11, 19)}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
