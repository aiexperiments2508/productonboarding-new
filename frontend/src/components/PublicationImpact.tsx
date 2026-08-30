import { useEffect, useState } from "react";
import { api } from "../api";
import type { PublicationImpact as Impact } from "../api";
import { Badge, Code, Panel, Skeleton, Tooltip, cn } from "../ui";

/* What a correction reaches, said in the words people act in.
 *
 * Blast Radius already answered this - fifteen content assets across five
 * listings on four channels - and answered it entirely in identifiers only this
 * system can read. A buyer asked which products are affected cannot answer from
 * VAR-01B; a marketplace account manager asked what to reissue cannot answer
 * from LST-07.
 *
 * So this panel says the same true thing twice over in a second vocabulary: the
 * SKUs, and the systems that have to be told about them.
 *
 * The dispatch plan beside it is the part worth reading the code for. It shows
 * what *would* happen without anything happening - so a reviewer sees that the
 * printed catalogue is inside its freeze window before deciding, rather than
 * from a report afterwards. Looking does not publish.
 */

const OUTCOME_TONE: Record<string, "ok" | "warn" | "danger" | "neutral"> = {
  SENT: "ok",
  DEFERRED: "warn",
  REFUSED: "danger",
};

const OUTCOME_WORDS: Record<string, string> = {
  SENT: "would send",
  DEFERRED: "would defer",
  REFUSED: "would refuse",
};

export function PublicationImpact({ entityId }: { entityId: string | null }) {
  const [impact, setImpact] = useState<Impact | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!entityId) { setImpact(null); return; }
    let cancelled = false;
    setBusy(true);
    api.publicationImpact(entityId)
      .then((next) => { if (!cancelled) setImpact(next); })
      .catch(() => { if (!cancelled) setImpact(null); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [entityId]);

  if (!entityId) return null;
  if (busy || !impact) {
    return (
      <Panel title="Who has to be told" subtitle="Affected SKUs, by system">
        <Skeleton className="h-32" />
      </Panel>
    );
  }

  const deferred = impact.dispatch_plan.filter((r) => r.outcome !== "SENT");

  return (
    <Panel
      title="Who has to be told"
      subtitle={
        `${impact.skus.length} SKU(s) across ` +
        `${impact.dispatch_plan.length} publication system(s)`
      }
      actions={
        deferred.length > 0 ? (
          <Badge tone="warn" dot>{deferred.length} would not go out</Badge>
        ) : (
          <Badge tone="ok" dot>all reachable</Badge>
        )
      }
    >
      <section>
        <h4 className="text-2xs uppercase tracking-caps text-faint">
          affected SKUs
        </h4>
        <ul className="sc-stagger mt-1.5 flex flex-wrap gap-1.5">
          {impact.skus.map((row, i) => (
            <li key={row.entity_id} style={{ ["--i" as string]: i }}>
              <Tooltip
                content={`${row.name} — live on ${row.channels.join(", ") || "no channel"}`}
              >
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-sm border",
                    "border-subtle bg-raised px-2 py-1",
                  )}
                >
                  <Code>{row.sku}</Code>
                  <span className="text-2xs text-faint">
                    {row.listings.length} listing
                    {row.listings.length === 1 ? "" : "s"}
                  </span>
                </span>
              </Tooltip>
            </li>
          ))}
        </ul>
      </section>

      {/* What would happen, without anything happening. A reviewer should see
          the frozen channel before deciding, not from a report afterwards. */}
      <section className="mt-4">
        <h4 className="text-2xs uppercase tracking-caps text-faint">
          if this were dispatched now
        </h4>
        <ul className="sc-stagger mt-1.5 flex flex-col gap-1">
          {impact.dispatch_plan.map((row, i) => (
            <li
              key={row.system}
              style={{ ["--i" as string]: i }}
              className={cn(
                "flex flex-wrap items-center gap-2 rounded-sm border px-2 py-1.5",
                row.outcome === "SENT"
                  ? "border-subtle bg-raised"
                  : "border-estate-degraded-border bg-estate-degraded-soft",
              )}
            >
              <Badge tone={OUTCOME_TONE[row.outcome] ?? "neutral"}>
                {OUTCOME_WORDS[row.outcome] ?? row.outcome.toLowerCase()}
              </Badge>
              <span className="min-w-0 truncate text-sm text-fg">
                {row.title}
              </span>
              <span className="text-2xs text-faint">
                {row.skus.join(", ")}
              </span>
              {/* Said plainly rather than left as a number of days: this is the
                  fact that decides whether a correction reaching this channel
                  is a fix or a conversation. */}
              {!row.recallable && (
                <Tooltip content="What this channel publishes cannot be recalled.">
                  <span className="shrink-0">
                    <Badge tone="warn">cannot be recalled</Badge>
                  </span>
                </Tooltip>
              )}
              {row.reason && (
                <span className="ml-auto min-w-0 truncate text-2xs text-muted">
                  {row.reason}
                </span>
              )}
            </li>
          ))}
        </ul>
      </section>
    </Panel>
  );
}
