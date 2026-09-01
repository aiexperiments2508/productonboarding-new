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
#: Every document type the index recognises.
#:
#: The first four are the written standards this system is answerable to. The
#: next three arrived with launch readiness, which asks questions the standards
#: cannot answer: what a market authority *requires* of a category as opposed
#: to what our own policy says about it, what our own internal documentation
#: says, and what makes a product worth buying in this region this month.
#: COMMS is correspondence - evidence about one situation rather than guidance,
#: and excluded from search unless asked for.
KNOWN_TYPES: frozenset[str] = frozenset({
    "STANDARD", "CHANNEL", "POLICY", "POSTMORTEM",
    "REGULATION", "INTERNAL", "MARKET",
    "RECORD",
    "COMMS",
})

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


def chunk_document(path: Path, raw: str | None = None) -> list[DocChunk]:
    """This file, as chunks. Whatever the file is.

    Deliberately has no opinion about retirement: the caller decides which
    documents belong in an index, and this answers only "what would this one
    contribute". ``chunk_corpus`` is where a retired document is passed over,
    which keeps "produces chunks" a property of the text rather than of a
    status that changes underneath the tests asserting it.

    ``raw`` lets a caller that has already read the file hand the text over
    rather than have it read twice.
    """
    raw = path.read_text(encoding="utf-8") if raw is None else raw
    meta, body = parse_frontmatter(raw)

    doc_id = str(meta.get("id") or path.stem)
    doc_type = str(meta.get("type") or "STANDARD").upper()
    if doc_type not in KNOWN_TYPES:
        # Classified, never dropped. A typo in front matter should cost a
        # document its classification and not its presence: an unfindable
        # regulation is a worse failure than a misfiled one, and the misfiling
        # is visible in the index status while the absence is not.
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
            # Carried so a citation can say *which* version of a document it
            # is standing on. `SourceCite` has always rendered a version and
            # has been taking it from the signal that cited the document
            # rather than from the document.
            "version": meta.get("version", ""),
        },
    )


#: Directories under the corpus root holding artefacts rather than authored
#: documents. ``_source`` keeps the original file a document was extracted
#: from; a markdown rendition left there would otherwise be indexed twice.
EXCLUDED_DIRS: frozenset[str] = frozenset({"_source"})


def chunk_corpus(root: Path, include_retired: bool = False) -> list[DocChunk]:
    """Every authored document under the root, retired ones passed over.

    A retired rule is not a deleted rule. It stays on disk, stays in git, and
    stays readable at the path every citation already written against it names.
    What it stops being is *evidence*: retrieving a superseded policy to
    justify a decision made today is worse than retrieving nothing, because it
    comes back with a document id and an excerpt and looks like an answer.
    """
    chunks: list[DocChunk] = []
    for path in sorted(root.rglob("*.md")):
        if EXCLUDED_DIRS & set(path.relative_to(root).parts[:-1]):
            continue
        raw = path.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(raw)
        if (not include_retired
                and str(meta.get("status", "")).strip().upper() == "RETIRED"):
            continue
        chunks.extend(chunk_document(path, raw=raw))
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


def chunk_records(base) -> list[DocChunk]:
    """The catalog's own held values, as retrievable passages.

    The index held prose and the record held values, and every caller that
    wanted both had to join them by hand. That is a small annoyance for a
    reviewer's search and a real problem for launch readiness, where "what do we
    hold about this product" and "what does the regulation require of it" are
    two halves of one question and should cite evidence the same way.

    One passage per variant rather than per attribute. An attribute on its own
    retrieves badly - "45" is not a searchable idea - and a reviewer reading a
    finding wants the surrounding record anyway.

    Generated, never authored, and rebuilt whenever the index is. A passage
    describing a value that has since been corrected is worse than no passage:
    it is a citation that supports the wrong answer.
    """
    chunks: list[DocChunk] = []
    for variant_id in sorted(base.variants):
        variant = base.variants[variant_id]
        product = base.products.get(variant.product_id)
        if product is None:
            continue

        lines: list[str] = []
        entities = {variant_id, variant.product_id, product.supplier}
        for (entity, path), value in sorted(base.attr_values.items()):
            if entity != variant_id:
                continue
            definition = base.attr_defs.get(path)
            label = definition.label if definition else path
            unit = f" {definition.unit}" if definition and definition.unit else ""
            source = base.attr_sources.get((entity, path))
            # The document behind the value, on the same line as the value. A
            # value with no provenance is not evidence, and this index is read
            # for evidence.
            cite = f" [{source.doc_id} {source.version}]" if source else ""
            lines.append(f"- {label} ({path}): {value}{unit}{cite}")

        if not lines:
            continue

        # The identifiers belong in the title. A reviewer searching an id is
        # searching for exactly this passage, and a record whose title never
        # says which variant it describes loses that search to whichever
        # standards document happens to quote the id twice - which is what a
        # wider catalog, with more attributes per record, made happen.
        title = f"{variant.name} ({variant_id} / {variant.sku}) - held values"
        body = "\n".join([
            f"Product {product.id}, variant {variant_id}, "
            f"supplier {product.supplier}.",
            f"Category {product.category}."
            + (" Regulated." if product.regulated else ""),
            "",
            "Held values:",
            *lines,
        ])
        chunks.append(DocChunk(
            id=f"REC-{variant_id}",
            doc_id=f"REC-{variant_id}",
            doc_type="RECORD",
            title=title,
            text=f"{title}\n\n{body}",
            ordinal=0,
            metadata={
                "heading": "held values",
                "source": "catalog",
                "entities": sorted(entities),
                "tags": ["record", product.category.split(".")[0]],
                "owner": "product information management",
                "occurred": "", "severity": "", "effective": "",
            },
            row_index=-1,
        ))
    return chunks
