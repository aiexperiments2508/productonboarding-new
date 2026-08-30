import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, subscribe } from "../api";
import type {
  CatalogState, Citation, Health, ReplayState, RunSnapshot, SCEvent,
} from "../api";
import { Approvals } from "../components/Approvals";
import { ControlTower } from "../components/ControlTower";
import { Investigation } from "../components/Investigation";
import { Scenarios } from "../components/Scenarios";
import { SystemControl } from "../components/SystemControl";
import { ErrorBoundary, ToastProvider, TooltipProvider, useToast } from "../ui";
import { CommandBar } from "./shell/CommandBar";
import { CommandPalette } from "./shell/CommandPalette";
import { DocPeek } from "./shell/DocPeek";
import { RunStage } from "./shell/RunStage";
import { Sidebar } from "./shell/Sidebar";
import { StatusStrip } from "./shell/StatusStrip";
import { sectionById } from "./nav";
import type { SectionId } from "./nav";

/* Application shell.
 *
 * Everything that used to be in main.tsx, plus the chrome. The data wiring is
 * carried over unchanged - the SSE subscription, the checkpointed-thread
 * restore, and the settled-promise refresh were all correct and are load
 * bearing for the demo.
 */

const NAV_KEY = "sc.navCollapsed";

export function App() {
  return (
    <TooltipProvider>
      <ToastProvider>
        <Shell />
      </ToastProvider>
    </TooltipProvider>
  );
}

