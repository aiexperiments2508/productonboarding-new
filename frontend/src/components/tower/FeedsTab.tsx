import type { TowerFeedDetail, TowerRegister } from "../../api";
import { fmt } from "../../api";
import { Badge, EmptyState, Panel, Table, Td, Th, Tooltip, Tr } from "../../ui";
import { Caveat, STATE_LABEL, StateChip, usd } from "./common";

/* The feed register: what arrived, from whom, carried by what.
 *
 * A feed is not a new object - it is a submission, which already has an id, a
 * supplier, a carrier, a timestamp and the entities it named. This lists them.
 *
 * **An image feed is not a separate kind of thing.** The brief asks about
 * product feeds and image feeds as two pipes; in this estate they are one pipe
 * carrying two payloads, and what distinguishes them is the carrier - the
 * imaging system and the artwork library deliver imagery, the data pool cannot.
 * So the table shows the carrier and a media count per feed rather than a
 * second feed type the code does not have.
 */

export function FeedsTab({ data, detail, onOpenFeed, onCloseFeed }: {
  data: TowerRegister | null;
  detail: TowerFeedDetail | null;
  onOpenFeed: (feedId: string) => void;
  onCloseFeed: () => void;
}) {
  if (!data) return null;

  if (detail) {
    return <FeedDetail detail={detail} onClose={onCloseFeed} />;
  }

  if (!data.feeds.length) {
    return (
      <Panel title="Feeds">
        <EmptyState
          compact
          title="No feed arrived in this window"
          children="Widen the dates, or clear them to see every feed on record."
        />
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
        <Panel title="By kind" subtitle="What suppliers actually sent">
          <Grouped rows={data.by_kind} />
        </Panel>
        <Panel title="By carrier"
               subtitle="Which system brought it in over MCP">
          <Grouped rows={data.by_system} />
        </Panel>
        <Panel title="By supplier" subtitle="Who is sending the most">
          <Grouped rows={data.by_supplier.slice(0, 8)} />
        </Panel>
      </div>

      <Caveat text={data.caveat} />

      <Panel title="The register"
             subtitle={`${data.count} of ${data.matched} feeds`} flush>
        <Table scroll>
          <thead>
            <Tr>
              <Th>Feed</Th>
              <Th>
                <Tooltip content="When this process actually received the submission, on the real clock. The date window above runs on the replay clock, so a feed can arrive today and sit in a July window.">
                  <span>Arrived</span>
                </Tooltip>
              </Th>
              <Th>Supplier</Th>
              <Th>Carried by</Th>
              <Th>Kind</Th>
              <Th num>Rows</Th>
              <Th num>
                <Tooltip content="Photographs in the archive. Imagery is a payload on the product feed, not a feed of its own - which system carried it is the distinction that exists.">
                  <span>Images</span>
                </Tooltip>
              </Th>
              <Th>In the record</Th>
              <Th num>
                <Tooltip content="What the models spent on this feed. Zero means nothing was asked of a model for it - not that it was free.">
                  <span>Spend</span>
                </Tooltip>
              </Th>
            </Tr>
          </thead>
          <tbody>
            {data.feeds.map((feed) => (
              <Tr key={feed.feed_id}
                  onClick={feed.kind === "DATA_PACK"
                    ? () => onOpenFeed(feed.feed_id) : undefined}>
                <Td className="font-mono text-sm">{feed.feed_id.slice(0, 12)}</Td>
                <Td className="font-mono text-sm text-muted">
                  <Tooltip content={`Real time this platform received the submission. The date window filters on the replay clock, where this feed is stamped ${fmt.stamp(feed.submitted_at)}.`}>
                    <span>{fmt.stamp(feed.wall_at)}</span>
                  </Tooltip>
                </Td>
                <Td>{feed.supplier}</Td>
                <Td className="font-mono text-sm">{feed.system}</Td>
                <Td><Badge tone="neutral">{feed.kind}</Badge></Td>
                <Td num>{feed.rows}</Td>
                <Td num className={feed.media_files ? undefined : "text-faint"}>
                  {feed.media_files || "—"}
                </Td>
                <Td>
                  {feed.ingested
                    ? <Badge tone="ok">accepted</Badge>
                    : <Badge tone="warn">not yet</Badge>}
                </Td>
                <Td num className={feed.spend.cost_usd ? undefined : "text-faint"}>
                  {feed.spend.calls ? usd(feed.spend.cost_usd) : "—"}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </Panel>
    </div>
  );
}

function Grouped({ rows }: {
  rows: { key: string; feeds: number; rows: number }[];
}) {
  if (!rows.length) {
    return <p className="text-2xs text-faint">nothing in this window</p>;
  }
  return (
    <ul className="flex flex-col gap-1">
      {rows.map((row) => (
        <li key={row.key}
            className="flex items-baseline justify-between gap-2 text-xs">
          <span className="truncate font-mono text-muted">{row.key}</span>
          <span className="shrink-0 font-mono tabular-nums text-fg">
            {row.feeds}
            <span className="text-faint"> · {row.rows} rows</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** One feed, row by row.
 *
 * The gate sentence is shown rather than the check name, for the reason
 * `gate._sentence` builds one: "it failed policy_conformance" is not something
 * anybody outside this repository can act on.
 */
function FeedDetail({ detail, onClose }: {
  detail: TowerFeedDetail;
  onClose: () => void;
}) {
  return (
    <Panel
      title={detail.feed_id}
      subtitle={
        `${detail.supplier} via ${detail.system} · ${detail.rows} rows, `
        + `${detail.assessed} placed · grain: the ${detail.grain} a supplier sent`
      }
      actions={
        <button
          type="button"
          onClick={onClose}
          className="rounded-sm border border-line px-2 py-1 text-2xs text-muted hover:text-fg"
        >
          Back to the register
        </button>
      }
      flush
    >
      <Caveat text={detail.caveat} className="m-2.5" />
      <Table scroll>
        <thead>
          <Tr>
            <Th>SKU</Th>
            <Th>Name</Th>
            <Th>State</Th>
            <Th>Why</Th>
            <Th num>Open</Th>
            <Th num>
              <Tooltip content="Values written unattended, with a citation. Counted apart from the state because it stays true after the row moves on.">
                <span>AI fixed</span>
              </Tooltip>
            </Th>
            <Th num>Decided</Th>
          </Tr>
        </thead>
        <tbody>
          {detail.products.map((row) => (
            <Tr key={row.entity_id}>
              <Td className="font-mono text-sm">{row.sku}</Td>
              <Td className="max-w-[22ch] truncate">{row.name}</Td>
              <Td><StateChip state={row.state} /></Td>
              <Td className="max-w-[38ch] text-2xs text-muted">
                {row.gate.why
                  || (row.open_findings
                    ? `${row.open_findings} open finding${row.open_findings > 1 ? "s" : ""}`
                    : STATE_LABEL[row.state])}
              </Td>
              <Td num className={row.open_findings ? undefined : "text-faint"}>
                {row.open_findings || "—"}
              </Td>
              <Td num className={row.ai_corrected ? undefined : "text-faint"}>
                {row.ai_corrected || "—"}
              </Td>
              <Td num className={row.decided_by_person ? undefined : "text-faint"}>
                {row.decided_by_person || "—"}
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </Panel>
  );
}
