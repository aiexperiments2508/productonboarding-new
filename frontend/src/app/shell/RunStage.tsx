import { useEffect, useRef } from "react";
import { IconCheck } from "../../icons";
import { Badge, Dot, cn } from "../../ui";
import { NODE_PHRASE, readable } from "./phrases";

/* The run, narrated at the size of the room.
 *
 * A correction loop takes the better part of a minute, and for that minute the
 * main region shows a Factory Floor that does not move. The only thing that did
 * move was the status strip's phrase - eleven pixels of the best writing in the
 * product, in a corner, on a projector. So the same phrase is promoted here
 * while the graph is running: what it is doing now, and the steps it has
 * already been through.
 *
 * Nothing is invented. The phrase is the strip's own vocabulary, the node name
 * is the string the trace is grepped by, and the step count is a count of nodes
 * entered - there is no percentage, because the graph's path depends on what
 * the document turns out to say and a bar pretending otherwise would be the one
 * dishonest thing on the screen.
 */

export function RunStage({ node, trail, revising }: {
  /** The graph node executing right now, streamed from the run. */
  node: string;
  /** Every node this run has entered, in order, the current one last. */
  trail: string[];
  revising?: boolean;
}) {
  const rail = useRef<HTMLOListElement>(null);
  const done = trail.slice(0, -1);

  // Keep the newest completed step in view; the rail fills left to right and
  // the interesting end is the right one.
  useEffect(() => {
    const el = rail.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [done.length]);

  return (
    <section
      className={cn(
        "mx-3 mt-3 flex shrink-0 animate-rise-in flex-col gap-2 overflow-hidden",
        "rounded-md border border-accent-border bg-raised p-3 shadow-e1"
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Dot tone="accent" pulse />
        <span className="text-2xs uppercase tracking-caps text-faint">
          {revising ? "revising the resolution" : "working the correction"}
        </span>
        <span className="ml-auto flex items-center gap-2">
          <span className="font-mono text-xs text-faint">{node}</span>
          <Badge tone="accent" mono>
            step {trail.length}
          </Badge>
        </span>
      </div>

      {/* Sized off the type tokens rather than a fixed step: the largest token
          is 28px, and this has to be legible from the back of a room. */}
      {/* A live region, but not role="status": the toast stack already owns one
          and two status regions announce over each other. */}
      <p
        aria-live="polite"
        className="min-w-0 font-semibold leading-tight tracking-tight text-fg"
        style={{
          fontSize:
            "clamp(var(--sc-text-xl), 3.4vw, calc(var(--sc-text-2xl) * 1.5))",
        }}
      >
        {readable(node, NODE_PHRASE)}
      </p>

      {done.length > 0 && (
        <ol
          ref={rail}
          aria-label="Steps already taken"
          className="flex min-w-0 items-center gap-1.5 overflow-x-auto pb-0.5"
        >
          {done.map((step, i) => (
            <li
              key={`${step}-${i}`}
              className={cn(
                "flex shrink-0 items-center gap-1 rounded-full border",
                "border-subtle bg-sunken py-px pl-1.5 pr-2 text-xs text-muted"
              )}
            >
              <IconCheck size={11} className="shrink-0 text-ok-text" />
              {readable(step, NODE_PHRASE)}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
