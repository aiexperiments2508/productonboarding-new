"""Editing the corpus: the documents the factory is answerable to.

The corpus is authored content committed to the repository, and that does not
change here. What changes is that adding a regulation, correcting a policy or
withdrawing a superseded standard no longer needs a checkout and a shell - the
same file lands in the same place, through a door that records who opened it.

Three rules hold that door shut.

*   **No path ever arrives from a client.** A caller names a document id; this
    module finds the file by reading front matter, and composes the path itself
    when creating one. There is no traversal to filter because there is no
    caller-supplied path to traverse - which is a stronger guarantee than any
    amount of ``..`` stripping, and it does not have to be right about Windows
    drive letters to hold.

*   **Removal is retirement first.** A retired document keeps its file and its
    history and simply stops producing chunks (see ``chunk.chunk_document``).
    Deleting it is a second, separate act that refuses to run until the first
    has happened. "What did this say when the decision was made" has to stay
    answerable after the document stops governing anything.

*   **Every mutation is audited, then reindexed, under one lock.** The index is
    a process-wide cache rebuilt in full, and FastAPI runs these handlers in a
    threadpool. Two concurrent saves without the lock is a corrupt index.

The rebuild after a save is lexical only. It needs no gateway, costs nothing
and takes milliseconds, so an edited document is findable immediately;
embeddings are a separate, explicit act because they cost tokens and can fail.
``index.status()["vectors_stale"]`` is what says the semantic half has fallen
behind, and it is only trustworthy because the fingerprint written by
``index.build`` makes it so.
"""

from __future__ import annotations

import os
import re
import threading
from datetime import datetime
from pathlib import Path

from sc.rag import chunk as chunker
from sc.rag import index as rag_index

#: A document id: a letter-led prefix and one to three dash-joined parts.
#: Matches POL-001, REG-009, STD-002, INC-2025-041.
DOC_ID = re.compile(r"^[A-Z][A-Z0-9]{1,9}(?:-[A-Z0-9]+){1,3}$")

TEXT_SUFFIXES = frozenset({".md", ".markdown", ".txt"})
BINARY_SUFFIXES = frozenset({".pdf", ".docx"})
ACCEPTED_SUFFIXES = TEXT_SUFFIXES | BINARY_SUFFIXES

#: A policy that does not fit in a megabyte of text is not a policy.
MAX_BODY_BYTES = 1 * 1024 * 1024
#: Mirrors ``sc.estate.intake.MAX_UPLOAD_BYTES`` deliberately - one number for
#: "how big may a document a stranger sends us be".
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

ACTIVE = "ACTIVE"
RETIRED = "RETIRED"

#: Where a new document of each type is filed, and the id series it joins.
#: The directory is convention only: ``chunk_corpus`` globs the whole tree and
#: the ``type:`` in front matter is what actually classifies a document.
TYPE_DIR: dict[str, str] = {
    "REGULATION": "regulation",
    "POLICY": "policy",
    "STANDARD": "standard",
    "INTERNAL": "internal",
    "CHANNEL": "channel",
    "POSTMORTEM": "incident",
    "MARKET": "market",
}

TYPE_PREFIX: dict[str, str] = {
    "REGULATION": "REG", "POLICY": "POL", "STANDARD": "STD",
    "INTERNAL": "INT", "CHANNEL": "CHN", "POSTMORTEM": "INC", "MARKET": "MKT",
}

#: The types a person may author. ``RECORD`` and ``COMMS`` are in
#: ``chunk.KNOWN_TYPES`` but are synthesised on every build - records from the
#: live catalog, correspondence from the simulation - so a file of either kind
#: would be silently overwritten by the next rebuild.
EDITABLE_TYPES: tuple[str, ...] = tuple(TYPE_DIR)

#: Front matter keys this module writes, in the order the corpus already uses.
#: Anything else a document carries - ``occurred`` and ``severity`` on an
#: incident, say - is preserved and written after these. Dropping a key we do
#: not happen to know about would quietly rewrite somebody else's document.
CANONICAL_KEYS: tuple[str, ...] = (
    "id", "type", "title", "owner", "version", "effective", "occurred",
    "closed", "severity", "status", "source_file", "entities", "tags",
)

