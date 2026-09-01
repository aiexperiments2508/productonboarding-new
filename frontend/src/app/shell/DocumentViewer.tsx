import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState }
  from "react";
import type { ReactNode } from "react";
import { Dialog } from "radix-ui";
import { api } from "../../api";
import type { CorpusDocumentDetail, SopDocument } from "../../api";
import { IconClose, IconDoc } from "../../icons";
import { Badge, Button, Code, Skeleton, cn } from "../../ui";
import { docTypeLabel } from "./DocPeek";

/* The whole document, opened at the passage that was cited.
 *
 * `DocPeek` shows the forty-five words retrieval scored. That is the right
 * default - it is what makes following a citation cheap - but it is not enough
 * to approve against. A reviewer reading "the listing is withheld" needs the
 * clause before it that says when, and the one after that says by whom, and
 * neither is in the excerpt.
 *
 * Two sources, in order, and the order is the point:
 *
 *   `/api/sop/{id}` is the index, so its chunks are exactly the passages the
 *   citation was scored against - the cited one can be highlighted because it
 *   is the same object.
 *
 *   `/api/corpus/{id}` is the disk, and answers for documents the index does
 *   not hold: one that has been retired, or one just written and not yet
 *   rebuilt. A citation on a six-month-old approval must stay readable against
 *   the rule that was in force when it was made, and that rule may since have
 *   been withdrawn - which is exactly when a reader most needs to see it.
 */

/* Opening a document from anywhere.
 *
 * A context rather than a prop threaded down, because the places that cite a
 * document are scattered - the approval diff, the fabric rail, the scenario
 * comparison, the answer panel - and none of them is on a path that would
 * naturally carry a callback from the shell. `useToast` solves the same shape
 * the same way, so this is the house pattern rather than a new one.
 *
 * The default is a no-op, so a component rendered outside the provider (a
 * test, a storybook) renders an inert control instead of throwing. */
const OpenDocument = createContext<(docId: string, chunkId?: string) => void>(
  () => undefined);

export const useOpenDocument = () => useContext(OpenDocument);

export function DocumentViewerProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<DocumentTarget | null>(null);
  const open = useCallback(
    (docId: string, chunkId?: string) => setTarget({ docId, chunkId }), []);
  const value = useMemo(() => open, [open]);

  return (
    <OpenDocument.Provider value={value}>
      {children}
      <DocumentViewer target={target} onClose={() => setTarget(null)} />
    </OpenDocument.Provider>
  );
}

export interface DocumentTarget {
  docId: string;
  /** The chunk to land on, when the reader arrived from a citation. */
  chunkId?: string;
}

type Loaded =
  | { from: "index"; doc: SopDocument }
  | { from: "disk"; doc: CorpusDocumentDetail };

