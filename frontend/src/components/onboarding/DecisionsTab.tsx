import { useState } from "react";
import type { Suggestion } from "../../api";
import { ArtAllClear } from "../../art/illustrations";
import { IconCheck, IconClose, IconSpark } from "../../icons";
import { Badge, Button, Code, EmptyState, Panel, Tooltip, cn } from "../../ui";
import { ConfidenceBar, ReasonList, ValueChip } from "./common";

/* The fourth stage: a category manager answers.
 *
 * Three answers and no fourth. **Approve** takes the value as proposed;
 * **rectify** replaces it with the one the manager types, which is the answer
 * that makes this a queue worth having rather than a pair of buttons; **reject**
 * writes nothing and sends the field back to the supplier.
 *
 * The reasons are open by default on every row rather than behind a
 * disclosure. This screen exists to be *read before* a decision, and evidence
 * a reader has to ask for is evidence most readers will not ask for - which
 * would leave a queue of buttons beside a number, which is the thing this whole
 * design is arranged to avoid.
 *
 * What a person decides is recorded against their name and as a *decision*,
 * not as an inference. That is not bookkeeping: the audit trail is meant to be
 * able to say who asserted a value, and the publish-time safety check treats
 * the two differently because they are different.
 */

export function DecisionsTab({ suggestions, threshold, actor, setActor, busy,
                              onDecide, decided }: {
  suggestions: Suggestion[];
  threshold: number;
  actor: string;
  setActor: (v: string) => void;
  busy: string | null;
  onDecide: (id: string, decision: "APPROVE" | "REJECT" | "RECTIFY",
             value?: unknown, comment?: string) => void;
  /** Everything already answered on this bundle, for the record below. */
  decided: Suggestion[];
}) {
  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="Your queue"
        subtitle={suggestions.length
          ? `${suggestions.length} to decide · oldest first`
          : undefined}
        tone={suggestions.length ? "warn" : undefined}
      >
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">Who is deciding</span>
            <input
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="your name"
              className="rounded-md border border-subtle bg-raised px-2 py-1"
            />
          </label>
          <p className="min-w-[18rem] flex-1 text-sm leading-relaxed text-muted">
            These are the proposals that did not clear{" "}
            {Math.round(threshold * 100)}%, plus every safety-class field —
            those are decided by a person whatever agrees with them. What you
            approve or correct is recorded against your name as a decision,
            not as something a model inferred. Nothing here publishes.
          </p>
        </div>
      </Panel>

      {suggestions.length === 0 ? (
        <Panel title="Nothing waiting">
          <EmptyState art={<ArtAllClear />} title="Your queue is empty">
            Every proposal on this bundle has either cleared the threshold with
            corroboration, or been answered. Proposals appear here as soon as a
            batch is worked in the previous tab.
          </EmptyState>
        </Panel>
      ) : (
        suggestions.map((row) => (
          <DecisionCard
            key={row.id}
            row={row}
            threshold={threshold}
            disabled={!actor.trim()}
            busy={busy === row.id}
            onDecide={onDecide}
          />
        ))
      )}

      {decided.length > 0 && (
        <Panel
          flush
          title="Already answered"
          subtitle={`${decided.length} on this bundle`}
        >
          <div className="divide-y divide-subtle">
            {decided.map((row) => (
              <div key={row.id}
                   className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
                <Badge tone={row.decision === "REJECT" ? "neutral" : "ok"}>
                  {(row.decision ?? "").toLowerCase()}
                </Badge>
                <Code>{row.entity_id}</Code>
                <Code>{row.attribute_path}</Code>
                {row.decision === "RECTIFY" ? (
                  <span className="flex items-baseline gap-1.5 text-muted">
                    <span className="line-through opacity-60">
                      <ValueChip value={row.value} />
                    </span>
                    →
                    <ValueChip value={row.decided_value} />
                  </span>
                ) : row.decision === "APPROVE" ? (
                  <ValueChip value={row.value} />
                ) : (
                  <span className="text-muted">nothing written</span>
                )}
                <span className="ml-auto text-xs text-faint">
                  {row.decided_by}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

function DecisionCard({ row, threshold, disabled, busy, onDecide }: {
  row: Suggestion;
  threshold: number;
  disabled: boolean;
  busy: boolean;
  onDecide: (id: string, decision: "APPROVE" | "REJECT" | "RECTIFY",
             value?: unknown, comment?: string) => void;
}) {
  const [correcting, setCorrecting] = useState(false);
  const [typed, setTyped] = useState("");
  const [comment, setComment] = useState("");

  return (
    <Panel
      tone={row.safety_class ? "danger" : "warn"}
      title={
        <span className="flex items-center gap-1.5">
          <Code>{row.attribute_path}</Code>
          <span className="normal-case tracking-normal text-muted">
            on <Code>{row.entity_id}</Code>
          </span>
        </span>
      }
      subtitle={row.safety_class ? "safety class" : undefined}
      actions={
        <ConfidenceBar
          value={row.confidence}
          threshold={row.threshold ?? threshold}
          safety={row.safety_class}
        />
      }
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline gap-2 text-sm">
          <span className="text-muted">proposed</span>
          <ValueChip value={row.value} />
          {row.citation?.doc_id && (
            <Tooltip content={row.citation.heading ?? row.citation.doc_id}>
              <span><Code>{row.citation.doc_id}</Code></span>
            </Tooltip>
          )}
        </div>

        <div className="rounded-md border border-subtle bg-sunken p-2.5">
          <p className="mb-1.5 text-2xs uppercase tracking-caps text-faint">
            why it scored what it did
          </p>
          <ReasonList reasons={row.reasons} />
        </div>

        {correcting && (
          <div className="flex flex-wrap items-end gap-2 border-t border-subtle pt-3">
            <label className="flex min-w-[10rem] flex-1 flex-col gap-1 text-sm">
              <span className="text-muted">
                The value it should be
              </span>
              <input
                autoFocus
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                placeholder="what the record should say"
                className="rounded-md border border-subtle bg-raised px-2 py-1"
              />
            </label>
            <label className="flex min-w-[12rem] flex-1 flex-col gap-1 text-sm">
              <span className="text-muted">Why (optional)</span>
              <input
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                placeholder="the spec sheet says otherwise"
                className="rounded-md border border-subtle bg-raised px-2 py-1"
              />
            </label>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-1.5 border-t border-subtle pt-3">
          {correcting ? (
            <>
              <Button
                tone="primary"
                loading={busy}
                disabled={disabled || !typed.trim()}
                icon={<IconCheck size={14} />}
                onClick={() => onDecide(row.id, "RECTIFY",
                                        coerce(typed, row.value), comment)}
              >
                Record this instead
              </Button>
              <Button tone="ghost" onClick={() => setCorrecting(false)}>
                cancel
              </Button>
            </>
          ) : (
            <>
              <Button
                tone="primary"
                loading={busy}
                disabled={disabled}
                icon={<IconCheck size={14} />}
                onClick={() => onDecide(row.id, "APPROVE")}
              >
                Approve
              </Button>
              <Button
                disabled={disabled}
                icon={<IconSpark size={14} />}
                onClick={() => { setCorrecting(true); setTyped(""); }}
              >
                Rectify
              </Button>
              <Button
                tone="danger"
                disabled={disabled}
                icon={<IconClose size={14} />}
                onClick={() => onDecide(row.id, "REJECT")}
              >
                Reject
              </Button>
            </>
          )}
          {disabled && (
            <span className={cn("text-xs text-faint")}>
              a decision has to be attributable to somebody — put your name in
              the box above
            </span>
          )}
        </div>
      </div>
    </Panel>
  );
}

/** Read a typed value back as the type the proposal was.
 *
 *  The record's own declared type is the authority and the server re-validates
 *  against it; this is only so that typing 65 into a field the catalog holds as
 *  an integer does not arrive as the string "65" and get recorded as one.
 */
function coerce(typed: string, like: unknown): unknown {
  const text = typed.trim();
  if (Array.isArray(like)) {
    return text.split(",").map((part) => part.trim()).filter(Boolean);
  }
  if (typeof like === "number") {
    const parsed = Number(text);
    return Number.isFinite(parsed) ? parsed : text;
  }
  if (typeof like === "boolean") return /^(true|yes|1)$/i.test(text);
  return text;
}