#: The keys ``write_document`` sets from its own arguments. Everything else a
#: document carries travels through ``extra`` untouched.
#:
#: Deliberately narrower than CANONICAL_KEYS, which is only a render *order*.
#: An incident's ``occurred`` and ``severity`` are ordered here and set by
#: nobody, so counting them as managed drops them the first time somebody edits
#: a postmortem - which is a field disappearing out of a compliance record
#: because a form did not have a box for it.
MANAGED_KEYS: frozenset[str] = frozenset({
    "id", "type", "title", "owner", "version", "effective", "status",
    "source_file", "entities", "tags",
})
LIST_KEYS = frozenset({"entities", "tags"})

#: Types whose last active member may not quietly leave, and the check that
#: stops working when the shelf is empty.
#:
#: This is the sharp edge of the whole feature. ``reading.saleability`` returns
#: ``[], True`` when nothing is retrieved (sc/readiness/reading.py:191-192),
#: and so do ``internal_contradiction`` (222) and ``policy_conformance`` (270).
#: So retiring the last REGULATION does not break anything visibly - it makes
#: every product *pass* the check that exists to stop it, and reports the
#: assessment as complete. A fail-open that reads as a clean run is the worst
#: shape a compliance failure can take, and it is one retirement away.
LOAD_BEARING_TYPES: dict[str, str] = {
    "REGULATION": "readiness.saleability - the only check that can block a "
                  "listing - would find no mandate to read, pass every "
                  "product, and report the assessment as complete",
    "INTERNAL": "readiness.internal_contradiction would pass every product",
    "POLICY": "readiness.policy_conformance would pass every product",
    "STANDARD": "copy regeneration would have no content standard to write to",
    "CHANNEL": "scope resolution would have no channel rules to read",
    "POSTMORTEM": "the evidence desk would find no prior incidents",
}

#: Serialises write-then-rebuild. Reentrant because the mutation helpers call
#: each other (retire reads, writes and rebuilds).
_LOCK = threading.RLock()


class LibraryError(ValueError):
    """A refusal with a sentence a person can act on."""


class ReferencedError(LibraryError):
    """Refused because something else would notice this document leaving.

    Its own type so the HTTP layer can answer 409 rather than 400. The request
    was well formed; the state of the corpus is what refused it, and a reviewer
    who has read the list may repeat the request having acknowledged it. A 400
    would say "you asked wrongly", which is not what happened.
    """

    def __init__(self, message: str, blocked: list[dict]) -> None:
        super().__init__(message)
        self.blocked = blocked


# ---------------------------------------------------------------------------
# Locating and validating
# ---------------------------------------------------------------------------


def _root() -> Path:
    return rag_index.corpus_root()


def _assert_id(doc_id: str) -> str:
    candidate = str(doc_id or "").strip().upper()
    if not DOC_ID.match(candidate):
        raise LibraryError(
            f"{doc_id!r} is not a document id - it should look like POL-005, "
            "REG-010 or INC-2026-003")
    return candidate


def _assert_inside(path: Path) -> Path:
    """Belt and braces over a path this module composed itself."""
    root = _root().resolve()
    resolved = path.resolve()
    if resolved == root or root not in resolved.parents:
        raise LibraryError(f"{path} is outside the corpus")
    if resolved.suffix.lower() not in ACCEPTED_SUFFIXES:
        raise LibraryError(
            f"{resolved.suffix or 'a file with no suffix'} is not a document "
            f"type this corpus accepts")
    return resolved


def _slug(text: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return out[:60] or "document"


def _iter_files() -> list[Path]:
    root = _root()
    if not root.exists():
        return []
    return [
        p for p in sorted(root.rglob("*.md"))
        if not (chunker.EXCLUDED_DIRS & set(p.relative_to(root).parts[:-1]))
    ]


def _read(path: Path) -> tuple[dict, str]:
    return chunker.parse_frontmatter(path.read_text(encoding="utf-8"))


def _find(doc_id: str) -> Path | None:
    """The file whose front matter claims this id.

    Reads front matter rather than trusting the filename: the id is what the
    rest of the system cites, and a file renamed by hand must not become a
    second document.
    """
    wanted = _assert_id(doc_id)
    for path in _iter_files():
        meta, _ = _read(path)
        if str(meta.get("id") or path.stem).strip().upper() == wanted:
            return path
    return None


def _new_path(doc_id: str, doc_type: str, title: str) -> Path:
    directory = TYPE_DIR.get(doc_type)
    if directory is None:
        raise LibraryError(f"{doc_type} is not a type a person authors")
    return _root() / directory / f"{doc_id}-{_slug(title)}.md"


def next_id(doc_type: str, documents: list[dict] | None = None) -> str:
    """The next free id in a type's series, for the editor to offer.

    Takes an already-fetched listing when the caller has one - offering seven
    of these on one screen should read the corpus once, not seven times.
    """
    prefix = TYPE_PREFIX.get(str(doc_type).strip().upper())
    if prefix is None:
        return ""
    pattern = re.compile(rf"^{prefix}-(\d+)$")
    highest = 0
    for document in (list_documents() if documents is None else documents):
        match = pattern.match(document["doc_id"])
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:03d}"