export function DocumentViewer({
  target, onClose,
}: {
  target: DocumentTarget | null;
  onClose: () => void;
}) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const cited = useRef<HTMLDivElement | null>(null);

  const docId = target?.docId ?? "";

  useEffect(() => {
    if (!docId) return;
    let live = true;
    setLoaded(null);
    setError(null);

    api.sopDocument(docId)
      .then((doc) => { if (live) setLoaded({ from: "index", doc }); })
      .catch(() =>
        // Not in the index. Retired, or written and not yet rebuilt - either
        // way the file is still there and still the answer.
        api.corpusDocument(docId)
          .then((doc) => { if (live) setLoaded({ from: "disk", doc }); })
          .catch((e) => { if (live) setError(String(e)); }))
      .catch(() => undefined);

    return () => { live = false; };
  }, [docId]);

  // After the content lands, put the cited passage on screen. Opening a
  // sixty-section regulation at the top and leaving the reader to find the
  // clause is not following a citation, it is being handed a document.
  useEffect(() => {
    if (!loaded || !cited.current) return;
    cited.current.scrollIntoView({ block: "center" });
  }, [loaded]);

  const title = loaded
    ? (loaded.from === "index" ? loaded.doc.title : loaded.doc.title)
    : docId;
  const docType = loaded
    ? (loaded.from === "index" ? loaded.doc.doc_type : loaded.doc.type)
    : "";
  const retired = loaded?.from === "disk" && loaded.doc.status === "RETIRED";

  return (
    <Dialog.Root open={!!target} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn(
            "fixed inset-0 z-[var(--z-dialog)] bg-scrim",
            "data-[state=open]:animate-fade-in"
          )}
        />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-[var(--z-dialog)]",
            "w-[min(860px,calc(100vw-24px))] max-h-[86vh] -translate-x-1/2",
            "-translate-y-1/2 overflow-hidden rounded-lg border border-strong",
            "bg-overlay shadow-e3 data-[state=open]:animate-scale-in"
          )}
        >
          <div className="flex items-start gap-2.5 border-b border-subtle p-3.5">
            <IconDoc size={17} className="mt-0.5 shrink-0 text-faint" />
            <div className="min-w-0 flex-1">
              <Dialog.Title className="truncate text-md font-semibold text-fg">
                {title}
              </Dialog.Title>
              <Dialog.Description
                className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-faint"
              >
                {docType && <Badge tone="neutral">{docTypeLabel(docType)}</Badge>}
                <Code>{docId}</Code>
                {retired && <Badge tone="warn">retired</Badge>}
                {loaded?.from === "disk" && (
                  <>
                    {loaded.doc.owner && <span>{loaded.doc.owner}</span>}
                    {loaded.doc.version && <span>v{loaded.doc.version}</span>}
                    {loaded.doc.effective && (
                      <span>effective {loaded.doc.effective}</span>
                    )}
                  </>
                )}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button
                tone="ghost"
                size="xs"
                iconOnly
                aria-label="Close"
                icon={<IconClose size={14} />}
              />
            </Dialog.Close>
          </div>

          {retired && (
            <p className={cn(
              "border-b border-subtle bg-warn-soft px-3.5 py-2",
              "text-xs leading-relaxed text-warn-text"
            )}>
              This document has been withdrawn and no longer answers a search.
              It is shown because a decision made while it was in force has to
              stay readable against it.
            </p>
          )}

          <div className="max-h-[68vh] overflow-y-auto p-4">
            {error && (
              <p className="text-sm leading-relaxed text-danger-text">
                {docId} could not be opened. {error}
              </p>
            )}
            {!loaded && !error && (
              <div className="flex flex-col gap-2">
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-24 w-full" />
                <Skeleton className="h-24 w-full" />
              </div>
            )}

            {loaded?.from === "index" && loaded.doc.chunks.map((chunk) => {
              const isCited = chunk.id === target?.chunkId;
              return (
                <div
                  key={chunk.id}
                  ref={isCited ? cited : undefined}
                  className={cn(
                    "mb-3 rounded-r-sm px-3 py-2",
                    isCited
                      ? "border-l-2 border-accent bg-accent-soft"
                      : "border-l-2 border-transparent"
                  )}
                >
                  <div className="mb-1 flex items-center gap-1.5">
                    <span className="font-mono text-2xs text-faint">
                      {chunk.id}
                    </span>
                    {String(chunk.metadata?.heading ?? "") && (
                      <span className="truncate text-xs text-muted">
                        {String(chunk.metadata.heading)}
                      </span>
                    )}
                    {isCited && <Badge tone="accent">cited</Badge>}
                  </div>
                  <p className="whitespace-pre-line text-base leading-relaxed text-fg">
                    {chunk.text}
                  </p>
                </div>
              );
            })}

            {loaded?.from === "disk" && (
              <p className="whitespace-pre-line text-base leading-relaxed text-fg">
                {loaded.doc.body}
              </p>
            )}
          </div>

          <div className="border-t border-subtle px-3.5 py-2 text-xs text-faint">
            {loaded?.from === "index" && (
              <>
                {loaded.doc.chunks.length} passage
                {loaded.doc.chunks.length === 1 ? "" : "s"}, as retrieval holds
                them
                {target?.chunkId && <> — cited passage <Code>{target.chunkId}</Code></>}
              </>
            )}
            {loaded?.from === "disk" && (
              <>Read from <Code>{loaded.doc.path}</Code> — not in the index</>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
