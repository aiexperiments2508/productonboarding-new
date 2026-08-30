"""Markdown-aware chunking for the standard, channel, policy and incident corpus.

Splitting on headings rather than on a fixed character count matters here.
These documents are structured as rule sections, and a chunk that begins
mid-clause retrieves badly and cites worse - an editor following a citation
needs to land on a whole rule, not on its second half.

Each chunk carries the document title and its heading path as a prefix, so an
embedded chunk retains the context that makes it findable. A section reading
"No content change may be applied within 7 days of its press date" is far more
retrievable when it also carries "CH-PRINT - Store Catalogue and Print".
"""

from __future__ import annotations

import re
from pathlib import Path

from sc.contracts import DocChunk

# Target sizes in words. Sections shorter than the minimum are merged forward
# so a two-line clause does not become its own chunk.
TARGET_WORDS = 320
MIN_WORDS = 40
MAX_WORDS = 500

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Read the YAML-ish header.

    Hand-parsed rather than pulling in a YAML dependency: the header format is
    ours and is limited to scalars and simple bracket lists.
    """
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text

    meta: dict = {}
    for line in match.group(1).splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, raw = line.partition(":")
        key, raw = key.strip(), raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            meta[key] = [v.strip() for v in inner.split(",") if v.strip()]
        else:
            meta[key] = raw
    return meta, text[match.end():]


def _sections(body: str) -> list[tuple[str, str]]:
    """Split into (heading path, text) pairs, tracking nesting."""
    sections: list[tuple[str, str]] = []
    stack: list[str] = []
    current: list[str] = []
    heading = ""

    def flush() -> None:
        text = "\n".join(current).strip()
        if text:
            sections.append((heading, text))

    for line in body.splitlines():
        match = _HEADING.match(line)
        if match:
            flush()
            current = []
            level = len(match.group(1))
            title = match.group(2).strip()
            stack = stack[: level - 1]
            stack.append(title)
            heading = " > ".join(stack)
        else:
            current.append(line)
    flush()
    return sections


def _split_long(text: str) -> list[str]:
    """Break an oversized section on paragraph boundaries.

    Tables are kept whole: a split table is unreadable in a citation and the
    header row carries the meaning of every cell below it.
    """
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    parts: list[str] = []
    buffer: list[str] = []
    count = 0

    for paragraph in paragraphs:
        words = len(paragraph.split())
        is_table = paragraph.lstrip().startswith("|")
        if count and count + words > MAX_WORDS and not is_table:
            parts.append("\n\n".join(buffer))
            buffer, count = [], 0
        buffer.append(paragraph)
        count += words
        if count >= TARGET_WORDS:
            parts.append("\n\n".join(buffer))
            buffer, count = [], 0

    if buffer:
        parts.append("\n\n".join(buffer))
    return parts or [text]


def chunk_document(path: Path) -> list[DocChunk]:
    raw = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)

    doc_id = str(meta.get("id") or path.stem)
    doc_type = str(meta.get("type") or "STANDARD").upper()
    if doc_type not in {"STANDARD", "CHANNEL", "POLICY", "POSTMORTEM", "COMMS"}:
        doc_type = "STANDARD"
    title = str(meta.get("title") or path.stem)

    chunks: list[DocChunk] = []
    pending: tuple[str, str] | None = None

    for heading, text in _sections(body):
        # Merge a too-short section into the next one rather than emitting it
        # alone - headings like "## Purpose" with one line under them.
        if pending is not None:
            heading = pending[0] or heading
            text = f"{pending[1]}\n\n{text}"
            pending = None
        if len(text.split()) < MIN_WORDS:
            pending = (heading, text)
            continue
        for part in _split_long(text):
            chunks.append(_make(doc_id, doc_type, title, heading, part,
                                len(chunks), meta, path))

    if pending is not None:
        chunks.append(_make(doc_id, doc_type, title, pending[0], pending[1],
                            len(chunks), meta, path))

    return chunks


def _make(doc_id, doc_type, title, heading, text, ordinal, meta,
          path) -> DocChunk:
    # The heading path is prepended to the indexed text, not just stored as
    # metadata, so both the embedding and BM25 see the context.
    prefix = f"{title}" + (f" - {heading}" if heading else "")
    return DocChunk(
        id=f"{doc_id}#{ordinal:02d}",
        doc_id=doc_id,
        doc_type=doc_type,
        title=title,
        text=f"{prefix}\n\n{text}",
        ordinal=ordinal,
        metadata={
            "heading": heading,
            "source": str(path.as_posix()),
            "entities": meta.get("entities", []),
            "tags": meta.get("tags", []),
            "owner": meta.get("owner", ""),
            "occurred": meta.get("occurred", ""),
            "severity": meta.get("severity", ""),
            "effective": meta.get("effective", ""),
        },
    )


def chunk_corpus(root: Path) -> list[DocChunk]:
    chunks: list[DocChunk] = []
    for path in sorted(root.rglob("*.md")):
        chunks.extend(chunk_document(path))
    return chunks


def chunk_comms(directory: Path) -> list[DocChunk]:
    """Inbound correspondence, indexed alongside the reference corpus.

    Retrieving a prior email is often what explains a live one - the finale's
    "Max only" clarification only makes sense next to the correction it narrows.
    """
    chunks: list[DocChunk] = []
    for path in sorted(directory.glob("*.eml")):
        raw = path.read_text(encoding="utf-8")
        headers, _, body = raw.partition("\n\n")
        fields = {}
        for line in headers.splitlines():
            key, _, value = line.partition(":")
            fields[key.strip().lower()] = value.strip()

        subject = fields.get("subject", path.stem)
        chunks.append(DocChunk(
            id=f"{path.stem}#00",
            doc_id=path.stem,
            doc_type="COMMS",
            title=subject,
            text=f"{subject}\n\nFrom: {fields.get('from', '')}\n\n{body.strip()}",
            ordinal=0,
            metadata={"heading": "", "source": str(path.as_posix()),
                      "from": fields.get("from", ""),
                      "date": fields.get("date", ""),
                      "event_id": fields.get("x-event-id", ""),
                      "entities": [], "tags": ["comms"]},
        ))
    return chunks
