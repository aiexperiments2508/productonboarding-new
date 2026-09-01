import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  TowerFeedDetail, TowerKpis, TowerPersonas, TowerRegister, TowerSpend,
} from "../../api";
import { api } from "../../api";
import {
  ErrorBoundary, LoadingBody, Panel, Select, Tab, TabList, TabPanel, Tabs,
  cn, useToast,
} from "../../ui";
import { LensNote, WindowNote } from "./common";
import { CostTab } from "./CostTab";
import { FeedsTab } from "./FeedsTab";
import { FlowTab } from "./FlowTab";
import { KpiTab } from "./KpiTab";

/* The Control Tower.
 *
 * One place that joins what the rest of the system already derives: where every
 * feed's rows got to, how well it is working over any date range, and what the
 * models cost reaching that. Nothing here decides anything - every verdict,
 * gate outcome and lane is read from the module that owns it.
 *
 * **The date range runs on the recorded flight's clock.** The tape's horizon
 * bounds the pickers, the same way `ProductFilters` bounds its pair, because a
 * window outside it silently returns nothing and looks like a bug in the
 * dashboard rather than a date outside the data.
 *
 * **The persona is a lens.** It changes which figures lead; it does not change
 * what the API will answer. That is stated on the screen and in the API's own
 * `enforced: false`, because a control that looks like access control and is
 * not is the kind of thing somebody builds a process on top of.
 */

const PERSONA_KEY = "sc.towerPersona";
const TAB_KEY = "sc.towerTab";