function Shell() {
  const toast = useToast();

  const [section, setSection] = useState<SectionId>("tower");
  const [navCollapsed, setNavCollapsed] = useState(
    () => localStorage.getItem(NAV_KEY) === "1"
  );
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [peek, setPeek] = useState<Citation | null>(null);

  const [health, setHealth] = useState<Health | null>(null);
  // Products, variants, channels, listings, and whatever corrections are in
  // force at the replay's current instant. Held here rather than per view so
  // three sections are not each fetching the same catalog.
  const [catalog, setCatalog] = useState<CatalogState | null>(null);
  const [events, setEvents] = useState<SCEvent[]>([]);
  const [replay, setReplay] = useState<ReplayState | null>(null);
  const [run, setRun] = useState<RunSnapshot | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [replanning, setReplanning] = useState(false);
  // The node the graph is on right now, streamed from the run itself, and the
  // ordered trail of everything it has been through - the run stage narrates
  // both, at a size a room can read.
  const [liveNode, setLiveNode] = useState<string | null>(null);
  const [nodeTrail, setNodeTrail] = useState<string[]>([]);
  const threadRef = useRef<string | null>(null);

  /* One node entered. Consecutive repeats are collapsed: validate_one runs once
   * per candidate and streams a node event each time, and three identical
   * phrases in the trail read as a rendering fault rather than as three
   * validations. */
  const enterNode = useCallback((node: string) => {
    setLiveNode(node);
    setNodeTrail((prev) =>
      prev[prev.length - 1] === node ? prev : [...prev, node]
    );
  }, []);

  const toggleNav = useCallback(() => {
    setNavCollapsed((c) => {
      localStorage.setItem(NAV_KEY, c ? "0" : "1");
      return !c;
    });
  }, []);

  const refreshCore = useCallback(async () => {
    const [h, c, e] = await Promise.allSettled([
      api.health(), api.network(), api.events(60),
    ]);
    if (h.status === "fulfilled") { setHealth(h.value); setReplay(h.value.replay); }
    if (c.status === "fulfilled") setCatalog(c.value);
    if (e.status === "fulfilled") setEvents(e.value.events);
  }, []);

  useEffect(() => {
    refreshCore().catch((e) => toast.error("Could not load the catalog", String(e)));
  }, [refreshCore, toast]);

  // The event stream is the live wire: the replay clock pushes supplier
  // documents and channel responses as it releases them, so the feed and the
  // map update without polling.
  useEffect(() => {
    const stop = subscribe((m) => {
      if (m.kind === "events") {
        const incoming = (m.events as SCEvent[]) ?? [];
        setEvents((prev) => [...incoming, ...prev].slice(0, 200));
        setReplay(m.replay as ReplayState);
        // Facts change as documents land, so which corrections are in force -
        // and which listings they hold back - moves with the tape.
        api.network().then(setCatalog).catch(() => undefined);
      } else if (m.kind === "hello") {
        setReplay(m.replay as ReplayState);
      }
    });
    return stop;
  }, []);

  // Restore an in-flight run across a reload - the graph is checkpointed
  // server-side, so a refreshed browser must not lose the pending approval.
  useEffect(() => {
    const saved = localStorage.getItem("thread_id");
    if (!saved) return;
    threadRef.current = saved;
    api.run(saved).then(setRun).catch(() => localStorage.removeItem("thread_id"));
  }, []);

  // Corrections waiting on a reviewer drive the rail badge. Re-read whenever
  // the run's status moves, which is the only thing that can change the count.
  useEffect(() => {
    api.pending()
      .then((r) => setPendingCount(r.pending.length))
      .catch(() => setPendingCount(run?.awaiting_approval ? 1 : 0));
  }, [run?.status, run?.awaiting_approval]);

  // Cmd/Ctrl-K from anywhere. Guarded so it does not fire while the reviewer is
  // mid-word in the approval comment box.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  /* Work one correction case.
   *
   * `caseId` names the product to scope to. Without it the graph picks the
   * worst case open rather than sweeping every correction in force into one
   * recommendation - a reviewer approves a decision about a product. */
  const startRun = useCallback(async (caseId?: string) => {
    setBusy(true);
    setNodeTrail([]);
    enterNode("starting");
    try {
      const incident = `INC-${Date.now().toString(36).toUpperCase()}`;
      const snapshot = await api.streamRun(
        { incident_id: incident, thread_id: incident, case_id: caseId },
        (e) => {
          if (e.kind === "node") enterNode(e.node);
          // The trace grows as the graph runs, so keep the snapshot fresh
          // rather than waiting for the final frame - the review screen is
          // watchable while the run is still going.
          else if (e.kind === "run_finished") setLiveNode(null);
        },
      );
      threadRef.current = incident;
      localStorage.setItem("thread_id", incident);
      setRun(snapshot);
      // Blast Radius, not the review screen. request_approval is the normal
      // terminal state, so routing on it walked straight past the two sections
      // the run exists to produce - what the correction reaches, and the
      // readings of it. The pending decision keeps its own affordances: the
      // rail badge, and the way onward on the toast below.
      setSection("investigation");
      toast.push({
        tone: snapshot.awaiting_approval ? "warn" : "ok",
        title: snapshot.awaiting_approval
          ? "Waiting on review before anything republishes"
          : "Correction loop finished",
        // Which product was worked, not just which incident id it was filed
        // under - the case is what the reviewer is being called to.
        detail: snapshot.values.case?.title ?? incident,
        action: snapshot.awaiting_approval
          ? { label: "Go to Review & Audit", onClick: () => setSection("approvals") }
          : undefined,
      });
    } catch (e) {
      toast.error("The correction run failed", String(e));
    } finally {
      setBusy(false);
      setLiveNode(null);
    }
  }, [enterNode, toast]);

  /* Revise the resolution against evidence that arrived after it was written -
   * the clarification that names the variant, or a marketplace rejection.
   *
   * Deliberately distinct from startRun: this keeps the thread, so the
   * correction, its audit trail and its checkpoint history all continue. A
   * second startRun would mint a new correction and lose the comparison, which
   * is the "full restart" the brief rules out. */
  const doReplan = useCallback(async (reason: string) => {
    const thread = threadRef.current;
    if (!thread) {
      toast.error("Nothing to revise", "Work a correction first.");
      return;
    }
    setReplanning(true);
    setNodeTrail([]);
    enterNode("starting");
    try {
      const next = await api.streamReplan(thread, reason, (e) => {
        if (e.kind === "node") enterNode(e.node);
        else if (e.kind === "run_finished") setLiveNode(null);
      });
      setRun(next);
      setSection("approvals");
      const diff = next.values.plan_diff;
      toast.push({
        tone: diff?.held ? "ok" : "warn",
        title: diff?.headline ?? `Revision ${next.values.revision ?? ""} ready`,
        detail: diff?.held
          ? undefined
          : diff?.previous?.name
          ? `was: ${diff.previous.name}`
          : undefined,
      });
    } catch (e) {
      toast.error("Could not revise the resolution", String(e));
    } finally {
      setReplanning(false);
      setLiveNode(null);
    }
  }, [enterNode, toast]);

  const doReplay = useCallback(
    async (body: { action: string; steps?: number; speed?: number; to_seq?: number }) => {
      setBusy(true);
      try {
        const r = await api.replay(body);
        setReplay(r.replay);
        await refreshCore();
      } catch (e) {
        toast.error("Replay control failed", String(e));
      } finally {
        setBusy(false);
      }
    },
    [refreshCore, toast]
  );

  const refreshRun = useCallback(async () => {
    if (!threadRef.current) return;
    try {
      setRun(await api.run(threadRef.current));
    } catch (e) {
      toast.error("Could not refresh the run", String(e));
    }
  }, [toast]);

  const paletteActions = useMemo(
    () => ({
      navigate: setSection,
      startRun,
      replan: doReplan,
      replay: doReplay,
      openCitation: setPeek,
    }),
    [startRun, doReplan, doReplay]
  );

  return (
    <div className="flex h-full w-full overflow-hidden bg-canvas">
      <Sidebar
        active={section}
        onSelect={setSection}
        collapsed={navCollapsed}
        onToggleCollapsed={toggleNav}
        pendingCount={pendingCount}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <CommandBar
          section={section}
          health={health}
          liveNode={liveNode}
          onOpenPalette={() => setPaletteOpen(true)}
          onOpenSystem={() => setSection("system")}
        />

        {/* Above <main> rather than inside it: the stage is what the room
            watches for the minute the loop takes, so it must not scroll away
            with the section content or remount when the presenter navigates. */}
        {liveNode && (
          <RunStage node={liveNode} trail={nodeTrail} revising={replanning} />
        )}

        {/* Keyed so switching section replays the entrance rather than
            cross-fading two unrelated layouts into each other. */}
        <main
          key={section}
          className="min-h-0 flex-1 animate-rise-in overflow-y-auto p-4"
        >
          {/* Keyed with the section, so navigating away from a view that threw
              gives it a clean mount rather than a stuck error. The shell -
              rail, header, transport - stays up either way, and the run behind
              it is checkpointed server-side. */}
          <ErrorBoundary key={section} label={sectionById(section).label}>
          {section === "tower" && (
            <ControlTower
              catalog={catalog} events={events} run={run}
              onStartRun={startRun} onReplay={doReplay} busy={busy}
            />
          )}
          {section === "investigation" && (
            <Investigation
              run={run} catalog={catalog} onOpenCitation={setPeek}
            />
          )}
          {section === "scenarios" && (
            <Scenarios run={run} catalog={catalog} onRefresh={refreshRun} />
          )}
          {section === "approvals" && (
            <Approvals
              run={run} onDecided={setRun}
              onReplan={doReplan} replanning={replanning}
              catalog={catalog} onOpenCitation={setPeek}
            />
          )}
          {section === "system" && (
            <SystemControl
              health={health} replay={replay} onReplay={doReplay}
              busy={busy} onRefresh={refreshCore}
            />
          )}
          </ErrorBoundary>
        </main>

        <StatusStrip
          replay={replay} run={run} onReplay={doReplay} busy={busy}
          liveNode={liveNode}
        />
      </div>

      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        actions={paletteActions}
      />
      <DocPeek citation={peek} onClose={() => setPeek(null)} />
    </div>
  );
}
