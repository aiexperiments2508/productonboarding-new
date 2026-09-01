import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { CorpusDocument, CorpusOverview, CorpusReference } from "../../api";
import { IconAlert, IconDoc, IconRefresh } from "../../icons";
import {
  Badge, Button, Code, Dot, EmptyState, Panel, SegmentedControl, Skeleton,
  Table, Td, Th, Tooltip, Tr, cn, useToast,
} from "../../ui";
import { DocumentEditor } from "./DocumentEditor";
import type { EditorMode } from "./DocumentEditor";

/* The policy library.
 *
 * Everything the factory is answerable to, in one place that can also change
 * it: the market authority's mandates, the retailer's own policy, the internal
 * documentation, the content standards, the channel rules and the postmortems.
 * Until now these were 29 markdown files you needed a checkout to touch.
 *
 * Three things this panel has to say out loud, because a plain table would
 * imply the opposite of each.
 *
 *   Withdrawing is not deleting. Retiring stops a document answering searches
 *   and leaves it on disk, because a decision taken while it was in force has
 *   to stay readable against it. Destroying it is a second, separate act.
 *
 *   Removing a document does not fail loudly. Three readiness checks pass
 *   everything when their shelf comes back empty and report the assessment as
 *   complete - a fail-open that reads as a clean run. So what would notice a
 *   document leaving is shown *before* it leaves, not after.
 *
 *   Saving rebuilds the lexical index, not the embeddings. The document is
 *   findable by identifier immediately and by paraphrase only after a
 *   re-embed, and the banner says so rather than letting the difference be
 *   discovered by a search that quietly returns nothing.
 */

const TYPE_TONE: Record<string, "neutral" | "danger" | "warn" | "info" | "accent"> = {
  REGULATION: "danger",
  POLICY: "accent",
  INTERNAL: "warn",
  STANDARD: "info",
  CHANNEL: "neutral",
  POSTMORTEM: "neutral",
  MARKET: "neutral",
};

/** Has this document commenced by the date retrieval is answering about?
 *
 *  Mirrors `retrieve.in_force`: no date means always, and a date that will not
 *  parse means always - a typo should cost a document its commencement date,
 *  not its presence. Shown here because the effective date stopped being
 *  decoration the moment retrieval started acting on it, and a row that is
 *  invisible to search has to say so on the screen that lists it. */
function commenced(doc: CorpusDocument, asOf?: string): boolean {
  if (!doc.effective || !asOf) return true;
  const when = Date.parse(doc.effective);
  const now = Date.parse(asOf);
  return Number.isNaN(when) || Number.isNaN(now) || when <= now;
}

