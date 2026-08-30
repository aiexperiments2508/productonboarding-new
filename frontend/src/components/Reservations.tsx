import { useEffect, useState } from "react";
import { api, fmt } from "../api";
import type { Reservation } from "../api";
import { IconAlert } from "../icons";
import { Badge, Code, Panel, Skeleton, Table, Td, Th, Tooltip } from "../ui";
import { ChannelChip } from "./common";

/* Publish locks.
 *
 * A lock is one channel and one product for one batch date. Taking it is how
 * two republishes of the same listing are prevented from racing: HARD locks are
 * exclusive per (resource, date), enforced by a partial unique index in SQLite
 * rather than by application logic. A second concurrent republish fails at the
 * database, not at a code path someone can forget to write.
 *
 * That is the right way to do it and it was, until this panel, only checkable
 * by reading the schema. Every row here is a claim on a channel that no other
 * republish can take, and the count is what a competing commit would collide
 * with. SOFT and HARD are distinguished because only one of them is exclusive:
 * a soft hold is an intention, a hard one is a guarantee.
 */

/** The six channel ids are the only tokens in a resource id that resolve to a
 *  place; everything else is a product or variant id and stays as an id. */
const CHANNEL_ID = /^CH-[A-Z0-9-]+$/;

/** A resource id, read as the channel-and-product pair it encodes.
 *
 * The raw id is always kept underneath: a reviewer chasing a publish conflict
 * searches for `CH-PRINT:PRD-01`, not for "the print catalogue".
 */
function LockTarget({ resourceId }: { resourceId?: string }) {
  if (!resourceId) return <span className="text-sm text-faint">—</span>;
  const parts = resourceId.split(/[:|/]/).filter(Boolean);
  const channel = parts.find((p) => CHANNEL_ID.test(p));
  const rest = parts.filter((p) => p !== channel);
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="flex flex-wrap items-center gap-1.5">
        {channel && <ChannelChip channelId={channel} />}
        {rest.map((p) => <Code key={p}>{p}</Code>)}
      </div>
      <span className="truncate font-mono text-2xs text-faint">
        {resourceId}
      </span>
    </div>
  );
}

export function Reservations({ refreshKey }: {
  /** Changes when a commit or a rollback lands, so the panel re-reads. */
  refreshKey?: string;
}) {
  const [rows, setRows] = useState<Reservation[] | null>(null);

  useEffect(() => {
    let live = true;
    api.reservations()
      .then((r) => {
        if (live) setRows(r.reservations as unknown as Reservation[]);
      })
      .catch(() => { if (live) setRows([]); });
    return () => { live = false; };
  }, [refreshKey]);

  const hard = (rows ?? []).filter((r) => r.status === "HARD").length;

  return (
    <Panel
      title="Publish locks"
      flush
      subtitle={rows ? `${hard} exclusive` : undefined}
      actions={
        <Tooltip content={
          "A HARD lock is exclusive per channel, product and batch date, held by "
          + "a partial unique index. A second republish of the same listing "
          + "cannot take the slot — the database refuses it rather than the "
          + "application remembering to check."
        }>
          <Badge tone="ok" dot>db-enforced</Badge>
        </Tooltip>
      }
    >
      {rows === null ? (
        <div className="flex flex-col gap-2 p-3">
          {Array.from({ length: 3 }, (_, i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <p className="p-3 text-sm leading-relaxed text-muted">
          Nothing locked. A lock is taken only where a resolution actually
          republishes — a print run inside its freeze window, a marketplace feed
          being replaced. A resolution that corrects stored values without
          pushing them anywhere takes none, so an empty table here is a fact
          about the resolution rather than a failed commit.
        </p>
      ) : (
        <Table scroll>
          <thead>
            <tr>
              <Th>Channel and product</Th>
              <Th>Batch date</Th>
              <Th num>Qty</Th>
              <Th>Lock</Th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 40).map((r, i) => {
              const exclusive = r.status === "HARD";
              return (
                <tr
                  key={r.id ?? i}
                  className="border-b border-subtle last:border-b-0"
                >
                  <Td>
                    <LockTarget resourceId={r.resource_id} />
                    {r.incident_id && (
                      <div className="mt-0.5 truncate font-mono text-2xs text-faint">
                        held for {r.incident_id}
                      </div>
                    )}
                  </Td>
                  <Td className="font-mono text-sm tabular-nums">
                    {r.bucket_date ?? "—"}
                  </Td>
                  <Td num>
                    {typeof r.qty === "number" ? r.qty.toLocaleString() : "—"}
                  </Td>
                  <Td>
                    <Tooltip
                      content={
                        exclusive
                          ? "Exclusive. No other republish can take this channel on this date."
                          : r.status === "RELEASED"
                          ? "Released. The slot is free again."
                          : "An intention, not a guarantee. It does not stop a competing republish."
                      }
                    >
                      <span className="inline-flex flex-col gap-0.5">
                        <span>
                          <Badge tone={exclusive ? "danger" : "neutral"}>
                            {exclusive ? "exclusive" : (r.status ?? "—").toLowerCase()}
                          </Badge>
                        </span>
                        {r.expires_at && (
                          <span className="font-mono text-2xs text-faint">
                            until {fmt.stamp(r.expires_at)}
                          </span>
                        )}
                      </span>
                    </Tooltip>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}

      {rows && rows.length > 40 && (
        <div className="flex items-center gap-2 border-t border-subtle px-3 py-2 text-sm text-faint">
          <IconAlert size={13} />
          showing 40 of {rows.length}
        </div>
      )}
    </Panel>
  );
}
