"""Turning an uploaded file into markdown the chunker can read.

Extraction here is **advisory**. What comes out of this module lands in the
editor for a person to read and correct; what they press save on is what
becomes a document. That ordering is the whole safety argument. A regulation
is the thing three readiness checks are answerable to, and a mis-parsed table
that silently becomes cited policy is a worse outcome than an upload that
needs five minutes of tidying.

Three formats, and they cost very different amounts.

``.md`` / ``.txt``
    Nothing to do. Decode, split any front matter the author already wrote,
    hand back the body.

``.docx``
    A zip of XML, so ``zipfile`` and ``xml.etree`` are enough and no
    dependency is added. That matters more here than it looks:
    ``requirements-datapack.txt`` excludes ``python-docx`` on the specific
    grounds that it needs ``lxml``, a compiled C extension, and this
    installation is meant to survive a Python version with no wheel for it.
    Style names map to heading levels, which is what makes the result
    chunkable - ``chunk._sections`` splits on headings, and a document
    arriving as one unbroken block retrieves badly and cites worse.

``.pdf``
    Needs ``pypdf``, which is pure Python but is still a dependency, so it is
    feature-detected exactly like ``openpyxl`` in ``sc.datapack.writers`` -
    absent, this says so in a sentence rather than failing an import at module
    load. PDFs carry no heading structure at all, so page markers are inserted:
    without them every chunk of a long regulation cites the same empty heading
    and a reviewer following the citation lands nowhere in particular.

The known-bad case is worth naming rather than hiding: a PDF of a table-heavy
regulation extracts as interleaved column fragments, and no amount of care here
fixes that. It is why the editor shows the result before anything is written.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from sc.rag import chunk as chunker
from sc.rag.library import BINARY_SUFFIXES, TEXT_SUFFIXES

#: WordprocessingML. The only namespace this needs.
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

#: Leading bytes worth recognising, so "you uploaded a PDF" is not reported as
#: "invalid UTF-8" - which is true, useless, and the kind of error message that
#: sends somebody to read the source.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"%PDF", ".pdf"),
    (b"PK\x03\x04", ".docx"),
    (b"\xd0\xcf\x11\xe0", ".doc"),
)


def available() -> dict[str, bool]:
    """Which formats this installation can actually read.

    The UI shows this rather than offering a file picker that accepts a type
    the server will refuse - an accept filter that lies is worse than a narrow
    one that does not.
    """
    return {
        ".md": True,
        ".markdown": True,
        ".txt": True,
        ".docx": True,
        ".pdf": _pypdf() is not None,
    }


def _pypdf():
    try:
        import pypdf
    except ImportError:
        return None
    return pypdf


def _sniff(raw: bytes) -> str:
    for prefix, suffix in _MAGIC:
        if raw.startswith(prefix):
            return suffix
    return ""


def extract(filename: str, raw: bytes) -> dict:
    """One uploaded file as markdown, plus whatever front matter it carried.

    Returns ``{"text", "frontmatter", "title", "note", "kind"}``. ``note`` is
    what the editor shows above the result: how it was read and what to check.
    """
    suffix = Path(str(filename or "")).suffix.lower()
    actual = _sniff(raw)

    if suffix in TEXT_SUFFIXES and actual in (".pdf", ".docx", ".doc"):
        raise ValueError(
            f"that file is named {filename!r} but its contents are a "
            f"{actual.lstrip('.').upper()}. Upload it with its real extension "
            "and it will be read properly")

    if suffix == ".docx" or (not suffix and actual == ".docx"):
        return _docx(raw)
    if suffix == ".pdf" or (not suffix and actual == ".pdf"):
        return _pdf(raw)
    if suffix in TEXT_SUFFIXES or not suffix:
        return _text(raw)

    accepted = ", ".join(sorted(TEXT_SUFFIXES | BINARY_SUFFIXES))
    raise ValueError(f"{suffix or 'that file'} is not a document type this "
                     f"corpus accepts - one of {accepted}")


def _finish(text: str, note: str, kind: str) -> dict:
    meta, body = chunker.parse_frontmatter(text)
    return {
        "text": body.strip(),
        "frontmatter": meta,
        "title": str(meta.get("title") or _first_heading(body) or ""),
        "note": note,
        "kind": kind,
    }


def _first_heading(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _text(raw: bytes) -> dict:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        # Latin-1 decodes any byte sequence, so this cannot fail - it can only
        # be wrong, which is visible in the editor and fixable there.
        text = raw.decode("latin-1")
        return _finish(text, "read as Latin-1 - it was not valid UTF-8, so "
                             "check any accented characters", "text")
    return _finish(text, "", "text")


# ---------------------------------------------------------------------------
# .docx
# ---------------------------------------------------------------------------


def _docx_text(node) -> str:
    """Every run of text under a node, in document order."""
    parts = [t.text or "" for t in node.iter(_W + "t")]
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _docx_heading(paragraph) -> int:
    """The heading level of a paragraph, or 0.

    Word writes ``Heading1`` and localisations write ``berschrift1`` and
    friends, so the digit is what is trusted and the word is only a gate.
    """
    style = paragraph.find(_W + "pPr/" + _W + "pStyle")
    if style is None:
        return 0
    name = str(style.get(_W + "val") or "")
    if "eading" not in name and "itle" not in name:
        return 0
    if "itle" in name:
        return 1
    # Word's Heading1 is the first *section* level, not the document title, so
    # it becomes `##`. That keeps the corpus convention - one `#` naming the
    # document, `##` for its sections - which is what makes the breadcrumb
    # `chunk._sections` builds read as "Allergen Standard > Scope" rather than
    # losing the document name at the first heading.
    digits = re.search(r"(\d+)", name)
    return min(int(digits.group(1)) + 1, 4) if digits else 2


def _docx_table(table) -> list[str]:
    rows: list[list[str]] = []
    for row in table.findall(_W + "tr"):
        rows.append([_docx_text(cell) for cell in row.findall(_W + "tc")])
    if not rows:
        return []

    width = max(len(r) for r in rows)
    rendered = []
    for i, row in enumerate(rows):
        cells = [c.replace("|", r"\|") for c in row] + [""] * (width - len(row))
        rendered.append("| " + " | ".join(cells) + " |")
        if i == 0:
            rendered.append("|" + "---|" * width)
    return rendered


def _docx(raw: bytes) -> dict:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        document = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(
            "that does not read as a .docx - it may be an older .doc, which "
            "this cannot open. Save it as .docx or paste the text in") from exc

    body = ElementTree.fromstring(document).find(_W + "body")
    if body is None:
        raise ValueError("that .docx has no document body")

    lines: list[str] = []
    tables = 0
    for node in body:
        if node.tag == _W + "p":
            text = _docx_text(node)
            if not text:
                continue
            level = _docx_heading(node)
            lines.append("#" * level + " " + text if level else text)
            lines.append("")
        elif node.tag == _W + "tbl":
            rendered = _docx_table(node)
            if rendered:
                tables += 1
                lines.extend(rendered)
                lines.append("")

    text = "\n".join(lines).strip()
    if not text:
        raise ValueError("that .docx held no readable text")

    headings = sum(1 for line in text.splitlines() if line.startswith("#"))
    note = (f"read from Word: {headings} heading(s), {tables} table(s). "
            "Headings are what the retriever splits on, so check they came "
            "through - a document with none is indexed as one long block.")
    if not headings:
        note = ("read from Word, but no headings came through - it may use "
                "direct formatting rather than heading styles. Add '## ' "
                "before each section title or it will be indexed as one "
                "undifferentiated block and cite badly.")
    return _finish(text, note, "docx")


# ---------------------------------------------------------------------------
# .pdf
# ---------------------------------------------------------------------------


def _pdf(raw: bytes) -> dict:
    pypdf = _pypdf()
    if pypdf is None:
        raise ValueError(
            "this installation cannot read .pdf - pypdf is not installed. "
            "Install it with 'pip install -r requirements-corpus.txt', or "
            "paste the text in as markdown")

    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError("that PDF is encrypted - unlock it first")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - a broken PDF is a message, not a 500
        raise ValueError(f"that PDF could not be read: {str(exc)[:200]}") from exc

    lines: list[str] = []
    for number, page in enumerate(pages, 1):
        if not page:
            continue
        # Page markers stand in for the headings a PDF does not have. Without
        # them `chunk._sections` sees one section, every chunk carries an empty
        # heading, and a citation points at the document rather than at a place
        # in it - which is the whole thing a citation is for.
        lines.append(f"## Page {number}")
        lines.append("")
        lines.append(page)
        lines.append("")

    text = "\n".join(lines).strip()
    if not text:
        raise ValueError(
            "no text came out of that PDF. It is most likely a scan, which "
            "needs OCR this system does not do - paste the text in instead")

    return _finish(
        text,
        f"read from PDF: {len([p for p in pages if p])} of {len(pages)} page(s) "
        "held text. Page headings were inserted because a PDF has none. Check "
        "tables and columns closely - they extract badly and this is the "
        "format most likely to need editing before you save it.",
        "pdf")