export function ControlTowerPanel({ horizon }: {
  /** The recorded flight's first and last day, so a picker cannot offer a
   *  date the tape has nothing on. */
  horizon?: { start: string; end: string } | null;
}) {
  const [tab, setTab] = useState(() => read(TAB_KEY, "flow"));
  const [personaId, setPersonaId] = useState(() => read(PERSONA_KEY, ""));
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [groupBy, setGroupBy] = useState("model");

  const [personas, setPersonas] = useState<TowerPersonas | null>(null);
  const [flow, setFlow] = useState<TowerRegister | null>(null);
  const [feeds, setFeeds] = useState<TowerRegister | null>(null);
  const [detail, setDetail] = useState<TowerFeedDetail | null>(null);
  const [kpis, setKpis] = useState<TowerKpis | null>(null);
  const [spend, setSpend] = useState<TowerSpend | null>(null);
  const [busy, setBusy] = useState(true);
  const toast = useToast();

  const window = useMemo(() => ({ start: start || undefined, end: end || undefined }),
                         [start, end]);

  useEffect(() => {
    api.towerPersonas()
      .then((p) => {
        setPersonas(p);
        setPersonaId((current) => current || p.default);
      })
      .catch(() => undefined);
  }, []);

  const persona = useMemo(
    () => personas?.personas.find((p) => p.id === personaId) ?? null,
    [personas, personaId]);

  /** Every tab from one window. Fetched together rather than per tab: the four
   *  are one question asked four ways, and a reader switching tabs to find the
   *  numbers had moved would have no way to tell which was current. */
  const load = useCallback(() => {
    setBusy(true);
    Promise.all([
      api.towerFlow(window),
      api.towerFeeds(window),
      api.towerKpis(window),
      api.towerSpend({ ...window, groupBy }),
    ])
      .then(([f, r, k, s]) => {
        setFlow(f); setFeeds(r); setKpis(k); setSpend(s);
      })
      .catch((e) => toast.error("Could not read the tower", String(e)))
      .finally(() => setBusy(false));
  }, [window, groupBy, toast]);

  useEffect(() => { load(); }, [load]);

  const openFeed = useCallback((feedId: string) => {
    api.towerFeed(feedId)
      .then((d) => { setDetail(d); setTab("feeds"); })
      .catch((e) => toast.error("Could not open that feed", String(e)));
  }, [toast]);

  const setBudget = useCallback(async (usd: number | null, actor: string,
                                       tokens: number | null) => {
    try {
      await api.setTowerBudget(usd, actor, tokens);
      const what = [usd !== null ? `$${usd}` : null,
                    tokens !== null ? `${tokens.toLocaleString()} tokens` : null]
        .filter(Boolean).join(" and ");
      toast.notify(what ? `Cap set to ${what}` : "Caps cleared",
                   "Recorded in the audit ledger against your name.");
      load();
    } catch (e) {
      toast.error("Could not move the cap", String(e));
    }
  }, [toast, load]);

  const onTab = (next: string) => {
    setTab(next);
    write(TAB_KEY, next);
    if (next !== "feeds") setDetail(null);
  };

  const onPersona = (next: string) => {
    setPersonaId(next);
    write(PERSONA_KEY, next);
    const chosen = personas?.personas.find((p) => p.id === next);
    if (chosen) onTab(chosen.default_tab);
  };

  return (
    <ErrorBoundary>
      <div className="flex min-h-0 flex-1 flex-col gap-3">
        <Panel
          title="Who is looking, and over what"
          subtitle={
            personas
              ? persona?.question ?? "Pick a persona and a date range."
              : "Loading the roles…"
          }
          actions={
            <div className="flex flex-wrap items-center gap-1.5">
              <Select
                value={personaId}
                onValueChange={onPersona}
                ariaLabel="Persona"
                options={(personas?.personas ?? []).map((p) => ({
                  value: p.id, label: p.label,
                }))}
              />
              <input
                type="date"
                value={start}
                min={horizon?.start}
                max={horizon?.end}
                onChange={(e) => setStart(e.target.value)}
                aria-label="Arrived on or after"
                className={dateInput}
              />
              <span className="text-2xs text-faint">to</span>
              <input
                type="date"
                value={end}
                min={horizon?.start}
                max={horizon?.end}
                onChange={(e) => setEnd(e.target.value)}
                aria-label="Arrived on or before"
                className={dateInput}
              />
              {(start || end) && (
                <button
                  type="button"
                  onClick={() => { setStart(""); setEnd(""); }}
                  className="rounded-sm border border-line px-1.5 py-1 text-2xs text-muted hover:text-fg"
                >
                  clear
                </button>
              )}
            </div>
          }
        >
          <div className="flex flex-col gap-2">
            {flow && (
              <WindowNote window={flow.window} bounded={flow.bounded} />
            )}
            {personas && <LensNote note={personas.note} />}
          </div>
        </Panel>

        {busy && !flow ? (
          <LoadingBody />
        ) : (
          <Tabs value={tab} onValueChange={onTab} fill>
            <TabList>
              <Tab value="flow">Flow</Tab>
              <Tab value="feeds">Feeds</Tab>
              <Tab value="kpis">KPIs</Tab>
              <Tab value="cost">Cost</Tab>
            </TabList>
            <TabPanel value="flow" scroll>
              <FlowTab data={flow} onOpenFeed={openFeed} />
            </TabPanel>
            <TabPanel value="feeds" scroll>
              <FeedsTab data={feeds} detail={detail} onOpenFeed={openFeed}
                        onCloseFeed={() => setDetail(null)} />
            </TabPanel>
            <TabPanel value="kpis" scroll>
              <KpiTab data={kpis} persona={persona} />
            </TabPanel>
            <TabPanel value="cost" scroll>
              <CostTab data={spend} groupBy={groupBy} onGroupBy={setGroupBy}
                       onBudget={setBudget} />
            </TabPanel>
          </Tabs>
        )}
      </div>
    </ErrorBoundary>
  );
}

const dateInput = cn(
  "rounded-sm border border-line bg-canvas px-1.5 py-1",
  "font-mono text-2xs text-fg focus:outline-none focus:ring-2 focus:ring-focus"
);

/** Persisted, like the appearance settings and the fabric rail. A dashboard
 *  that forgets which persona you are every reload is one nobody uses twice. */
function read(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private window, or storage disabled. The picker still works. */
  }
}
