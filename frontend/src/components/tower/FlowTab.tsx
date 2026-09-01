import type { TowerRegister } from "../../api";
import { EmptyState, Panel, Table, Td, Th, Tr, Tooltip, cn } from "../../ui";
import { Caveat, STATE_LABEL, STATE_NOTE, STATE_ORDER } from "./common";

/* Where every row a supplier sent has got to.
 *
 * The whole point of this section: two state spines already existed and
 * neither answered it. A submission was tracked through nine stages and
 * stopped at `verdict`; a product's lifecycle lane started from its current
 * state and knew nothing about which archive delivered it.
 *
 * **The grain is the row, and the screen says so.** Product Lifecycle places a
 * *product*, and a product is as blocked as its worst variant - so a pack whose
 * 500ml is fit to sell and whose 1L is not appears there as one product with
 * its supplier, and here as one row cleared and one not. Both are right, and
 * the caption is what stops the pair reading as a contradiction.
 */

export function FlowTab({ data, onOpenFeed }: {
  data: TowerRegister | null;
  onOpenFeed: (feedId: string) => void;
}) {
  if (!data) return null;

  const total = Object.values(data.totals).reduce((a, b) => a + b, 0);
  if (!total) {
    return (
      <Panel title="Flow">
        <EmptyState
          compact
          title="Nothing to place in this window"
          children={
            data.caveat
              ?? "No supplier data pack arrived between these dates, so there "
                 + "is no onboarding population to report on."
          }
        />
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Received → on sale"
        subtitle={
          `${total} rows across ${data.assessable_feeds} data packs. The grain `
          + "is the row a supplier sent; Product Lifecycle places the product "
          + "it belongs to, and the two can differ for the same pack without "
          + "either being wrong."
        }
      >
        <div className="flex flex-col gap-2">
          <StateBar totals={data.totals} total={total} />
          <div className="grid grid-cols-[repeat(auto-fit,minmax(112px,1fr))] gap-1.5">
            {STATE_ORDER.map((state) => (
              <Tooltip key={state} content={STATE_NOTE[state]}>
                <div
                  className={cn(
                    "min-w-0 rounded-sm border border-subtle bg-sunken",
                    "px-2 py-1.5",
                    data.totals[state] === 0 && "opacity-45"
                  )}
                >
                  <div className="truncate text-2xs uppercase tracking-caps text-faint">
                    {STATE_LABEL[state]}
                  </div>
                  <div className="font-mono text-base tabular-nums text-fg">
                    {data.totals[state]}
                  </div>
                </div>
              </Tooltip>
            ))}
          </div>
          <Caveat text={data.caveat} />
        </div>
      </Panel>

      <Panel
        title="By feed"
        subtitle="One row per archive, in the states its rows ended in."
        flush
      >
        <Table>
          <thead>
            <Tr>
              <Th>Feed</Th>
              <Th>Supplier</Th>
              <Th>Carried by</Th>
              <Th num>Rows</Th>
              {STATE_ORDER.map((s) => (
                <Th key={s} num>
                  <Tooltip content={STATE_NOTE[s]}>
                    <span>{STATE_LABEL[s]}</span>
                  </Tooltip>
                </Th>
              ))}
              <Th num>
                <Tooltip content="Rows this system filled without asking anybody. Counted apart from the states because it is a fact about the past that stays true after the row moves on.">
                  <span>AI fixed</span>
                </Tooltip>
              </Th>
            </Tr>
          </thead>
          <tbody>
            {data.feeds
              .filter((f) => f.kind === "DATA_PACK")
              .map((feed) => (
                <Tr key={feed.feed_id} onClick={() => onOpenFeed(feed.feed_id)}>
                  <Td className="font-mono text-sm">{feed.feed_id.slice(0, 12)}</Td>
                  <Td>{feed.supplier}</Td>
                  <Td className="font-mono text-sm">{feed.system}</Td>
                  <Td num>{feed.rows}</Td>
                  {STATE_ORDER.map((s) => (
                    <Td key={s} num
                        className={feed.counts[s] ? undefined : "text-faint"}>
                      {feed.counts[s] || "—"}
                    </Td>
                  ))}
                  <Td num className={feed.ai_corrected ? undefined : "text-faint"}>
                    {feed.ai_corrected || "—"}
                  </Td>
                </Tr>
              ))}
          </tbody>
        </Table>
      </Panel>
    </div>
  );
}

/** One bar, seven segments, in flow order.
 *
 * Hand-rolled rather than charted, like every other diagram here. A segment
 * under two per cent still gets two per cent of the width, because a state with
 * one row in it disappearing entirely is the state somebody most needs to see.
 */
function StateBar({ totals, total }: {
  totals: TowerRegister["totals"];
  total: number;
}) {
  const TONE: Record<string, string> = {
    RECEIVED: "bg-neutral-border",
    PROCESSING: "bg-info",
    ON_HOLD: "bg-warn",
    BLOCKED: "bg-danger",
    ALL_CLEAR: "bg-ok",
    PUSHED_DOWNSTREAM: "bg-ok/70",
    ON_SALE: "bg-accent",
  };
  const shown = STATE_ORDER.filter((s) => totals[s] > 0);
  return (
    <div
      className="flex h-2.5 overflow-hidden rounded-full bg-sunken"
      role="img"
      aria-label={shown
        .map((s) => `${totals[s]} ${STATE_LABEL[s]}`)
        .join(", ")}
    >
      {shown.map((state) => (
        <Tooltip
          key={state}
          content={`${totals[state]} ${STATE_LABEL[state].toLowerCase()} — ${STATE_NOTE[state]}`}
        >
          <div
            className={cn("h-full", TONE[state])}
            style={{ width: `${Math.max(2, (totals[state] / total) * 100)}%` }}
          />
        </Tooltip>
      ))}
    </div>
  );
}
