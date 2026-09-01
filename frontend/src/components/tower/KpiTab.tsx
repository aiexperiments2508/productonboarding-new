import type { TowerKpis, TowerPersona } from "../../api";
import { Panel, Tooltip, cn } from "../../ui";
import { Caveat, Tile, hours, pct, tokens, usd } from "./common";

/* The numbers, and what each one is allowed to claim.
 *
 * Two rules run through this file and both are the reason it is longer than a
 * grid of `<Stat>`:
 *
 * A **dash is not a zero.** Every rate arrives as `null` when its denominator
 * was empty, and it renders as "—". "0% of feeds passed compliance" for a week
 * nothing arrived in is a figure somebody screenshots.
 *
 * A **duration says how many things it measured.** "Four hours" over two feeds
 * and over two hundred are different claims, and the sample size sits under the
 * figure rather than in a legend.
 */

/** Every KPI this screen can draw, with the words for it and what it may
 *  claim. Keyed by the field `sc/tower/kpis.py` returns, so a persona's tile
 *  list and this table cannot drift - `tests/test_tower.py` asserts every tile
 *  a persona asks for is a key the summary actually returns. */
const DEFS: Record<string, {
  label: string;
  note: string;
  render: (k: TowerKpis) => string;
  sub?: (k: TowerKpis) => string | undefined;
  tone?: (k: TowerKpis) => "good" | "bad" | undefined;
}> = {
  feeds_received: {
    label: "Feeds received",
    note: "Submissions that arrived in this window, on the recorded flight's own clock.",
    render: (k) => String(k.feeds_received),
    sub: (k) => (k.truncated ? `of ${k.feeds_matched} — a sample` : "archives"),
    tone: (k) => (k.truncated ? "bad" : undefined),
  },
  rows_received: {
    label: "Rows received",
    note: "Lines across every feed in the window.",
    render: (k) => String(k.rows_received),
    sub: () => "lines sent",
  },
  rows_assessed: {
    label: "Rows assessed",
    note: "Rows placed in a state. Only a supplier data pack has a population to place; a document or a single correction does not.",
    render: (k) => String(k.rows_assessed),
    sub: (k) => `of ${k.rows_received} sent`,
  },
  compliance_pass_rate: {
    label: "Compliance pass",
    note: "Rows the gate did not stop and that carry no blocking finding. A missing value is not a compliance failure - it is a gap, and it is counted separately.",
    render: (k) => pct(k.compliance_pass_rate),
    sub: () => "cleared the gate",
  },
  all_clear_rate: {
    label: "All clear",
    note: "Rows fit to launch, dispatched, or on sale. A row waiting on a person is not among them - it has not cleared, it has stopped somewhere politer.",
    render: (k) => pct(k.all_clear_rate),
    sub: () => "fit to sell or beyond",
  },
  blocked_rate: {
    label: "Blocked",
    note: "Stopped by a regulation, by this organisation's own policy, or by a blocking finding, and back with the supplier.",
    render: (k) => pct(k.blocked_rate),
    sub: () => "back with the supplier",
    tone: (k) => (k.blocked_rate && k.blocked_rate > 0.1 ? "bad" : undefined),
  },
  awaiting_decision_rate: {
    label: "Awaiting a person",
    note: "Rows with a proposal the system would not write unattended.",
    render: (k) => pct(k.awaiting_decision_rate),
    sub: () => "queued for review",
  },
  residual_error_rate: {
    label: "Residual errors",
    note: "Rows that are on sale and still carry an open finding. Not a second blocked count - this is what the process let through rather than what it stopped.",
    render: (k) => pct(k.residual_error_rate),
    sub: (k) => `${k.residual_errors} live rows`,
    tone: (k) => (k.residual_errors > 0 ? "bad" : undefined),
  },
  residual_errors: {
    label: "Live with findings",
    note: "Rows on sale that still carry an open finding.",
    render: (k) => String(k.residual_errors),
    sub: () => "on sale, not clean",
    tone: (k) => (k.residual_errors > 0 ? "bad" : undefined),
  },
  proposals: {
    label: "Values proposed",
    note: "Gaps the system found a candidate value for.",
    render: (k) => String(k.proposals),
    sub: () => "gaps with a candidate",
  },
  autonomous_fills: {
    label: "Recorded unattended",
    note: "Written without asking anybody: at or above the confidence threshold, with at least two supporting sources, and never safety-class.",
    render: (k) => String(k.autonomous_fills),
    sub: () => "written with a citation",
  },
  autonomous_fill_rate: {
    label: "AI closed",
    note: "Proportion of proposals the system settled itself. The rest went to a person, which is the design rather than a shortfall.",
    render: (k) => pct(k.autonomous_fill_rate),
    sub: (k) => `${k.autonomous_fills} of ${k.proposals}`,
  },
  decisions_by_person: {
    label: "Decided by a person",
    note: "Approved or rectified by somebody named. These land DECIDED, not INFERRED - the audit trail can tell them apart.",
    render: (k) => String(k.decisions_by_person),
    sub: () => "approved or rectified",
  },
  human_decision_rate: {
    label: "Answered by a person",
    note: "Proportion of proposals a named person settled.",
    render: (k) => pct(k.human_decision_rate),
    sub: (k) => `${k.decisions_by_person} of ${k.proposals}`,
  },
  awaiting_decision: {
    label: "Still queued",
    note: "Proposals routed to a person and not yet answered.",
    render: (k) => String(k.awaiting_decision),
    sub: () => "waiting on somebody",
    tone: (k) => (k.awaiting_decision > 0 ? "bad" : undefined),
  },
  feed_success_rate: {
    label: "Feeds clean on arrival",
    note: "Feeds that carried no stamped defect through the estate. A defect does not necessarily refuse the feed, which is what makes this a reliability figure rather than a second blocked count.",
    render: (k) => pct(k.feed_success_rate),
    sub: (k) => `${k.feeds_with_defects} carried defects`,
  },
  feeds_with_defects: {
    label: "Feeds with defects",
    note: "Feeds whose payload the estate stamped on the way in.",
    render: (k) => String(k.feeds_with_defects),
    sub: () => "malformed on arrival",
    tone: (k) => (k.feeds_with_defects > 0 ? "bad" : undefined),
  },
  median_hours_to_downstream: {
    label: "To downstream",
    note: "Median time from a feed landing to a commit against its products. Both ends are wall clock - the window filters the simulated one, and subtracting across the two would mean nothing.",
    render: (k) => hours(k.median_hours_to_downstream),
    sub: (k) => `median of ${k.measured_downstream} · real clock`,
  },
  median_hours_to_first_fill: {
    label: "To first fill",
    note: "Median time from a feed landing to the first enrichment run against it. Real clock at both ends.",
    render: (k) => hours(k.median_hours_to_first_fill),
    sub: (k) => `median of ${k.measured_first_fill} · real clock`,
  },
  tokens: {
    label: "Tokens",
    note: "Tokens actually sent, excluding anything the response cache answered.",
    render: (k) => tokens(k.tokens),
    sub: (k) => `${tokens(k.tokens_avoided)} avoided by cache`,
  },
  tokens_avoided: {
    label: "Tokens avoided",
    note: "What the response cache answered without a round trip.",
    render: (k) => tokens(k.tokens_avoided),
    sub: () => "served from cache",
    tone: () => "good",
  },
  cost_usd: {
    label: "Model spend",
    note: "What the gateway priced the calls at. Cache hits cost nothing and are excluded.",
    render: (k) => usd(k.cost_usd),
    sub: (k) => (k.priced ? "gateway priced" : "nothing priced this window"),
    tone: (k) => (k.priced ? undefined : "bad"),
  },
  cost_avoided_usd: {
    label: "Spend avoided",
    note: "What the cached calls cost the day they were real. Never added to spend - two sums over one table.",
    render: (k) => usd(k.cost_avoided_usd),
    sub: () => "saved by the cache",
    tone: () => "good",
  },
  cost_per_row_cleared_usd: {
    label: "Cost per row cleared",
    note: "Window spend divided by rows that got through. Null when nothing cleared, rather than a division by zero dressed as zero.",
    render: (k) => usd(k.cost_per_row_cleared_usd),
    sub: () => "spend ÷ rows through",
  },
  checks_complete: {
    label: "Checks complete",
    note: "False when the checks that read regulation, internal documentation and copy meaning did not run. The counts are then narrower rather than cleaner.",
    render: (k) => (k.checks_complete ? "Yes" : "No"),
    sub: (k) => (k.checks_complete ? "all checks ran" : "rules only"),
    tone: (k) => (k.checks_complete ? undefined : "bad"),
  },
};

