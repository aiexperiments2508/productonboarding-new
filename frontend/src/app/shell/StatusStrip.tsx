import { fmt } from "../../api";
import type { ReplayState, RunSnapshot } from "../../api";
import {
  IconClock, IconJump, IconPause, IconPlay, IconReset, IconStep,
} from "../../icons";
import { Badge, Button, Dot, ProgressBar, Spinner, Tooltip, cn } from "../../ui";
import { NODE_PHRASE, STATUS_PHRASE, readable } from "./phrases";

/* Status strip.
 *
 * The replay transport used to live only in System Control, which meant
 * narrating the tape - "the portal feed, then the corrected spec sheet, then
 * the marketplace rejection" - required stepping it on one tab and watching
 * the catalog on another. Nobody can do that and talk at the same time.
 *
 * So the transport is persistent, at the bottom, next to the simulated clock
 * it drives. System Control keeps the full panel; this is the subset needed
 * while looking at something else.
 *
 * The node and status vocabularies moved to ./phrases, because the run stage
 * narrates the same nodes at a size a room can read.
 */

/** Only two outcomes are settled-good; two are settled-bad. Everything else is
 *  the loop still working, which is accent, not a verdict. */
function statusTone(status: string): "ok" | "warn" | "danger" | "accent" {
  if (status === "PUBLISHED") return "ok";
  if (status === "PUBLISH_REFUSED" || status === "CONFLICT_UNRESOLVED") return "danger";
  if (status === "NO_OPTIONS" || status === "PARKED") return "warn";
  return "accent";
}

export function StatusStrip({
  replay, run, onReplay, busy, liveNode,
}: {
  replay: ReplayState | null;
  run: RunSnapshot | null;
  onReplay: (body: { action: string; steps?: number }) => void;
  busy: boolean;
  /** The graph node executing right now, streamed from the run. */
  liveNode?: string | null;
}) {
  const progress =
    replay && replay.total_events
      ? (replay.cursor_seq / replay.total_events) * 100
      : 0;
  const running = !!replay?.running;
  const status = run?.status ?? "";

  return (
    <footer
      className={cn(
        "flex h-[var(--shell-strip-h)] shrink-0 items-center gap-3",
        "border-t border-subtle bg-raised px-3 text-xs"
      )}
    >
      {/* --- transport ----------------------------------------------------- */}
      <div className="flex shrink-0 items-center gap-0.5">
        <Tooltip content={running ? "Pause the replay clock" : "Start the replay clock"}>
          <Button
            tone="ghost"
            size="xs"
            iconOnly
            disabled={busy}
            aria-label={running ? "Pause replay" : "Start replay"}
            onClick={() => onReplay({ action: running ? "PAUSE" : "START" })}
            icon={running ? <IconPause size={13} /> : <IconPlay size={13} />}
          />
        </Tooltip>
        <Tooltip
          content={"Release one event.\nThe way to narrate a supplier document as it lands."}
        >
          <Button
            tone="ghost"
            size="xs"
            iconOnly
            disabled={busy}
            aria-label="Release one event"
            onClick={() => onReplay({ action: "STEP", steps: 1 })}
            icon={<IconStep size={13} />}
          />
        </Tooltip>
        <Tooltip content="Release every event up to the corrected spec sheet">
          <Button
            tone="ghost"
            size="xs"
            iconOnly
            disabled={busy}
            aria-label="Jump to the correction"
            onClick={() => onReplay({ action: "JUMP" })}
            icon={<IconJump size={13} />}
          />
        </Tooltip>
        <Tooltip content="Rewind to day one and clear every released event">
          <Button
            tone="ghost"
            size="xs"
            iconOnly
            disabled={busy}
            aria-label="Rewind the tape"
            onClick={() => onReplay({ action: "RESET" })}
            icon={<IconReset size={13} />}
          />
        </Tooltip>
      </div>

      {/* --- clock --------------------------------------------------------- */}
      <Tooltip content="Simulated clock — where the tape has reached, not wall time">
        <span className="flex shrink-0 items-center gap-1.5 font-mono text-muted tabular-nums">
          <IconClock size={12} className="text-faint" />
          {replay?.sim_clock ? fmt.stamp(replay.sim_clock) : "not started"}
        </span>
      </Tooltip>

      {/* --- tape progress ------------------------------------------------- */}
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <ProgressBar
          value={progress}
          tone="accent"
          ariaLabel="Events released"
          className="min-w-16 max-w-64 flex-1"
        />
        <Tooltip content="Events released, out of the whole tape">
          <span className="hidden shrink-0 font-mono text-faint tabular-nums sm:inline">
            {replay?.cursor_seq ?? 0}/{replay?.total_events ?? 0}
          </span>
        </Tooltip>
        {running && (
          <Badge tone="accent" className="shrink-0">
            {replay?.speed}x
          </Badge>
        )}
      </div>

      {/* --- run state ----------------------------------------------------- */}
      <div className="flex shrink-0 items-center gap-2">
        {liveNode ? (
          // While a run streams, the step it is on is more useful than its last
          // settled status - it is the difference between "working" and
          // "working out which variant the correction names".
          <Tooltip content={`Graph node: ${liveNode}`}>
            <span className="flex items-center gap-1.5 text-accent-text">
              <Spinner size={12} />
              <span className="truncate">{readable(liveNode, NODE_PHRASE)}</span>
            </span>
          </Tooltip>
        ) : run?.awaiting_approval ? (
          <Badge tone="warn" dot>
            waiting on review
          </Badge>
        ) : status ? (
          <Tooltip content={`Run status: ${status}`}>
            <span className="flex items-center gap-1.5 text-muted">
              <Dot tone={statusTone(status)} />
              <span className="truncate">{readable(status, STATUS_PHRASE)}</span>
            </span>
          </Tooltip>
        ) : (
          <span className="text-faint">no correction being worked</span>
        )}
      </div>
    </footer>
  );
}
