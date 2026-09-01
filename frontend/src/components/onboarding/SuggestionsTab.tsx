import { Fragment, useState } from "react";
import type { BatchReport, Suggestion } from "../../api";
import { ArtQuietFeed } from "../../art/illustrations";
import { IconChevronDown, IconChevronRight, IconSpark } from "../../icons";
import {
  Badge, Button, Code, EmptyState, Panel, Table, Tooltip, cn,
} from "../../ui";
import { Kpi } from "../common";
import { ConfidenceBar, ReasonList, ValueChip } from "./common";

/* The third stage: what could fill the gaps, and how sure are we.
 *
 * One row per missing field. The value comes from a passage a model actually
 * read, or - when nothing was retrievable, or there was no model to read with -
 * from what the rest of the product, the rest of the category and the reviewer's
 * own past decisions already say.
 *
 * The score beside it is not the model's own number. It is composed from a
 * discounted self-report plus counts of things already on file, and every part
 * of it is on the row when it is opened. That is what the threshold is applied
 * to, and it is why the reasons are the point of this screen rather than a
 * disclosure under it.
 *
 * Two things this screen must keep visible, because both are more restrictive
 * than the threshold and neither moves with it: a safety-class field is decided
 * by a person whatever agrees with it, and a value only one source supports is
 * never written unattended.
 */

export function SuggestionsTab({
  report, suggestions, threshold, minSources, actor, setActor, busy, onApply,
}: {
  report: BatchReport;
  suggestions: Suggestion[];
  threshold: number;
  minSources: number;
  actor: string;
  setActor: (v: string) => void;
  busy: boolean;
  onApply: () => void;
}) {
  const autonomous = suggestions.filter((s) => s.route === "AUTONOMOUS");
  const human = suggestions.filter((s) => s.route === "HUMAN");
  const { gaps, candidates, held_safety, no_source } = report.fixable;

  return (
    <div className="flex flex-col gap-3">
      <Panel
        title="What could close the gaps, and what may not be closed this way"
        tone={candidates ? "accent" : undefined}
      >
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Kpi label="Gaps" value={gaps.length}
               sub="fields nobody sent a value for" />
          <Kpi label="A source is on file" value={candidates}
               sub="a passage could carry the value" />
          <Kpi label="Held — safety class" value={held_safety}
               sub="a person decides these, whatever agrees" />
          <Kpi label="Nothing to read it from" value={no_source}
               sub="the catalog and past decisions are all there is" />
        </div>

        <p className="mt-3 text-sm leading-relaxed text-muted">
          A proposal is written without anybody looking only if it clears{" "}
          <strong className="text-default">{Math.round(threshold * 100)}%</strong>{" "}
          <em>and</em> at least {minSources} independent sources agree with it.
          The second rule does not move with the threshold: one passage, one
          sibling or one past decision is a lead, and a lead is what the
          decision queue is for.
        </p>

        <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-subtle pt-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">Who is asking</span>
            <input
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="your name"
              className="rounded-md border border-subtle bg-raised px-2 py-1"
            />
          </label>
          <Button
            onClick={onApply}
            disabled={busy || !actor.trim()}
            icon={<IconSpark size={14} />}
          >
            {busy ? "Reading the sources…" : "Propose values for every gap"}
          </Button>
          <p className="w-full text-sm leading-relaxed text-muted">
            Every value that clears both rules is recorded as{" "}
            <em>inferred</em>, with the passage it was read from beside it. The
            rest arrive in Decisions with the evidence their score was composed
            from. <strong>Nothing is published</strong> — a product with no
            findings left is ready to launch, and launching it still needs a
            reviewer.
          </p>
        </div>
      </Panel>

      {suggestions.length === 0 ? (
        <Panel title="No proposal yet">
          <EmptyState art={<ArtQuietFeed />} title="Nothing has been proposed">
            Nobody has asked yet. Propose values above and every gap becomes
            either a recorded value, a question for a category manager, or a
            request to the supplier — with the reason attached either way.
          </EmptyState>
        </Panel>
      ) : (
        <>
          {autonomous.length > 0 && (
            <SuggestionTable
              title="Recorded without a reviewer"
              subtitle={`${autonomous.length} cleared ${Math.round(threshold * 100)}% with corroboration`}
              rows={autonomous}
              threshold={threshold}
            />
          )}
          <SuggestionTable
            title="Waiting on a category manager"
            subtitle={human.length
              ? `${human.length} to decide — the queue is in the next tab`
              : "nothing"}
            rows={human}
            threshold={threshold}
          />
        </>
      )}
    </div>
  );
}

function SuggestionTable({ title, subtitle, rows, threshold }: {
  title: string;
  subtitle?: string;
  rows: Suggestion[];
  threshold: number;
}) {
  const [open, setOpen] = useState<string | null>(null);
  if (rows.length === 0) {
    return (
      <Panel title={title} subtitle={subtitle}>
        <p className="text-sm text-muted">Nothing in this state.</p>
      </Panel>
    );
  }
  return (
    <Panel flush title={title} subtitle={subtitle}>
      <Table>
        <thead>
          <tr>
            <th />
            <th>Product</th>
            <th>Field</th>
            <th>Proposed</th>
            <th>Confidence</th>
            <th>From</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            /* Fragment rather than two sibling rows: the disclosure is part of
               the row it belongs to, and a keyed fragment is what keeps React
               from re-mounting an open one every time the list re-renders. */
            <Fragment key={row.id}>
              <tr
                onClick={() => setOpen(open === row.id ? null : row.id)}
                className="cursor-pointer transition-colors hover:bg-hover"
              >
                <td className="w-6 text-faint">
                  {open === row.id
                    ? <IconChevronDown size={13} />
                    : <IconChevronRight size={13} />}
                </td>
                <td><Code>{row.entity_id}</Code></td>
                <td>
                  <Code>{row.attribute_path}</Code>
                  {row.safety_class && (
                    <Badge tone="danger" className="ml-1.5">safety</Badge>
                  )}
                </td>
                <td><ValueChip value={row.value} /></td>
                <td>
                  <ConfidenceBar
                    value={row.confidence}
                    threshold={row.threshold ?? threshold}
                    safety={row.safety_class}
                  />
                </td>
                <td>
                  {row.citation?.doc_id ? (
                    <Tooltip content={row.citation.heading ?? row.citation.doc_id}>
                      <span><Code>{row.citation.doc_id}</Code></span>
                    </Tooltip>
                  ) : (
                    <span className="text-xs text-faint">
                      the catalog and past decisions
                    </span>
                  )}
                </td>
              </tr>
              {open === row.id && (
                <tr>
                  <td colSpan={6} className={cn("bg-sunken")}>
                    <div className="px-2 py-2">
                      <ReasonList reasons={row.reasons} />
                    </div>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </Table>
    </Panel>
  );
}
