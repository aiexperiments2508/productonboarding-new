import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { Dialog } from "radix-ui";
import { api, toBase64 } from "../../api";
import type { CorpusDocumentDetail, CorpusOverview, ExtractResult } from "../../api";
import { IconAlert, IconClose, IconDoc } from "../../icons";
import { Badge, Button, Code, Select, cn, useToast } from "../../ui";

/* Authoring one document.
 *
 * The id and the type are fixed once a document exists, and that is a rule
 * rather than a simplification. The id is what every stored citation names and
 * what `sc/graph/evidence.py` hard-codes; the type is what decides which
 * retrieval filter can see it. Changing either turns an edit into a new
 * document wearing an old one's history. Creating a new one and retiring this
 * one says the same thing and leaves the trail intact.
 *
 * Uploading fills this in rather than bypassing it. What a parser makes of a
 * .docx is a reading, and a reading that becomes cited regulation without
 * anybody looking at it is the failure this feature would otherwise introduce.
 * So the file is extracted, shown here, and saved only when somebody presses
 * the button.
 */

const input = cn(
  "w-full rounded-sm border border-line bg-canvas px-2 py-1 text-base text-fg",
  "transition-colors focus:outline-none focus:ring-2 focus:ring-focus",
  "disabled:cursor-not-allowed disabled:opacity-55"
);

/** A stacked label. The `Field` primitive lays its label out beside the
 *  control, which is right for a toolbar and wrong for a form of eight - at
 *  this count the labels want to align above their inputs so the eye reads one
 *  column rather than two. */
function Row({ label, children, className }: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("flex min-w-0 flex-col gap-1", className)}>
      <span className="text-xs text-faint">{label}</span>
      {children}
    </label>
  );
}

export type EditorMode =
  | { kind: "create" }
  | { kind: "edit"; docId: string };