export function KpiTab({ data, persona }: {
  data: TowerKpis | null;
  persona: TowerPersona | null;
}) {
  if (!data) return null;
  const highlighted = new Set(persona?.tiles ?? []);

  return (
    <div className="flex flex-col gap-3">
      {persona && (
        <Panel
          title={persona.label}
          subtitle={persona.question}
        >
          <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2">
            {persona.tiles.map((key) => (
              <KpiTile key={key} id={key} data={data} lead />
            ))}
          </div>
        </Panel>
      )}

      <Caveat text={data.caveat} />

      <Group title="Volume"
             note="What arrived, and how much of it there was a population to judge."
             keys={["feeds_received", "rows_received", "rows_assessed"]}
             data={data} skip={highlighted} />

      <Group title="Quality"
             note="What cleared, what was stopped, and what got through carrying a finding anyway."
             keys={["compliance_pass_rate", "all_clear_rate", "blocked_rate",
                    "awaiting_decision_rate", "residual_error_rate"]}
             data={data} skip={highlighted} />

      <Group title="Correction — the machine and the person"
             note="Two claims, counted separately. What the system settled on its own evidence, and what it declined to settle without somebody."
             keys={["proposals", "autonomous_fills", "autonomous_fill_rate",
                    "decisions_by_person", "human_decision_rate",
                    "awaiting_decision"]}
             data={data} skip={highlighted} />

      <Group title="Reliability"
             note="Whether suppliers are sending files the estate can read."
             keys={["feed_success_rate", "feeds_with_defects"]}
             data={data} skip={highlighted} />

      <Group title="Speed"
             note={
               "Both ends of every duration are the real clock, while the window "
               + "above filters the simulated one. That pairing is the only one "
               + "that means anything on a replay: a feed that arrived in "
               + "simulated August and published this morning did not take four "
               + "weeks."
             }
             keys={["median_hours_to_downstream", "median_hours_to_first_fill"]}
             data={data} skip={highlighted} />

      <Group title="Cost"
             note="Spend and spend avoided are separate sums and must not be added."
             keys={["tokens", "tokens_avoided", "cost_usd", "cost_avoided_usd",
                    "cost_per_row_cleared_usd"]}
             data={data} skip={highlighted} />
    </div>
  );
}

function Group({ title, note, keys, data, skip }: {
  title: string;
  note: string;
  keys: string[];
  data: TowerKpis;
  skip: Set<string>;
}) {
  return (
    <Panel title={title} subtitle={note}>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-2">
        {keys.map((key) => (
          <KpiTile key={key} id={key} data={data} dimmed={skip.has(key)} />
        ))}
      </div>
    </Panel>
  );
}

function KpiTile({ id, data, lead, dimmed }: {
  id: string;
  data: TowerKpis;
  /** In the persona strip at the top, where the figure leads. */
  lead?: boolean;
  /** Already shown in the persona strip above. Kept rather than hidden, so the
   *  group reads as complete - a persona is a lens and not a filter, and a
   *  group with a hole in it would imply the number does not exist. */
  dimmed?: boolean;
}) {
  const def = DEFS[id];
  if (!def) return null;
  return (
    <Tooltip content={def.note}>
      <div className={cn(dimmed && "opacity-60", lead && "ring-1 ring-accent/25 rounded-sm")}>
        <Tile
          label={def.label}
          value={def.render(data)}
          sub={def.sub?.(data)}
          tone={def.tone?.(data)}
        />
      </div>
    </Tooltip>
  );
}
