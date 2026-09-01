/* The six one-click views.
 *
 * Each button carries the question it asks, not just a title, because that is
 * the difference between a finding and a chart: six rows of numbers with no
 * stated question is something a reader has to interpret, and interpreting is
 * where a wrong conclusion comes from.
 *
 * These are saved queries and there is no free-text box. The id is checked
 * against a catalogue on the server before anything runs, which is the same
 * closed-set-checked-by-name posture the evidence desk already takes - and it
 * means this component cannot be talked into running something.
 */

import { useEffect, useState } from "react";

import type { KgInsightResult, KgInsightSpec } from "../../api";
import { api, fmt } from "../../api";
import { ArtBroken } from "../../art/illustrations";
import {
  Badge, Button, EmptyState, Skeleton, Table, Td, Th, Tr, Tooltip, cn,
} from "../../ui";
import { DOMAIN_TEXT, DOMAIN_LABEL } from "./domains";

export function InsightBar() {
  const [specs, setSpecs] = useState<KgInsightSpec[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [result, setResult] = useState<KgInsightResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    api.kgInsights()
      .then((answer) => { if (live) setSpecs(answer.insights); })
      .catch((e) => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, []);

  const run = (id: string) => {
    // Clicking the open one closes it. A view that could only be opened would
    // leave a table on screen that the reader has finished with.
    if (chosen === id) { setChosen(null); setResult(null); return; }
    setChosen(id);
    setResult(null);
    setBusy(true);
    setError(null);
    api.kgQuery(id)
      .then(setResult)
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false));
  };

  if (error && !specs) {
    return (
      <EmptyState compact art={<ArtBroken />} title="Could not read the views">
        {error}
      </EmptyState>
    );
  }

  const spec = specs?.find((s) => s.id === chosen) ?? null;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-wrap gap-1.5">
        {!specs && Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-6 w-40" rounded="sm" />
        ))}
        {specs?.map((entry) => (
          <Tooltip key={entry.id} content={entry.question}>
            <Button
              size="xs"
              tone={chosen === entry.id ? "primary" : "default"}
              onClick={() => run(entry.id)}
            >
              {entry.title}
            </Button>
          </Tooltip>
        ))}
      </div>

      {spec && (
        <div className="rounded-sm border border-subtle bg-sunken">
          <div className="border-b border-subtle px-3 py-2">
            <p className="text-sm leading-relaxed text-fg">{spec.question}</p>
            <p className="mt-1 text-xs leading-relaxed text-muted">{spec.why}</p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              {spec.domains.map((domain) => (
                <span key={domain}
                      className={cn("text-2xs", DOMAIN_TEXT[domain])}>
                  {DOMAIN_LABEL[domain]}
                </span>
              ))}
              {result && (
                <span className="text-2xs text-faint">
                  · as of {fmt.date(result.as_of)} · {result.backend}
                </span>
              )}
              {result?.truncated && (
                <Badge tone="warn">first {result.rows.length}</Badge>
              )}
            </div>
          </div>

          <div className="max-h-[18rem] overflow-auto">
            {busy && (
              <div className="p-3">
                <Skeleton className="h-4 w-full" rounded="sm" />
                <Skeleton className="mt-1.5 h-4 w-5/6" rounded="sm" />
                <Skeleton className="mt-1.5 h-4 w-4/6" rounded="sm" />
              </div>
            )}
            {!busy && error && (
              <EmptyState compact art={<ArtBroken />} title="That view failed">
                {error}
              </EmptyState>
            )}
            {!busy && !error && result && result.rows.length === 0 && (
              <EmptyState compact title="Nothing to report">
                Nothing in the catalogue meets this condition right now. That is
                an answer, not a failure — but it is worth checking the seed
                data if you expected rows.
              </EmptyState>
            )}
            {!busy && !error && result && result.rows.length > 0 && (
              <Table>
                <thead>
                  <Tr>
                    {result.columns.map((column) => (
                      <Th key={column}>{humanise(column)}</Th>
                    ))}
                  </Tr>
                </thead>
                <tbody>
                  {result.rows.map((row, i) => (
                    <Tr key={i}>
                      {result.columns.map((column) => (
                        <Td key={column}>
                          {fmt.value(row[column] as never)}
                        </Td>
                      ))}
                    </Tr>
                  ))}
                </tbody>
              </Table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function humanise(key: string): string {
  return key.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}