# ---------------------------------------------------------------------------
# Rendering front matter
# ---------------------------------------------------------------------------


def _split_list(value) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value or "").strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [v.strip() for v in text.split(",") if v.strip()]


def _render_value(key: str, value) -> str:
    if key in LIST_KEYS or isinstance(value, (list, tuple)):
        return "[" + ", ".join(_split_list(value)) + "]"
    return str(value).strip()


def _assert_renderable(meta: dict) -> None:
    """Refuse what ``parse_frontmatter`` would read back as something else.

    The header format is hand-parsed (chunk.py:47-68), not YAML, and it has two
    edges that turn a save into a silent corruption:

    *   a scalar that starts with ``[`` and ends with ``]`` is re-read as a
        list, so a title like ``[Draft] Allergen Policy`` comes back as the
        one-element list ``["Draft] Allergen Policy"]``;
    *   a list item containing a comma is split in two, because the parser
        splits on every comma unconditionally.

    Refusing is right where escaping would be wrong. An escaping scheme the
    reader does not know about produces a file that round-trips through this
    module and breaks the moment somebody edits it by hand - and hand-editing
    is still the normal way to work on a committed corpus.
    """
    for key, value in meta.items():
        if key in LIST_KEYS or isinstance(value, (list, tuple)):
            for item in _split_list(value):
                if "," in item or "[" in item or "]" in item:
                    raise LibraryError(
                        f"{key} item {item!r} cannot contain a comma or a "
                        "bracket - the header format splits on commas and "
                        "would read it back as two entries")
            continue
        text = str(value)
        if "\n" in text or "\r" in text:
            raise LibraryError(f"{key} has to be a single line")
        stripped = text.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            raise LibraryError(
                f"{key} cannot start with '[' and end with ']' - the header "
                "format would read it back as a list rather than as text")


def _clean_body(body: str) -> str:
    """Body text that will not be mistaken for a second header.

    ``_FRONTMATTER`` (chunk.py:43) is anchored at the start and non-greedy, so
    a body whose first line is a markdown horizontal rule can be swallowed as
    front matter on a later read. Cheaper to drop the rule than to explain the
    document that lost its opening section.
    """
    text = str(body or "").strip()
    while text.startswith("---"):
        _, _, rest = text.partition("\n")
        text = rest.strip()
    return text


