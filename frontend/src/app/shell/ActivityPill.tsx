import { IconRobot, IconTrace } from "../../icons";
import { Badge, Dot, Menu, MenuItem, MenuLabel, MenuSeparator, cn } from "../../ui";
import { callSubtitle, callTitle, isRecent, useActivity } from "./useActivity";
import type { ActivityCall, ActivityRoster } from "./useActivity";

/* The agent monitor.
 *
 * The claim this system makes about itself is that agents propose and
 * deterministic code decides, and that the pieces doing the proposing are
 * separately owned - a lineage analyst, a resolution planner, a validator and
 * a copywriter, over toolsets belonging to the catalog, the channel registry,
 * the content store and the rest. Both rosters are visible in full on the
 * System Control screen, which is exactly where nobody is looking while a
 * correction is being worked.
 *
 * So the header carries a compressed version: what is executing right now,
 * what ran last, and how much of the traffic actually crossed a boundary
 * rather than being called in-process. The count of crossings is the part
 * worth having in permanent view - it is the difference between a protocol
 * that is configured and a protocol that is being used, and it is the first
 * thing a sceptical reviewer asks about.
 *
 * Open it for the feed. Nothing here is a control: the transport switches stay
 * on System Control, because flipping a transport is a change to how the
 * system runs and does not belong on a status indicator.
 */

export function ActivityPill({ liveNode, onOpenSystem }: {
  /** The graph node executing right now, streamed from the run itself.
   *  Null between runs. */
  liveNode: string | null;
  onOpenSystem: () => void;
}) {
  const live = liveNode != null;
  const activity = useActivity(live);
  const { latest, roster } = activity;

  const busy = live || isRecent(latest);
  const label = liveNode ?? latest?.name ?? "idle";
  const total = activity.calls.length;

  return (
    <Menu
      align="end"
      trigger={
        <button
          aria-label={
            live
              ? `Agent monitor - running ${liveNode}`
              : `Agent monitor - ${total} recent calls`
          }
          className={cn(
            "hidden h-[var(--control-h-sm)] items-center gap-1.5 rounded-full",
            "border px-2 text-xs transition-colors duration-[var(--dur-fast)]",
            "outline-none focus-visible:ring-2 focus-visible:ring-accent-border",
            "md:inline-flex",
            busy
              ? "border-accent-border bg-accent-soft text-accent-text"
              : "border-subtle bg-sunken text-muted hover:border-strong"
          )}
        >
          <IconRobot size={13} className="shrink-0" />
          {/* Only pulses while something is actually running. A pulse that
              never stops is decoration, and stops being read within a
              minute. */}
          <Dot
            tone={activity.failures > 0 ? "warn" : busy ? "accent" : "neutral"}
            pulse={busy}
            className="[&>span]:size-1.5"
          />
          <span
            className={cn(
              "max-w-[13ch] truncate font-mono",
              !busy && "text-faint"
            )}
          >
            {label}
          </span>
          {total > 0 && (
            <span className="tabular-nums text-faint">{total}</span>
          )}
        </button>
      }
    >
      <div className="w-[330px]">
        <MenuLabel>Peers and toolsets</MenuLabel>

        {/* The roster, as the server declares it - not a count of who happens
            to have been called. */}
        <p className="px-2 pb-1 text-xs text-faint">
          {roster.peers} peer agents over {roster.toolsets} toolsets
          {roster.degraded.length > 0 &&
            `, ${roster.degraded.length} running in-process after a failed spawn`}
        </p>

        <div className="flex flex-wrap gap-1.5 px-2 pb-1.5">
          <Badge tone="neutral" mono>{activity.agentCalls} delegated</Badge>
          <Badge tone="neutral" mono>{activity.toolCalls} looked up</Badge>
          <Badge tone={activity.crossings > 0 ? "accent" : "neutral"} mono>
            {activity.crossings} crossed
          </Badge>
          {activity.failures > 0 && (
            <Badge tone="danger" mono>{activity.failures} failed</Badge>
          )}
        </div>

        {live && (
          <div className="mx-2 mb-1.5 flex items-center gap-2 rounded-sm border border-accent-border bg-accent-soft px-2 py-1.5">
            <Dot tone="accent" pulse className="[&>span]:size-1.5" />
            <span className="font-mono text-xs text-accent-text">
              {liveNode}
            </span>
            <span className="ml-auto text-xs text-muted">executing</span>
          </div>
        )}

        <MenuSeparator />

        {activity.calls.length === 0 ? (
          <p className="px-2 py-3 text-sm text-faint">
            Nothing has asked a peer or a toolset for anything yet. Work a
            correction from the Factory Floor and this fills up.
          </p>
        ) : (
          <ul className="max-h-[280px] overflow-y-auto px-1 py-1">
            {activity.calls.map((call) => (
              <CallRow key={call.key} call={call} roster={roster} />
            ))}
          </ul>
        )}

        <MenuSeparator />
        <MenuItem icon={<IconTrace size={14} />} onSelect={onOpenSystem}>
          Open the full consoles
        </MenuItem>
      </div>
    </Menu>
  );
}

/** One call. The transport is the column that earns its place: "in-process"
 *  and "stdio" are the same call taking different paths, and which one it took
 *  is a fact about the run rather than about the configuration. */
function CallRow({ call, roster }: { call: ActivityCall; roster: ActivityRoster }) {
  const crossed = call.transport !== "in-process";
  return (
    <li className="flex items-center gap-2 rounded-sm px-1.5 py-1 text-sm">
      <span
        className={cn(
          "shrink-0 text-2xs uppercase tracking-caps",
          call.kind === "agent" ? "text-accent-text" : "text-faint"
        )}
      >
        {call.kind === "agent" ? "a2a" : "mcp"}
      </span>

      <span className="min-w-0 flex-1">
        <span
          className={cn(
            "block truncate font-mono text-xs",
            call.ok ? "text-fg" : "text-danger-text line-through decoration-1"
          )}
        >
          {callTitle(call, roster)}
        </span>
        <span className="block truncate text-2xs text-faint">
          {callSubtitle(call, roster)}
        </span>
      </span>

      <Badge tone={crossed ? "accent" : "neutral"} mono>
        {call.transport}
      </Badge>
      <span className="w-12 shrink-0 text-right font-mono text-2xs tabular-nums text-faint">
        {call.ms < 1 ? "<1ms" : `${Math.round(call.ms)}ms`}
      </span>
    </li>
  );
}