export function DocumentEditor({
  mode, overview, actor, onClose, onSaved,
}: {
  mode: EditorMode;
  /** Types, suggested ids and which formats this installation can read. */
  overview: CorpusOverview;
  /** The name every mutation is recorded against. Owned by the panel so it is
   *  typed once per session rather than once per dialog. */
  actor: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const creating = mode.kind === "create";

  const [loaded, setLoaded] = useState<CorpusDocumentDetail | null>(null);
  const [docId, setDocId] = useState("");
  const [docType, setDocType] = useState(overview.types[0] ?? "POLICY");
  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState("");
  const [version, setVersion] = useState("1.0");
  const [effective, setEffective] = useState("");
  const [entities, setEntities] = useState("");
  const [tags, setTags] = useState("");
  const [body, setBody] = useState("");
  const [source, setSource] = useState<{ name: string; b64: string } | null>(null);
  const [note, setNote] = useState("");
  // Keys the form does not model, carried back untouched on save.
  const [extra, setExtra] = useState<Record<string, unknown>>({});
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const file = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (creating) {
      setDocId(overview.next_ids[docType] ?? "");
      return;
    }
    api.corpusDocument(mode.docId).then((doc) => {
      setLoaded(doc);
      setDocId(doc.doc_id);
      setDocType(doc.type);
      setTitle(doc.title);
      setOwner(doc.owner);
      setVersion(doc.version);
      setEffective(doc.effective);
      setEntities(doc.entities.join(", "));
      setTags(doc.tags.join(", "));
      setBody(doc.body);
      setExtra(doc.extra ?? {});
    }).catch((e) => toast.error("Could not open the document", String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode.kind, creating ? "" : mode.docId]);

  // Creating: the suggested id follows the type until somebody edits it.
  const [idTouched, setIdTouched] = useState(false);
  useEffect(() => {
    if (creating && !idTouched) setDocId(overview.next_ids[docType] ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docType, creating, idTouched]);

  const readable = Object.entries(overview.extract)
    .filter(([, yes]) => yes).map(([ext]) => ext);

  async function pick(chosen: File | null | undefined) {
    if (!chosen) return;
    setReading(true);
    try {
      const b64 = await toBase64(chosen);
      const out: ExtractResult = await api.extractCorpusDocument({
        filename: chosen.name, content_base64: b64,
      });
      setBody(out.text);
      setNote(out.note);
      setSource({ name: chosen.name, b64 });
      const meta = out.frontmatter ?? {};
      const scalar = (k: string) =>
        typeof meta[k] === "string" ? (meta[k] as string) : "";
      const list = (k: string) =>
        Array.isArray(meta[k]) ? (meta[k] as string[]).join(", ") : "";
      if (out.title && !title) setTitle(out.title);
      if (scalar("title")) setTitle(scalar("title"));
      if (scalar("owner")) setOwner(scalar("owner"));
      if (scalar("version")) setVersion(scalar("version"));
      if (scalar("effective")) setEffective(scalar("effective"));
      if (list("entities")) setEntities(list("entities"));
      if (list("tags")) setTags(list("tags"));
      if (creating && scalar("id")) { setDocId(scalar("id")); setIdTouched(true); }
      if (creating && scalar("type")
          && overview.types.includes(scalar("type").toUpperCase())) {
        setDocType(scalar("type").toUpperCase());
      }
      toast.notify(`read ${chosen.name}`,
                   "check it below - nothing is written until you save");
    } catch (e) {
      toast.error("Could not read that file", String(e));
    } finally {
      setReading(false);
      if (file.current) file.current.value = "";
    }
  }

  const split = (raw: string) =>
    raw.split(",").map((v) => v.trim()).filter(Boolean);

  async function save() {
    setBusy(true);
    try {
      const result = await api.saveCorpusDocument({
        doc_id: docId.trim(),
        type: docType,
        title: title.trim(),
        body,
        actor: actor.trim(),
        owner: owner.trim(),
        version: version.trim(),
        effective: effective.trim(),
        entities: split(entities),
        tags: split(tags),
        extra,
        replace: !creating,
        ...(source ? { source_base64: source.b64, source_filename: source.name } : {}),
      });
      const chunks = result.index?.chunks ?? 0;
      const mine = result.created ? "written" : "replaced";
      toast.notify(
        `${result.doc_id} ${mine}`,
        `the index was rebuilt lexically - ${chunks} chunks. Re-embed when you `
        + "want paraphrase search current too");
      onSaved();
      onClose();
    } catch (e) {
      toast.error("Could not save", String(e));
    } finally {
      setBusy(false);
    }
  }

  const words = body.trim() ? body.trim().split(/\s+/).length : 0;
  const ready = !!actor.trim() && !!docId.trim() && !!title.trim() && !!body.trim();

  return (
    <Dialog.Root open onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn("fixed inset-0 z-[var(--z-dialog)] bg-scrim",
                        "data-[state=open]:animate-fade-in")}
        />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-[var(--z-dialog)]",
            "flex w-[min(900px,calc(100vw-24px))] max-h-[90vh] -translate-x-1/2",
            "-translate-y-1/2 flex-col overflow-hidden rounded-lg border",
            "border-strong bg-overlay shadow-e3 data-[state=open]:animate-scale-in"
          )}
        >
          <div className="flex items-start gap-2.5 border-b border-subtle p-3.5">
            <IconDoc size={17} className="mt-0.5 shrink-0 text-faint" />
            <div className="min-w-0 flex-1">
              <Dialog.Title className="truncate text-md font-semibold text-fg">
                {creating ? "New document" : `Editing ${docId}`}
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 text-xs text-faint">
                {creating
                  ? "It joins the corpus retrieval reads, and the checks that read it."
                  : "Saving replaces the file and rebuilds the index."}
              </Dialog.Description>
            </div>
            <Dialog.Close asChild>
              <Button tone="ghost" size="xs" iconOnly aria-label="Close"
                      icon={<IconClose size={14} />} />
            </Dialog.Close>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-3.5">
            {Object.keys(extra).length > 0 && (
              <p className="mb-3 text-xs leading-relaxed text-faint">
                Carried through unchanged:{" "}
                {Object.keys(extra).map((k) => (
                  <Code key={k} className="mr-1">{k}</Code>
                ))}
              </p>
            )}

            {!creating && loaded && loaded.references.length > 0 && (
              <p className={cn("mb-3 rounded-sm border border-warn-border",
                               "bg-warn-soft px-2.5 py-2 text-xs leading-relaxed",
                               "text-warn-text")}>
                <IconAlert size={12} className="mr-1 inline align-[-1px]" />
                {loaded.references.length} place(s) in the code name{" "}
                <Code>{docId}</Code>. Its wording can change; its id and type
                cannot.
              </p>
            )}

            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              <Row label="Document id">
                <input
                  className={input}
                  value={docId}
                  disabled={!creating}
                  onChange={(e) => { setDocId(e.target.value); setIdTouched(true); }}
                  placeholder="POL-005"
                />
              </Row>
              <Row label="Type">
                <Select
                  value={docType}
                  onValueChange={setDocType}
                  disabled={!creating}
                  ariaLabel="Document type"
                  className="w-full"
                  options={overview.types.map((t) => ({ value: t, label: t }))}
                />
              </Row>
              <Row label="Title">
                <input className={input} value={title}
                       onChange={(e) => setTitle(e.target.value)}
                       placeholder="Allergen and Regulated Claim Policy" />
              </Row>
              <Row label="Owner">
                <input className={input} value={owner}
                       onChange={(e) => setOwner(e.target.value)}
                       placeholder="Regulatory Affairs" />
              </Row>
              <Row label="Version">
                <input className={input} value={version}
                       onChange={(e) => setVersion(e.target.value)} placeholder="1.0" />
              </Row>
              <Row label="Effective">
                <input className={input} value={effective}
                       onChange={(e) => setEffective(e.target.value)}
                       placeholder="2026-09-01" />
              </Row>
              <Row label="Entities">
                <input className={input} value={entities}
                       onChange={(e) => setEntities(e.target.value)}
                       placeholder="PRD-02, VAR-02A" />
              </Row>
              <Row label="Tags">
                <input className={input} value={tags}
                       onChange={(e) => setTags(e.target.value)}
                       placeholder="allergen, fail-closed" />
              </Row>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
                <input
                  ref={file}
                  type="file"
                  className="hidden"
                  accept={readable.join(",")}
                  onChange={(e) => pick(e.target.files?.[0])}
                />
                <Button size="sm" loading={reading}
                        onClick={() => file.current?.click()}>
                  Upload a file
                </Button>
                <span className="text-xs text-faint">
                  reads {readable.join(", ")}
                  {!overview.extract[".pdf"] && " — PDF needs pypdf installed"}
                </span>
            </div>

            {note && (
              <p className={cn("mt-2 rounded-sm border border-info-border",
                               "bg-info-soft px-2.5 py-2 text-xs leading-relaxed",
                               "text-info-text")}>
                {note}
              </p>
            )}

            <Row label="Body" className="mt-3">
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                spellCheck={false}
                className={cn(input, "h-[38vh] resize-y font-mono text-sm leading-relaxed")}
                placeholder={"# Title\n\n## Scope\n\nWhat this document governs."}
              />
            </Row>

            <p className="mt-1.5 text-xs leading-relaxed text-faint">
              {words} words. Headings are what retrieval splits on, so a
              document written as one block is cited as one block. Sections
              under 40 words are merged into the next one, and a document that
              produces no chunks is invisible to search however carefully it is
              filed.
            </p>
          </div>

          <div className={cn("flex flex-wrap items-center gap-2 border-t",
                             "border-subtle px-3.5 py-2.5")}>
            {!actor.trim() && (
              <Badge tone="warn">put your name in the panel behind this first</Badge>
            )}
            <div className="ml-auto flex items-center gap-2">
              <Button size="sm" onClick={onClose}>Cancel</Button>
              <Button size="sm" tone="primary" loading={busy} disabled={!ready}
                      onClick={save}>
                {creating ? "Create document" : "Save and reindex"}
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