def _render(meta: dict, body: str) -> str:
    """Front matter plus body, in the shape ``parse_frontmatter`` reads back.

    Round-tripping matters more than prettiness: whatever this writes is what
    the chunker parses on the next build, and a key rendered in a form the
    hand-written parser does not accept is a document that silently loses a
    field.
    """
    _assert_renderable(meta)
    lines = ["---"]
    written: set[str] = set()
    for key in CANONICAL_KEYS:
        if key not in meta:
            continue
        written.add(key)
        lines.append(f"{key}: {_render_value(key, meta[key])}")
    for key, value in meta.items():
        if key in written:
            continue
        lines.append(f"{key}: {_render_value(key, value)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + _clean_body(body) + "\n"


def _write_atomic(path: Path, text: str) -> None:
    _assert_inside(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _summary(path: Path, meta: dict, body: str, counts: dict[str, int]) -> dict:
    doc_id = str(meta.get("id") or path.stem).strip()
    stat = path.stat()
    return {
        "doc_id": doc_id,
        "type": str(meta.get("type") or "STANDARD").strip().upper(),
        "title": str(meta.get("title") or path.stem),
        "owner": str(meta.get("owner", "")),
        "version": str(meta.get("version", "")),
        "effective": str(meta.get("effective", "")),
        "status": str(meta.get("status", ACTIVE)).strip().upper(),
        "entities": _split_list(meta.get("entities", [])),
        "tags": _split_list(meta.get("tags", [])),
        "source_file": str(meta.get("source_file", "")),
        "path": path.relative_to(_root()).as_posix(),
        "bytes": stat.st_size,
        "words": len(body.split()),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(
            timespec="seconds"),
        "chunks": counts.get(doc_id, 0),
        "indexed": doc_id in counts,
    }


def list_documents() -> list[dict]:
    """Every document on disk, with what the index currently holds of it.

    Reads the filesystem rather than the index, so a retired document - which
    produces no chunks - still appears, marked, rather than vanishing from the
    screen that is supposed to be able to bring it back.
    """
    counts: dict[str, int] = {}
    try:
        for c in rag_index.load().chunks:
            counts[c.doc_id] = counts.get(c.doc_id, 0) + 1
    except Exception:  # noqa: BLE001 - an unbuilt index is not a failed listing
        pass

    out = []
    for path in _iter_files():
        meta, body = _read(path)
        out.append(_summary(path, meta, body, counts))
    out.sort(key=lambda d: (d["type"], d["doc_id"]))
    return out


def read_document(doc_id: str) -> dict:
    """One document, in the shape the editor needs to put it back."""
    path = _find(doc_id)
    if path is None:
        raise LookupError(f"no document {doc_id}")

    from sc.rag import retrieve

    meta, body = _read(path)
    resolved = str(meta.get("id") or path.stem).strip()
    counts: dict[str, int] = {}
    try:
        for c in rag_index.load().chunks:
            counts[c.doc_id] = counts.get(c.doc_id, 0) + 1
    except Exception:  # noqa: BLE001
        pass

    summary = _summary(path, meta, body, counts)
    extra = {k: v for k, v in meta.items() if k not in MANAGED_KEYS}
    return {
        **summary,
        "body": body.strip(),
        "text": path.read_text(encoding="utf-8"),
        "extra": extra,
        "chunk_ids": [c.id for c in retrieve.get_document(resolved)],
        "references": references(resolved),
    }


def references(doc_id: str) -> list[dict]:
    """Where the code names this document by id.

    Retiring `POL-002` does not fail loudly. It removes chunks, and the checks
    that cited them quietly start finding nothing - which looks like a clean
    run. This is what lets the screen say so before the fact instead of a
    reviewer discovering it after.
    """
    wanted = _assert_id(doc_id)
    found: list[dict] = []

    root = Path("sc")
    if root.exists():
        pattern = re.compile(r"\b" + re.escape(wanted) + r"\b")
        # This module is skipped, and not as a convenience. Its own refusal
        # messages name POL-005 and REG-010 as examples of what an id looks
        # like, so scanning itself reports any document created at one of
        # those ids as load bearing - a warning that is always wrong, on the
        # one path where a warning has to be worth reading.
        here = Path(__file__).resolve()
        for path in sorted(root.rglob("*.py")):
            if "__pycache__" in path.parts or path.resolve() == here:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for number, line in enumerate(lines, 1):
                if pattern.search(line):
                    found.append({"kind": "NAMED",
                                  "where": path.as_posix() + ":" + str(number),
                                  "detail": line.strip()[:200]})
                    if len(found) >= 50:
                        return found

    documents = list_documents()
    mine = next((d for d in documents if d["doc_id"].upper() == wanted), None)
    if mine is not None and mine["status"] == ACTIVE:
        kind = mine["type"]
        consequence = LOAD_BEARING_TYPES.get(kind)
        siblings = [d for d in documents
                    if d["type"] == kind and d["status"] == ACTIVE
                    and d["doc_id"].upper() != wanted]
        if consequence and not siblings:
            found.append({"kind": "LAST",
                          "where": "the last document of type " + kind,
                          "detail": consequence})
    return found


def _assert_unreferenced(doc_id: str, acknowledged: bool) -> list[dict]:
    """Refuse a removal nothing else is ready for, unless it is acknowledged.

    Advisory by design. A reviewer who has read the list is allowed to go
    ahead - this is a corpus, not a lock - but they have to have been shown it
    first, because the failure mode being guarded against is invisible.
    """
    blocked = references(doc_id)
    if blocked and not acknowledged:
        where = ", ".join(b["where"] for b in blocked[:3])
        more = "" if len(blocked) <= 3 else " and " + str(len(blocked) - 3) + " more"
        raise ReferencedError(
            doc_id + " is named in " + str(len(blocked)) + " place(s) that "
            "would notice it leaving - " + where + more + ". Read them, then "
            "repeat this having acknowledged it if it is still what you want.",
            blocked)
    return blocked


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _audit(actor: str, action: str, doc_id: str, detail: dict) -> None:
    from sc.tools import planning

    planning.audit(actor, action, "corpus", doc_id, detail)


def _reindex() -> dict:
    """Lexical rebuild. Fast, gateway-free, and enough to make an edit findable."""
    return rag_index.build(embed=False)


def _assert_actor(actor: str) -> str:
    name = str(actor or "").strip()
    if not name:
        raise LibraryError(
            "changing what the factory is answerable to has to be attributable "
            "to somebody")
    return name


def write_document(
    *,
    doc_id: str,
    doc_type: str,
    title: str,
    body: str,
    actor: str,
    owner: str = "",
    version: str = "",
    effective: str = "",
    entities=None,
    tags=None,
    status: str = ACTIVE,
    source_file: str = "",
    extra: dict | None = None,
    replace: bool = False,
    reindex: bool = True,
) -> dict:
    """Create a document, or - with ``replace`` - put a new version of one back.

    ``replace`` is required rather than inferred. Writing over an existing
    document because its id happened to match is how somebody sets out to add
    REG-010 and instead silently rewrites the one already there - no error, no
    diff, and the old text is gone unless the corpus happened to be committed.
    Editing is a thing you open a document to do, so it says so.

    Replacing keeps the existing file path even when the title has changed. A
    document's id is what the rest of the system cites; renaming its file on a
    title edit would leave every stored ``source`` path pointing at nothing for
    no gain a reader would notice.
    """
    name = _assert_actor(actor)
    identifier = _assert_id(doc_id)
    kind = str(doc_type or "").strip().upper()
    if kind not in EDITABLE_TYPES:
        raise LibraryError(
            f"{doc_type!r} is not a type a person authors - one of "
            f"{', '.join(EDITABLE_TYPES)}")
    heading = str(title or "").strip()
    if not heading:
        raise LibraryError("a document needs a title")
    text = str(body or "")
    if len(text.encode("utf-8")) > MAX_BODY_BYTES:
        raise LibraryError(
            f"that body is larger than the {MAX_BODY_BYTES // 1024}KB a single "
            "document may be")

    state = str(status or ACTIVE).strip().upper()
    if state not in {ACTIVE, RETIRED}:
        raise LibraryError(f"{status!r} is not a document status")

    with _LOCK:
        existing = _find(identifier)
        created = existing is None
        if existing is not None and not replace:
            raise LibraryError(
                f"{identifier} already exists at "
                f"{existing.relative_to(_root()).as_posix()}. Open it to edit "
                "it, or pick another id - creating over a document would "
                "replace what it says without showing you what it said")
        path = existing if existing is not None else _new_path(
            identifier, kind, heading)

        meta: dict = dict(extra or {})
        meta.update({
            "id": identifier,
            "type": kind,
            "title": heading,
            "owner": str(owner or "").strip(),
            "version": str(version or "").strip(),
            "effective": str(effective or "").strip(),
            "entities": _split_list(entities),
            "tags": _split_list(tags),
        })
        if state == RETIRED:
            meta["status"] = RETIRED
        elif "status" in meta:
            meta["status"] = ACTIVE
        if source_file:
            meta["source_file"] = str(source_file).strip()
        meta = {k: v for k, v in meta.items() if v not in ("", [], None)}

        _write_atomic(path, _render(meta, text))
        _audit(name,
               "CORPUS_DOCUMENT_CREATED" if created else "CORPUS_DOCUMENT_WRITTEN",
               identifier,
               {"type": kind, "title": heading,
                "path": path.relative_to(_root()).as_posix(),
                "version": meta.get("version", ""), "bytes": len(text)})
        index_status = _reindex() if reindex else None

    return {"doc_id": identifier, "created": created,
            "path": path.relative_to(_root()).as_posix(),
            "index": index_status}


def _set_status(doc_id: str, state: str, actor: str, action: str,
                reason: str = "", acknowledged: list[dict] | None = None) -> dict:
    name = _assert_actor(actor)
    with _LOCK:
        path = _find(doc_id)
        if path is None:
            raise LookupError(f"no document {doc_id}")
        meta, body = _read(path)
        identifier = str(meta.get("id") or path.stem).strip()
        before = str(meta.get("status", ACTIVE)).strip().upper()
        meta["status"] = state
        _write_atomic(path, _render(meta, body))
        _audit(name, action, identifier,
               {"from": before, "to": state, "reason": str(reason or "").strip(),
                "path": path.relative_to(_root()).as_posix(),
                "acknowledged": acknowledged or []})
        index_status = _reindex()
    return {"doc_id": identifier, "status": state, "previous": before,
            "index": index_status}


def retire_document(doc_id: str, actor: str, reason: str = "",
                    acknowledge_references: bool = False) -> dict:
    """Withdraw a document from retrieval without destroying it.

    The file stays, the front matter records the state, and the chunker stops
    emitting chunks for it. Nothing that cited it while it governed becomes
    unreadable; it simply stops being offered as current guidance.
    """
    with _LOCK:
        blocked = _assert_unreferenced(doc_id, acknowledge_references)
        result = _set_status(doc_id, RETIRED, actor,
                             "CORPUS_DOCUMENT_RETIRED", reason,
                             acknowledged=blocked)
    result["acknowledged"] = blocked
    return result


def restore_document(doc_id: str, actor: str, reason: str = "") -> dict:
    return _set_status(doc_id, ACTIVE, actor, "CORPUS_DOCUMENT_RESTORED", reason)


def delete_document(doc_id: str, actor: str, reason: str = "",
                    acknowledge_references: bool = False) -> dict:
    """Remove the file. Refuses until the document has been retired.

    Two steps rather than one because they are two decisions. "This no longer
    governs" is a judgement somebody makes about the business; "and no record
    of it should remain here" is a different one, and running them together
    means the second never gets argued.
    """
    name = _assert_actor(actor)
    with _LOCK:
        path = _find(doc_id)
        if path is None:
            raise LookupError(f"no document {doc_id}")
        meta, _ = _read(path)
        identifier = str(meta.get("id") or path.stem).strip()
        if str(meta.get("status", ACTIVE)).strip().upper() != RETIRED:
            raise LibraryError(
                f"{identifier} is still in force - retire it first, so that "
                "withdrawing it and destroying it stay two decisions")

        blocked = _assert_unreferenced(identifier, acknowledge_references)
        relative = path.relative_to(_root()).as_posix()
        # The whole text into the ledger before the file goes. "Recoverable"
        # has to mean recoverable even when the branch was never committed,
        # and every document in this corpus fits inside the cap several times
        # over.
        raw = path.read_text(encoding="utf-8")
        _assert_inside(path).unlink()

        original = str(meta.get("source_file", "")).strip()
        if original:
            candidate = _root() / original
            try:
                _assert_inside(candidate).unlink(missing_ok=True)
            except LibraryError:
                pass

        _audit(name, "CORPUS_DOCUMENT_DELETED", identifier,
               {"path": relative, "reason": str(reason or "").strip(),
                "type": str(meta.get("type", "")),
                "title": str(meta.get("title", "")),
                "acknowledged": blocked,
                "bytes": len(raw), "text": raw[:64_000],
                "truncated": len(raw) > 64_000})
        index_status = _reindex()

    return {"doc_id": identifier, "deleted": relative, "index": index_status}


def store_original(doc_id: str, filename: str, raw: bytes) -> str:
    """Keep the file a document was extracted from, beside the corpus.

    Under ``_source``, which ``chunk_corpus`` skips - the rendition is what is
    indexed and the original is what is authoritative, and indexing both would
    make a document cite itself twice.
    """
    identifier = _assert_id(doc_id)
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix not in ACCEPTED_SUFFIXES:
        raise LibraryError(f"{suffix or 'that file'} is not a document type "
                           "this corpus accepts")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise LibraryError(
            f"that file is larger than the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB "
            "a single upload may be")

    path = _root() / "_source" / f"{identifier}{suffix}"
    _assert_inside(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path.relative_to(_root()).as_posix()
