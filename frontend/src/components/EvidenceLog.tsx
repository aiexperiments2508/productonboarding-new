import { useState } from "react";
import type { EvidenceRecord } from "../api";
import { IconChevronRight, IconSearch } from "../icons";
import { Badge, Code, Panel, Tooltip, cn } from "../ui";

/* What the investigator asked for, and what it got.
 *
 * This is the visible proof of the one place in the system where a model
 * chooses an action rather than describing one. Without it, "the investigation
 * decides which evidence to query next" is a claim in a README; with it, a
 * reviewer can read the question the agent asked, why it asked, and whether
 * the desk answered.
 *
 * Refusals are shown, not hidden. A request for a tool outside the allowlist
 * is the clearest evidence the allowlist is doing anything at all, and burying
 * it would leave the governance story resting on trust.
 */

const STATUS_TONE = {
  OK: "ok",
  REFUSED: "danger",
  ERROR: "warn",
} as const;

export function EvidenceLog({ records }: { records: EvidenceRecord[] }) {
  if (!records?.length) return null;

  const refused = records.filter((r) => r.status !== "OK").length;

  return (
    <Panel
      title="Evidence the investigator requested"
      icon={<IconSearch size={14} />}
      subtitle={
        `${records.length} ${records.length === 1 ? "request" : "requests"}` +
        (refused ? ` · ${refused} refused` : "")
      }
    >
      <p className="mb-3 text-sm leading-relaxed text-muted">
        The investigation is not a fixed script. Where the record did not
        settle which variant the correction applies to, the agent asked the
        evidence desk a specific question and was called again with the answer.
        The desk is a closed, read-only allowlist — anything outside it is
        refused and recorded as refused.
      </p>
      <ol className="flex flex-col gap-2">
        {records.map((record, i) => (
          <EvidenceRow key={`${record.tool}-${i}`} record={record} index={i} />
        ))}
      </ol>
    </Panel>
  );
}

function EvidenceRow({ record, index }: { record: EvidenceRecord; index: number }) {
  const [open, setOpen] = useState(false);
  const tone = STATUS_TONE[record.status] ?? "neutral";

  return (
    <li
      style={{ ["--i" as string]: index }}
      className="animate-rise-in rounded-sm border border-subtle bg-sunken"
    >
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
          <div className="flex flex-wrap items-center gap-1.5">
            <Code>
              {record.tool}({record.argument || "—"})
            </Code>
            <Badge tone={tone}>{record.status}</Badge>
          </div>
          {record.why && (
            <div className="mt-1 text-sm text-muted">
              <span className="text-faint">asked because </span>
              {record.why}
            </div>
          )}
        </div>
      </button>
      {open && (
        <pre
          className={cn(
            "mx-2.5 mb-2.5 max-h-56 overflow-auto rounded-sm border",
            "border-subtle bg-raised p-2.5 font-mono text-xs leading-relaxed",
            "text-muted"
          )}
        >
          {JSON.stringify(record.result, null, 2)}
        </pre>
      )}
    </li>
  );
}

/** The allowlist itself, for the governance surface in System Control. */
export function EvidenceAllowlist({ tools, maxPasses, maxPerPass }: {
  tools: { name: string; takes: string; describes: string }[];
  maxPasses: number;
  maxPerPass: number;
}) {
  return (
    <div className="flex flex-col gap-2.5">
      <p className="text-sm leading-relaxed text-muted">
        The investigator may call these and nothing else. Every entry is
        read-only: none of them writes a fact, takes a reservation or moves a
        number, so a bad request cannot escalate past an error message.
        Committing a plan still goes through the approval gate.
      </p>
      <div className="flex flex-wrap gap-1.5">
        <Tooltip content="Extra rounds of evidence-gathering before the investigator must conclude">
          <Badge tone="neutral" mono>max {maxPasses} passes</Badge>
        </Tooltip>
        <Tooltip content="Requests honoured per round; the rest are dropped">
          <Badge tone="neutral" mono>max {maxPerPass} per pass</Badge>
        </Tooltip>
        <Badge tone="ok" dot>read-only</Badge>
      </div>
      <ul className="flex flex-col gap-1.5">
        {tools.map((tool) => (
          <li key={tool.name} className="text-sm">
            <Code>{tool.name}</Code>
            <span className="text-faint"> takes {tool.takes}</span>
            <div className="text-muted">{tool.describes}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}
