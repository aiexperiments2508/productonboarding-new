import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { Preview, ProductHit, Readiness } from "../api";
import { IconCheck, IconSearch } from "../icons";
import {
  Badge, Button, Code, Panel, Skeleton, Tooltip, cn, useToast,
} from "../ui";
import { PageHeader } from "../app/shell/PageHeader";

/* Product 360.
 *
 * The rest of this system reasons about corrections to things already
 * published. This is the question that comes first and had no home: is this
 * product fit to publish at all.
 *
 * Three things on this screen are deliberate and worth reading the code for.
 *
 * **There is no readiness score.** A product with three open findings is not
 * seventy per cent ready - it is not ready, and the three findings are the
 * thing somebody acts on. A number would invite a threshold and a threshold
 * would invite launching at ninety.
 *
 * **Every finding names a system.** "The data is incomplete" is not something
 * anybody can act on; "the imaging system never sent an ingredient panel" is,
 * because it says who has to fix it. That is what the estate is for.
 *
 * **The preview refuses rather than warns.** A page that renders a blocked
 * product with a banner across the top is a page somebody screenshots.
 */

const VERDICT_TONE: Record<string, "ok" | "warn" | "danger" | "neutral"> = {
  READY_TO_LAUNCH: "ok",
  RETURN_TO_SOURCE: "warn",
  BLOCKED: "danger",
};

const VERDICT_WORDS: Record<string, string> = {
  READY_TO_LAUNCH: "ready to launch",
  RETURN_TO_SOURCE: "back to source",
  BLOCKED: "blocked",
};

function verdictLabel(verdict?: string): string {
  return verdict ? VERDICT_WORDS[verdict] ?? verdict.toLowerCase() : "unassessed";
}