export function PolicyLibraryPanel() {
  const toast = useToast();
  const [overview, setOverview] = useState<CorpusOverview | null>(null);
  const [actor, setActor] = useState("");
  const [filter, setFilter] = useState<string>("");
  const [query, setQuery] = useState("");
  const [showRetired, setShowRetired] = useState(true);
  const [editing, setEditing] = useState<EditorMode | null>(null);
  const [armed, setArmed] = useState<string | null>(null);
  const [working, setWorking] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.corpus().then(setOverview).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);

  // Arming is per row and per action, and it resets whenever the list moves
  // under it - an armed "delete" that survives a refresh is a button pointing
  // at whatever ended up in that position.
  useEffect(() => { setArmed(null); }, [overview]);

  async function act(key: string, label: string, run: () => Promise<unknown>) {
    setWorking(key);
    try {
      await run();
      toast.notify(label);
      refresh();
    } catch (e) {
      toast.error("That did not happen", String(e));
    } finally {
      setWorking(null);
      setArmed(null);
    }
  }

  function retire(doc: CorpusDocument, acknowledged: boolean) {
    return act(`${doc.doc_id}:retire`, `${doc.doc_id} withdrawn from retrieval`,
               () => api.retireCorpusDocument(doc.doc_id, {
                 actor: actor.trim(), acknowledge_references: acknowledged,
               }));
  }

  if (!overview) {
    return (
      <Panel title="Policy library">
        <div className="flex flex-col gap-2">
          <Skeleton className="h-4 w-2/5" />
          <Skeleton className="h-40 w-full" />
        </div>
      </Panel>
    );
  }

  const documents = overview.documents.filter((d) => {
    if (!showRetired && d.status === "RETIRED") return false;
    if (filter && d.type !== filter) return false;
    if (!query.trim()) return true;
    const q = query.trim().toLowerCase();
    return [d.doc_id, d.title, d.owner, ...d.tags]
      .some((v) => String(v).toLowerCase().includes(q));
  });

  const active = overview.documents.filter((d) => d.status === "ACTIVE").length;
  const retired = overview.documents.length - active;
  const orphans = overview.documents.filter(
    (d) => d.status === "ACTIVE" && d.chunks === 0);
  const pending = overview.documents.filter(
    (d) => d.status === "ACTIVE" && !commenced(d, overview.index.as_of));
  const named = !!actor.trim();

  return (
    <>
      <Panel
        title="Policy library"
        subtitle={`${active} in force, ${retired} retired, `
                  + `${overview.index.chunks} chunks indexed`}
        actions={
          <>
            <Button size="xs" disabled={!named}
                    onClick={() => setEditing({ kind: "create" })}>
              New document
            </Button>
            <Button
              size="xs"
              icon={<IconRefresh size={12} />}
              loading={working === "reembed"}
              onClick={() => act("reembed", "the corpus was re-embedded",
                                 () => api.reindex(true))}
            >
              Re-embed
            </Button>
          </>
        }
      >
        <div className="flex flex-col gap-3">
          <p className="text-sm leading-relaxed text-muted">
            The documents retrieval reads and the readiness checks are answerable
            to. Editing one changes what the factory will cite the moment it is
            saved — <Code>{overview.root}</Code> is the corpus on disk, and it is
            committed content, not generated data.
          </p>

          <label className="flex max-w-xs flex-col gap-1 text-sm">
            <span className="text-muted">Who is changing it</span>
            <input
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="your name"
              className={cn(
                "rounded-md border border-subtle bg-raised px-2 py-1",
                "focus:outline-none focus:ring-2 focus:ring-focus"
              )}
            />
          </label>

          {overview.index.vectors_stale && (
            <p className={cn("rounded-sm border border-warn-border bg-warn-soft",
                             "px-2.5 py-2 text-xs leading-relaxed text-warn-text")}>
              <IconAlert size={12} className="mr-1 inline align-[-1px]" />
              The embeddings no longer match the corpus, so search is running on
              identifiers alone — it will find <Code>VAR-01B</Code> and miss
              “can we still change the catalogue”. Re-embed to bring paraphrase
              search back.
            </p>
          )}
          {overview.index.vectors && overview.index.vectors_verified === false && (
            <p className="text-xs leading-relaxed text-faint">
              The embedding matrix predates the fingerprint check, so it is in
              use on trust rather than on proof. A re-embed settles it.
            </p>
          )}
          {pending.length > 0 && (
            <p className="text-xs leading-relaxed text-faint">
              {pending.map((d) => d.doc_id).join(", ")}{" "}
              {pending.length === 1 ? "has" : "have"} not commenced as of{" "}
              <Code>{overview.index.as_of}</Code>, so{" "}
              {pending.length === 1 ? "it is" : "they are"} on file and out of
              retrieval until then. A rule taking effect later is not the answer
              to what may be published now.
            </p>
          )}
          {orphans.length > 0 && (
            <p className={cn("rounded-sm border border-warn-border bg-warn-soft",
                             "px-2.5 py-2 text-xs leading-relaxed text-warn-text")}>
              {orphans.map((d) => d.doc_id).join(", ")} produced no chunks and
              cannot be retrieved at all. Usually too short — sections under 40
              words are merged, and a document under that in total yields
              nothing.
            </p>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <SegmentedControl
              ariaLabel="Document type"
              value={filter}
              onChange={setFilter}
              options={[{ value: "", label: "All" },
                        ...overview.types.map((t) => ({
                          value: t,
                          label: t.slice(0, 3),
                          title: t,
                        }))]}
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="filter by id, title, owner or tag"
              className={cn(
                "h-[var(--control-h-sm)] min-w-[16rem] flex-1 rounded-sm border",
                "border-line bg-canvas px-2 text-base",
                "focus:outline-none focus:ring-2 focus:ring-focus"
              )}
            />
            <label className="flex items-center gap-1.5 text-xs text-muted">
              <input type="checkbox" checked={showRetired}
                     onChange={(e) => setShowRetired(e.target.checked)} />
              show retired
            </label>
          </div>
        </div>
      </Panel>

      <Panel title="Documents" subtitle={`${documents.length} shown`} flush>
        {documents.length === 0 ? (
          <EmptyState
            art={<IconDoc size={20} />}
            title="Nothing matches"
            compact
          >
            Widen the type filter or clear the search.
          </EmptyState>
        ) : (
          <Table scroll>
            <thead>
              <tr>
                <Th>Document</Th>
                <Th>Type</Th>
                <Th>Title</Th>
                <Th>Owner</Th>
                <Th>Version</Th>
                <Th>Effective</Th>
                <Th num>Chunks</Th>
                <Th>In index</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => {
                const retiredRow = doc.status === "RETIRED";
                const key = `${doc.doc_id}:`;
                return (
                  <Tr key={doc.doc_id}>
                    <Td><Code>{doc.doc_id}</Code></Td>
                    <Td>
                      <Badge tone={TYPE_TONE[doc.type] ?? "neutral"}>
                        {doc.type.toLowerCase()}
                      </Badge>
                    </Td>
                    <Td className="max-w-[22rem]">
                      <span className={cn("block truncate",
                                          retiredRow && "text-faint line-through")}>
                        {doc.title}
                      </span>
                    </Td>
                    <Td className="text-muted">{doc.owner || "—"}</Td>
                    <Td className="font-mono text-sm">{doc.version || "—"}</Td>
                    <Td className="font-mono text-sm">
                      {doc.effective || "—"}
                      {!retiredRow && !commenced(doc, overview.index.as_of) && (
                        <Tooltip content={
                          `Not in force until ${doc.effective}. Retrieval `
                          + `answers as of ${overview.index.as_of}, so this `
                          + "document is not cited yet."
                        }>
                          <span className="ml-1 align-middle">
                            <Badge tone="info">pending</Badge>
                          </span>
                        </Tooltip>
                      )}
                    </Td>
                    <Td num>{doc.chunks}</Td>
                    <Td>
                      {retiredRow ? (
                        <Badge tone="warn">retired</Badge>
                      ) : (
                        <Tooltip content={doc.indexed
                          ? "answering searches now"
                          : "on disk, but producing no chunks"}>
                          <span><Dot tone={doc.indexed ? "ok" : "warn"} /></span>
                        </Tooltip>
                      )}
                    </Td>
                    <Td>
                      <div className="flex flex-wrap items-center justify-end gap-1">
                        <Button size="xs" disabled={!named}
                                onClick={() => setEditing({ kind: "edit",
                                                            docId: doc.doc_id })}>
                          Edit
                        </Button>

                        {retiredRow ? (
                          <>
                            <Button
                              size="xs"
                              disabled={!named}
                              loading={working === key + "restore"}
                              onClick={() => act(
                                key + "restore",
                                `${doc.doc_id} is back in force`,
                                () => api.restoreCorpusDocument(doc.doc_id,
                                                                { actor: actor.trim() }))}
                            >
                              Restore
                            </Button>
                            <Button
                              size="xs"
                              tone="danger"
                              disabled={!named}
                              loading={working === key + "delete"}
                              onClick={() => {
                                if (armed !== key + "delete") {
                                  setArmed(key + "delete");
                                  return;
                                }
                                act(key + "delete",
                                    `${doc.doc_id} was destroyed — its text is in `
                                    + "the audit ledger",
                                    () => api.deleteCorpusDocument(doc.doc_id, {
                                      actor: actor.trim(),
                                      confirm_id: doc.doc_id,
                                      acknowledge_references: true,
                                    }));
                              }}
                            >
                              {armed === key + "delete" ? "Yes — destroy it" : "Delete"}
                            </Button>
                          </>
                        ) : (
                          <RetireButton
                            doc={doc}
                            disabled={!named}
                            loading={working === key + "retire"}
                            armed={armed === key + "retire"}
                            onArm={() => setArmed(key + "retire")}
                            onRetire={(ack) => retire(doc, ack)}
                          />
                        )}
                      </div>
                    </Td>
                  </Tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Panel>

      {editing && (
        <DocumentEditor
          mode={editing}
          overview={overview}
          actor={actor}
          onClose={() => setEditing(null)}
          onSaved={refresh}
        />
      )}
    </>
  );
}

/* Retiring, armed, with the consequences fetched before the second click.
 *
 * The list of what would notice is asked for at arming time rather than held
 * on every row: it is a scan of the Python tree per document, and doing 29 of
 * them to render a table nobody has interacted with yet is work spent on a
 * question nobody asked. */
function RetireButton({
  doc, disabled, loading, armed, onArm, onRetire,
}: {
  doc: CorpusDocument;
  disabled: boolean;
  loading: boolean;
  armed: boolean;
  onArm: () => void;
  onRetire: (acknowledged: boolean) => void;
}) {
  const [blocking, setBlocking] = useState<CorpusReference[] | null>(null);

  useEffect(() => {
    if (!armed) { setBlocking(null); return; }
    api.corpusDocument(doc.doc_id)
      .then((full) => setBlocking(full.references))
      .catch(() => setBlocking([]));
  }, [armed, doc.doc_id]);

  if (!armed) {
    return (
      <Button size="xs" tone="danger" disabled={disabled} onClick={onArm}>
        Retire
      </Button>
    );
  }

  return (
    <div className="flex flex-col items-end gap-1">
      {blocking === null ? (
        <span className="text-2xs text-faint">checking what would notice…</span>
      ) : blocking.length === 0 ? (
        <span className="text-2xs text-faint">nothing else names it</span>
      ) : (
        <Tooltip content={
          <span className="block max-w-[26rem]">
            {blocking.slice(0, 6).map((b) => (
              <span key={b.where} className="mt-0.5 block">
                <span className="font-mono text-2xs">{b.where}</span> — {b.detail}
              </span>
            ))}
            {blocking.length > 6 && (
              <span className="mt-0.5 block">
                and {blocking.length - 6} more
              </span>
            )}
          </span>
        }>
          <span className="text-2xs text-warn-text">
            <IconAlert size={10} className="mr-0.5 inline align-[-1px]" />
            {blocking.length} would notice
          </span>
        </Tooltip>
      )}
      <Button size="xs" tone="danger" loading={loading}
              onClick={() => onRetire(true)}>
        Yes — withdraw it
      </Button>
    </div>
  );
}
