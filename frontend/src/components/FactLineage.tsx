import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, fmt } from "../api";
import type { Fact } from "../api";
import { IconChevronRight, IconTrace } from "../icons";
import { Badge, Code, Panel, SegmentedControl, Skeleton, Tooltip, cn } from "../ui";
import { ProvBadge } from "./common";

/* Fact lineage.
 *
 * The bitemporal store is the strongest audit claim in the system and it was,
 * until now, entirely invisible: the data was written correctly and never
 * shown. This is the panel that makes it checkable.
 *
 * Two time axes, and the distinction is the whole point. `valid_from` is when
 * something became true in the world; `recorded_at` is when we found out. A
 * spec sheet corrected on the 28th and clarified on the 32nd is two different
 * dates on both axes, and copy written on the 29th has to be judged against
 * what was known on the 29th - not against what we know now. A correction
 * supersedes rather than overwrites, so the chain below is the complete
 * history of a belief.
 */

/** The kinds of fact the store actually holds, with names a reviewer uses.
 *  Read off the schema rather than invented: the ingest writes facts about
 *  variants, products, listings, channels and document versions. */
const KINDS = [
  { value: "variant", label: "Variants",
    hint: "corrected attribute values on one sellable variant" },
  { value: "product", label: "Products",
    hint: "values asserted for every variant of a product" },
  { value: "listing", label: "Listings",
    hint: "publish state of one variant on one channel" },
  { value: "channel", label: "Channels", hint: "channel-wide holds and rejections" },
  { value: "source_doc", label: "Documents",
    hint: "supplier documents superseding each other" },
] as const;

const kindLabel = (value: string) =>
  KINDS.find((k) => k.value === value)?.label.toLowerCase() ?? value;

export function FactLineage({
  attr, kind: initialKind = "variant", title = "Fact lineage", icon, note,
}: {
  /** Narrow to one attribute path - "specs.power_w". The whole history of the
   *  corrected value, rather than the whole store. */
  attr?: string;
  kind?: string;
  title?: string;
  icon?: ReactNode;
  /** Replaces the standing explanation where the caller has a more specific
   *  one to give. */
  note?: ReactNode;
} = {}) {
  const [kind, setKind] = useState<string>(initialKind);
  const [facts, setFacts] = useState<Fact[] | null>(null);
  const [mix, setMix] = useState<Record<string, number>>({});

  useEffect(() => {
    let live = true;
    setFacts(null);
    api.facts(kind, attr)
      .then((r) => {
        if (!live) return;
        setFacts(r.facts);
        setMix(r.provenance_mix ?? {});
      })
      .catch(() => { if (live) setFacts([]); });
    return () => { live = false; };
  }, [kind, attr]);

  return (
    <Panel
      title={title}
      icon={icon ?? <IconTrace size={14} />}
      subtitle={attr ? attr : undefined}
      actions={
        <SegmentedControl
          ariaLabel="Fact kind"
          value={kind}
          onChange={setKind}
          options={KINDS.map((k) => ({
            value: k.value, label: k.label, title: k.hint,
          }))}
        />
      }
    >
      <div className="flex flex-col gap-3">
        <p className="text-sm leading-relaxed text-muted">
          {note ?? (
            <>
              Every fact carries both time axes: when it became true, and when
              we learned it. Corrections supersede rather than overwrite, so
              published copy can always be judged against the evidence it
              actually had. Expand one to see its full chain.
            </>
          )}
        </p>

        {Object.keys(mix).length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-faint">across the whole store:</span>
            {Object.entries(mix).map(([provenanceKind, n]) => (
              <span key={provenanceKind} className="flex items-center gap-1">
                <ProvBadge
                  provenance={{ kind: provenanceKind as never }}
                  showConfidence={false}
                />
                <span className="font-mono text-xs text-faint tabular-nums">
                  {n}
                </span>
              </span>
            ))}
          </div>
        )}

        {facts === null ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : facts.length === 0 ? (
          <p className="text-sm text-muted">
            No {kindLabel(kind)} facts
            {attr ? <> for <Code>{attr}</Code></> : null} in force at the
            current simulated clock.
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {facts.map((fact) => (
              <FactRow key={fact.id} fact={fact} />
            ))}
          </ul>
        )}
      </div>
    </Panel>
  );
}

function FactRow({ fact }: { fact: Fact }) {
  const [open, setOpen] = useState(false);
  const [chain, setChain] = useState<Fact[] | null>(null);

  useEffect(() => {
    if (!open || chain) return;
    let live = true;
    api.lineage(fact.id)
      .then((r) => { if (live) setChain(r.lineage); })
      .catch(() => { if (live) setChain([]); });
    return () => { live = false; };
  }, [open, chain, fact.id]);

  return (
    <li className="rounded-sm border border-subtle bg-sunken">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-start gap-2 px-2.5 py-2 text-left"
      >
        <IconChevronRight
          size={13}
          className={cn(
            "mt-1 shrink-0 text-faint transition-transform",
            "duration-[var(--dur-fast)]",
            open && "rotate-90"
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-sm">
            <Code>{fact.entity_id}</Code>
            <span className="text-faint">{fact.attr}</span>
            <strong className="font-mono">{fmt.value(fact.value)}</strong>
            <ProvBadge provenance={fact.provenance} />
          </div>
          <div className="mt-0.5 flex flex-wrap gap-x-3 font-mono text-xs text-faint tabular-nums">
            <Tooltip content="When this became true in the world">
              <span>valid {fmt.date(fact.valid_from)}</span>
            </Tooltip>
            <Tooltip content="When we learned it">
              <span>known {fmt.stamp(fact.recorded_at)}</span>
            </Tooltip>
            {fact.supersedes_id && <Badge tone="warn">correction</Badge>}
          </div>
        </div>
      </button>

      {open && (
        <div className="border-t border-subtle px-2.5 py-2">
          {chain === null ? (
            <Skeleton className="h-8 w-full" />
          ) : chain.length === 0 ? (
            <p className="text-sm text-muted">
              No earlier version — this is the original assertion.
            </p>
          ) : (
            <ol className="flex flex-col gap-1.5">
              {chain.map((version, i) => (
                <li
                  key={version.id}
                  className="flex items-start gap-2 text-sm"
                >
                  <span className="mt-0.5 w-5 shrink-0 font-mono text-xs text-faint tabular-nums">
                    {chain.length - i}
                  </span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <strong className="font-mono">{fmt.value(version.value)}</strong>
                      <ProvBadge provenance={version.provenance} />
                      {i === 0 && <Badge tone="ok">in force</Badge>}
                    </div>
                    <div className="font-mono text-xs text-faint tabular-nums">
                      valid {fmt.date(version.valid_from)}
                      {version.valid_to && ` → ${fmt.date(version.valid_to)}`}
                      {" · known "}{fmt.stamp(version.recorded_at)}
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </li>
  );
}
