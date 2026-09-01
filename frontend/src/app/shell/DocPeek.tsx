import { Dialog } from "radix-ui";
import type { Citation } from "../../api";
import { IconClose, IconDoc } from "../../icons";
import { Badge, Button, Code, cn } from "../../ui";
import { useOpenDocument } from "./DocumentViewer";

/* Reference chunk viewer.
 *
 * Searching the reference library from the palette is only half an answer -
 * the reviewer asked a question and got a list of headings. This shows the
 * retrieved text, with the identifiers that make it citable in an approval
 * comment: a correction is approved against a standard, and the standard has
 * to be readable at the moment of approving.
 */

/** The kinds the index carries, in words. Content standards, per-channel
 *  rules, the source-precedence policy, and postmortems of corrections that
 *  went wrong before. The document id stays visible beside the badge - it is
 *  what a reviewer quotes. */
const DOC_TYPE_LABEL: Record<string, string> = {
  STANDARD: "standard",
  CHANNEL: "channel rules",
  POLICY: "policy",
  POSTMORTEM: "postmortem",
  COMMS: "message",
  // The four that arrived with launch readiness and never got a phrase here,
  // so they rendered as a lowercased enum next to five that read as English.
  REGULATION: "regulation",
  INTERNAL: "internal documentation",
  MARKET: "market context",
  RECORD: "held values",
};

export const docTypeLabel = (raw: string): string =>
  DOC_TYPE_LABEL[raw] ?? raw.toLowerCase().replace(/_/g, " ");

export function DocPeek({
  citation, onClose,
}: {
  citation: Citation | null;
  onClose: () => void;
}) {
  const openDocument = useOpenDocument();
  // RECORD passages are synthesised from the live catalog and COMMS are .eml
  // files under data/ - neither is a document in the library, so neither has
  // a whole to open.
  const followable = !!citation
    && !["RECORD", "COMMS"].includes(citation.doc_type);
  return (
    <Dialog.Root open={!!citation} onOpenChange={(o) => !o && onClose()}>
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
            "w-[min(640px,calc(100vw-24px))] max-h-[80vh] -translate-x-1/2",
            "-translate-y-1/2 overflow-hidden rounded-lg border border-strong",
            "bg-overlay shadow-e3 data-[state=open]:animate-scale-in"
          )}
        >
          {citation && (
            <>
              <div className="flex items-start gap-2.5 border-b border-subtle p-3.5">
                <IconDoc size={17} className="mt-0.5 shrink-0 text-faint" />
                <div className="min-w-0 flex-1">
                  <Dialog.Title className="truncate text-md font-semibold text-fg">
                    {citation.heading || citation.title}
                  </Dialog.Title>
                  <Dialog.Description className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-faint">
                    <Badge tone="neutral">{docTypeLabel(citation.doc_type)}</Badge>
                    <Code>{citation.doc_id}</Code>
                    {citation.version && <span>v{citation.version}</span>}
                    <span className="truncate">{citation.title}</span>
                    <span className="ml-auto font-mono">
                      {typeof citation.rerank_score === "number"
                        ? `relevance ${citation.rerank_score.toFixed(1)}/10`
                        : `score ${citation.score.toFixed(3)}`}
                    </span>
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

              <div className="max-h-[56vh] overflow-y-auto p-4">
                <p className="whitespace-pre-line text-base leading-relaxed text-fg">
                  {citation.excerpt}
                </p>
              </div>

              <div className={cn(
                "flex flex-wrap items-center gap-x-2 gap-y-1 border-t",
                "border-subtle px-3.5 py-2 text-xs text-faint"
              )}>
                <span>
                  Retrieved from <Code>{citation.source}</Code> — chunk{" "}
                  <Code>{citation.chunk_id}</Code>
                  {citation.effective && <> — in force from {citation.effective}</>}
                </span>
                {followable && (
                  <button
                    type="button"
                    onClick={() => {
                      onClose();
                      openDocument(citation.doc_id, citation.chunk_id);
                    }}
                    className={cn(
                      "ml-auto inline-flex items-center gap-1 rounded-xs px-1 py-0.5",
                      "text-xs text-accent-text transition-colors hover:bg-hover"
                    )}
                  >
                    <IconDoc size={11} />
                    Read the whole document
                  </button>
                )}
              </div>
            </>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