export function Product360() {
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<ProductHit[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  // Who is looking. The same thing the approval gate asks for and no more -
  // neither is authenticated, and inventing a login here would protect
  // unpublished copy more carefully than the decision to publish it. What it
  // buys is a name in the ledger against "who saw this before it launched".
  const [actor, setActor] = useState("reviewer");

  const search = useCallback(async (term: string) => {
    try {
      const answer = await api.products(term, 50);
      setHits(answer.results);
      // Selecting the first result keeps the detail pane populated as somebody
      // types. An empty right-hand side beside a full left-hand one reads as a
      // page that failed rather than one waiting.
      setSelected((current) =>
        current && answer.results.some((r) => r.entity_id === current)
          ? current
          : answer.results[0]?.entity_id ?? null);
    } catch (e) {
      toast.error("Could not search products", String(e));
    }
  }, [toast]);

  useEffect(() => { search(query); }, [search, query]);

  useEffect(() => {
    if (!selected) { setReadiness(null); setPreview(null); return; }
    let cancelled = false;
    setBusy(true);
    setPreview(null);
    // The full assessment, model-backed. The list view runs the deterministic
    // half only; asking for the reading checks on twenty rows nobody has
    // clicked into would be sixty model calls to render a page.
    api.readiness(selected, true)
      .then((r) => { if (!cancelled) setReadiness(r); })
      .catch(() => { if (!cancelled) setReadiness(null); })
      .finally(() => { if (!cancelled) setBusy(false); });
    return () => { cancelled = true; };
  }, [selected]);

  const openPreview = useCallback(async () => {
    if (!selected) return;
    if (!actor.trim()) {
      toast.error("A name is required",
                  "Unpublished content is viewed under a name, the same as an "
                  + "approval decision is taken under one.");
      return;
    }
    try {
      setPreview(await api.preview(selected, actor.trim(), true));
    } catch (e) {
      toast.error("Could not build the preview", String(e));
    }
  }, [actor, selected, toast]);

  const counts = useMemo(() => {
    const tally: Record<string, number> = {};
    for (const hit of hits ?? []) {
      const key = hit.verdict ?? "unassessed";
      tally[key] = (tally[key] ?? 0) + 1;
    }
    return tally;
  }, [hits]);

  return (
    <>
      <PageHeader
        section="product360"
        actions={
          <div className="flex items-center gap-2">
            {Object.entries(counts).map(([verdict, n]) => (
              <Badge key={verdict} tone={VERDICT_TONE[verdict] ?? "neutral"} dot>
                {n} {verdictLabel(verdict)}
              </Badge>
            ))}
          </div>
        }
      />

      <div className="grid gap-3 xl:grid-cols-[minmax(320px,1fr)_minmax(0,2fr)]">
        <Panel
          title="Products"
          subtitle="Search by SKU, identifier or name"
          flush
        >
          <div className="border-b border-subtle p-2">
            <label className="flex items-center gap-2 rounded-sm border border-line bg-canvas px-2">
              <IconSearch size={13} className="shrink-0 text-faint" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="AER-300-MAX, VAR-01B, or purifier"
                aria-label="Search products"
                className={cn(
                  "min-w-0 flex-1 bg-transparent py-1.5 font-mono text-xs",
                  "text-fg placeholder:text-faint focus:outline-none",
                )}
              />
            </label>
          </div>

          {hits === null ? (
            <div className="p-3"><Skeleton className="h-64" /></div>
          ) : hits.length === 0 ? (
            <p className="p-4 text-sm text-muted">
              Nothing matches <Code>{query}</Code>.
            </p>
          ) : (
            <ul className="sc-stagger flex flex-col">
              {hits.map((hit, i) => (
                <li key={hit.entity_id} style={{ ["--i" as string]: i }}>
                  <button
                    onClick={() => setSelected(hit.entity_id)}
                    className={cn(
                      "flex w-full items-center gap-2 border-b border-subtle",
                      "px-3 py-2 text-left transition-colors",
                      selected === hit.entity_id
                        ? "bg-accent-soft"
                        : "hover:bg-hover",
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-fg">
                        {hit.name}
                      </span>
                      <span className="block truncate font-mono text-2xs text-faint">
                        {hit.sku} · {hit.entity_id}
                      </span>
                    </span>
                    <Badge tone={VERDICT_TONE[hit.verdict ?? ""] ?? "neutral"}>
                      {hit.findings ? `${hit.findings}` : "clear"}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <div className="flex min-w-0 flex-col gap-3">
          <Panel
            title={readiness?.record?.name ?? "Readiness"}
            subtitle={
              readiness
                ? `${readiness.findings.length} finding(s) · ${verdictLabel(readiness.verdict)}`
                : "Select a product"
            }
            actions={
              readiness?.ready ? (
                <div className="flex items-center gap-1.5">
                  <input
                    value={actor}
                    onChange={(e) => setActor(e.target.value)}
                    aria-label="Who is viewing this unpublished content"
                    placeholder="your name"
                    className={cn(
                      "w-28 rounded-sm border border-line bg-canvas px-2 py-1",
                      "text-xs text-fg placeholder:text-faint",
                      "focus:outline-none focus:ring-2 focus:ring-focus",
                    )}
                  />
                  <Button size="sm" tone="primary" onClick={openPreview}>
                    Open staging page
                  </Button>
                </div>
              ) : undefined
            }
          >
            {busy || !readiness ? (
              <Skeleton className="h-40" />
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={VERDICT_TONE[readiness.verdict] ?? "neutral"} dot>
                    {verdictLabel(readiness.verdict)}
                  </Badge>
                  <Code>{readiness.record?.sku}</Code>
                  {readiness.record?.product.regulated && (
                    <Badge tone="warn">regulated</Badge>
                  )}
                </div>

                {/* An assessment that could not reach a model has found fewer
                    things. Saying so is the whole point - reporting a narrower
                    result as a clean one is the most dangerous thing this
                    surface could do. */}
                {readiness.caveat && (
                  <p className="mt-2 rounded-sm border border-warn-border bg-warn-soft px-2 py-1.5 text-xs text-warn-text">
                    {readiness.caveat}
                  </p>
                )}

                {readiness.findings.length === 0 ? (
                  <p className="mt-3 flex items-center gap-2 text-sm text-muted">
                    <IconCheck size={14} className="text-ok-text" />
                    Nothing open. Every applicable attribute is held, the
                    imagery this category needs is present, and no claim
                    outruns the record.
                  </p>
                ) : (
                  <ul className="sc-stagger mt-3 flex flex-col gap-1.5">
                    {readiness.findings.map((finding, i) => (
                      <li
                        key={`${finding.check}-${finding.subject}`}
                        style={{ ["--i" as string]: i }}
                        className={cn(
                          "rounded-sm border-l-2 bg-sunken px-2 py-1.5",
                          finding.severity === "BLOCKING"
                            ? "border-danger"
                            : "border-warn",
                        )}
                      >
                        <div className="flex flex-wrap items-baseline gap-2">
                          <Code>{finding.check}</Code>
                          <span className="font-mono text-2xs text-faint">
                            {finding.subject}
                          </span>
                          {/* Who has to fix it. A return that names nobody is
                              not a return. */}
                          {finding.system && (
                            <Badge tone="info">{finding.system}</Badge>
                          )}
                          <Tooltip content="The rule or passage this rests on">
                            <span className="ml-auto shrink-0 font-mono text-2xs text-faint">
                              {finding.basis}
                            </span>
                          </Tooltip>
                        </div>
                        <p className="mt-0.5 text-xs text-muted">
                          {finding.detail}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </Panel>

          {readiness?.record && (
            <Panel
              title="The record"
              subtitle="What the estate has said, and who said it"
              flush
            >
              <table className="w-full text-xs">
                <tbody>
                  {readiness.record.attributes.map((row) => (
                    <tr key={row.path} className="border-b border-subtle">
                      <td className="px-3 py-1.5 text-muted">{row.label}</td>
                      <td className="px-3 py-1.5 font-mono text-fg">
                        {String(row.value)}
                        {row.unit ? ` ${row.unit}` : ""}
                      </td>
                      <td className="px-3 py-1.5">
                        {row.system ? (
                          <Badge tone="neutral">{row.system}</Badge>
                        ) : (
                          <span className="text-faint">carrier unknown</span>
                        )}
                      </td>
                      <td className="px-3 py-1.5 font-mono text-2xs text-faint">
                        {row.source ?? ""}
                      </td>
                      <td className="px-3 py-1.5">
                        {/* A disagreement precedence settled is settled, not
                            absent. Hiding the loser would make the record look
                            like everybody agreed. */}
                        {row.superseded.length > 0 && (
                          <Tooltip
                            content={row.superseded
                              .map((s) => `${s.system ?? "unknown"} said ${String(s.value)}`)
                              .join("; ")}
                          >
                            <span>
                              <Badge tone="warn">
                                {row.superseded.length} superseded
                              </Badge>
                            </span>
                          </Tooltip>
                        )}
                        {row.defects.map((d) => (
                          <Badge key={d} tone="danger">{d}</Badge>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}

          {preview && <StagingPage preview={preview} />}
        </div>
      </div>
    </>
  );
}

/* The staging page.
 *
 * What the listing would look like, for a record that passed. Refusals are the
 * whole response rather than a banner, because a page that renders a blocked
 * product is a page somebody screenshots. */
function StagingPage({ preview }: { preview: Preview }) {
  if (!preview.rendered) {
    return (
      <Panel title="Staging page" subtitle="Not available">
        <p className="text-sm text-muted">
          {preview.reason}. This product is{" "}
          <strong className="text-warn-text">
            {verdictLabel(preview.verdict)}
          </strong>{" "}
          with {preview.findings?.length ?? 0} open finding(s).
        </p>
      </Panel>
    );
  }

  const differentiator = preview.differentiator;
  return (
    <Panel
      title="Staging page"
      subtitle="What the listing would look like"
      actions={<Badge tone="ok" dot>ready</Badge>}
    >
      <article className="flex flex-col gap-3">
        <header>
          <h3 className="text-lg font-semibold text-fg">{preview.title}</h3>
          <p className="font-mono text-2xs text-faint">
            {preview.sku} · {preview.category}
          </p>
        </header>

        {/* The differentiator, and its grounds shown beside it rather than
            hidden. A claim a reviewer cannot trace is a claim they cannot
            approve. */}
        {differentiator && (
          <div className="rounded-md border border-accent-border bg-accent-soft p-3">
            <p className="text-2xs uppercase tracking-caps text-accent-text">
              why somebody buys this
            </p>
            <p className="mt-1 text-sm text-fg">{differentiator.text}</p>
            <p className="mt-2 flex flex-wrap items-center gap-1.5 text-2xs text-muted">
              <span>grounded in</span>
              {differentiator.attributes.map((a) => (
                <Code key={a}>{a}</Code>
              ))}
              <span>and</span>
              <Code>{differentiator.source}</Code>
              {!differentiator.written_by_model && (
                <Badge tone="neutral">{differentiator.note}</Badge>
              )}
            </p>
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {(preview.media ?? []).map((m) => (
            <span
              key={m.role}
              className="rounded-sm border border-subtle bg-sunken px-2 py-1 text-2xs text-muted"
            >
              {m.role.toLowerCase().replace("_", " ")}
            </span>
          ))}
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          {(preview.specification ?? []).map((row) => (
            <div key={row.path} className="contents">
              <dt className="text-muted">{row.label}</dt>
              <dd className="font-mono text-fg">
                {String(row.value)}{row.unit ? ` ${row.unit}` : ""}
              </dd>
            </div>
          ))}
        </dl>

        {(preview.claims ?? []).length > 0 && (
          <p className="flex flex-wrap items-center gap-1.5">
            {(preview.claims ?? []).map((c) => (
              <Badge key={c} tone="ok">{c}</Badge>
            ))}
          </p>
        )}
      </article>
    </Panel>
  );
}
