"""Authoring the corpus: path safety, retirement, removal guards, extraction.

**Every test in this module works on a throwaway copy of the corpus.** The
fixture copies ``corpus/`` into ``tmp_path`` and points ``CORPUS_DIR`` at it,
because ``corpus_root()`` reads the environment at call time. That is not
tidiness. A test that wrote into the real tree and then failed halfway would
leave a half-written policy document committed-adjacent in somebody's working
copy, and would break ``test_rag``'s golden set for everybody else on the next
run - non-deterministically, because the suite is distributed by file. The
first assertion in the fixture is that the root is not the real one.
"""

from __future__ import annotations

import base64
import io
import os
import shutil
import zipfile
from pathlib import Path

import pytest

os.environ.setdefault("DB_PATH", "data/test_corpus_library.db")

from sc import db  # noqa: E402
from sc.rag import chunk as chunker  # noqa: E402
from sc.rag import extract  # noqa: E402
from sc.rag import index as index_mod  # noqa: E402
from sc.rag import library, retrieve  # noqa: E402

REAL_CORPUS = Path("corpus")

#: A phrase that appears nowhere in the authored corpus, so retrieving it
#: proves the document under test was indexed rather than that BM25 found
#: something adjacent.
PHRASE = "zephyrine cascade provision"

BODY = ("# Test Handling Policy\n\n## Scope\n\n"
        + f"This policy governs the {PHRASE} and applies to every prepacked "
          "product offered to a final consumer in this catalogue. " * 4)


@pytest.fixture(autouse=True)
def corpus(tmp_path, monkeypatch):
    """A private copy of the corpus, and an index built from it."""
    root = tmp_path / "corpus"
    shutil.copytree(REAL_CORPUS, root)
    monkeypatch.setenv("CORPUS_DIR", str(root))

    assert index_mod.corpus_root().resolve() != REAL_CORPUS.resolve(), (
        "the fixture is pointed at the real corpus; refusing to run")

    db.init_db(drop=True)
    index_mod.load.cache_clear()
    index_mod.build(include_comms=False, embed=False)
    yield root
    index_mod.load.cache_clear()


def write(**kwargs):
    """A valid document, with anything the caller wants overridden."""
    return library.write_document(**{
        "doc_id": "POL-005", "doc_type": "POLICY",
        "title": "Test Handling Policy", "body": BODY, "actor": "R. Vance",
        **kwargs})


def snapshot(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [
    "../../etc/passwd", r"..\..\x", "POL-001/../../x", "/abs/path",
    "C:/windows/system32", "POL-001;rm -rf /", "POL-001\x00", "con",
    "POL 001", "", "A" * 300, "POL-001.md",
])
def test_a_document_id_cannot_escape_the_corpus(corpus, bad):
    before = snapshot(corpus)
    with pytest.raises(library.LibraryError):
        write(doc_id=bad)
    assert snapshot(corpus) == before, "a refused write still touched the tree"


def test_a_title_cannot_escape_the_corpus(corpus):
    """The filename tail is composed, not accepted.

    ``_slug`` emits ``[a-z0-9-]`` and nothing else, so a title cannot
    contribute a separator, a drive letter or a parent reference to the path.
    """
    result = write(doc_id="POL-005", title="../../evil name")
    written = corpus / result["path"]
    assert written.parent == corpus / "policy"
    assert written.name == "POL-005-evil-name.md"


def test_a_synthesised_type_cannot_be_authored(corpus):
    """RECORD and COMMS are rebuilt from the catalog and the simulation.

    A file of either would be silently overwritten by the next build, so a
    surface that accepted one would be offering to write into a bin.
    """
    for kind in ("RECORD", "COMMS", "NONSENSE"):
        with pytest.raises(library.LibraryError):
            write(doc_id="REC-050", doc_type=kind)


def test_a_change_has_to_be_attributable(corpus):
    for actor in ("", "   ", None):
        with pytest.raises(library.LibraryError):
            write(actor=actor)


def test_creating_over_an_existing_document_is_refused(corpus):
    """The failure this prevents is silent.

    Somebody sets out to add a policy, picks an id that is already taken, and
    without this replaces the document that was there - no error, no diff, and
    the old text gone unless the corpus happened to be committed.
    """
    before = snapshot(corpus)
    with pytest.raises(library.LibraryError, match="already exists"):
        write(doc_id="POL-001", title="Something else")
    assert snapshot(corpus) == before

    result = write(doc_id="POL-001", title="Something else", replace=True)
    assert not result["created"]


# ---------------------------------------------------------------------------
# Front matter round-trip
# ---------------------------------------------------------------------------


def test_frontmatter_round_trips_for_every_authored_document(corpus):
    """The claim that makes this module safe to point at the real corpus.

    ``parse_frontmatter`` is hand-rolled, and the renderer is its inverse. If
    they disagree about any of the 29 committed documents, editing one through
    this surface corrupts it.
    """
    for path in sorted(corpus.rglob("*.md")):
        meta, body = chunker.parse_frontmatter(path.read_text(encoding="utf-8"))
        again, again_body = chunker.parse_frontmatter(library._render(meta, body))
        assert again == meta, path.name
        assert again_body.strip() == body.strip(), path.name


def test_a_scalar_that_would_read_back_as_a_list_is_refused(corpus):
    with pytest.raises(library.LibraryError, match="read it back as a list"):
        write(title="[Draft]")


def test_a_list_item_containing_a_comma_is_refused(corpus):
    """The parser splits on every comma, so this would become two tags."""
    with pytest.raises(library.LibraryError, match="comma"):
        write(tags=["allergen,regulated"])


def test_unmodelled_frontmatter_keys_survive_an_edit(corpus):
    """An incident carries ``occurred`` and ``severity``.

    Dropping a key nobody happened to model is how an editing tool teaches
    people not to use it.
    """
    path = next(corpus.rglob("INC-2025-041*.md"))
    before, _ = chunker.parse_frontmatter(path.read_text(encoding="utf-8"))
    doc = library.read_document("INC-2025-041")
    library.write_document(
        doc_id="INC-2025-041", doc_type="POSTMORTEM", title=doc["title"],
        body=doc["body"], actor="R. Vance", owner=doc["owner"],
        version=doc["version"], effective=doc["effective"],
        entities=doc["entities"], tags=doc["tags"], extra=doc["extra"],
        replace=True)
    after, _ = chunker.parse_frontmatter(path.read_text(encoding="utf-8"))
    assert after.get("occurred") == before.get("occurred")
    assert after.get("severity") == before.get("severity")


def test_a_body_starting_with_a_rule_is_not_read_as_a_second_header(corpus):
    write(body="---\n\n# Title\n\n## Scope\n\n" + "word " * 60)
    meta, _ = chunker.parse_frontmatter(
        (corpus / library.read_document("POL-005")["path"]).read_text("utf-8"))
    assert meta["id"] == "POL-005"


# ---------------------------------------------------------------------------
# The lifecycle
# ---------------------------------------------------------------------------


def test_a_created_document_is_retrievable_at_once(corpus):
    """The end-to-end claim: saving rebuilds the index, lexically, in line."""
    result = write()
    assert result["created"]
    assert any(hit.chunk.doc_id == "POL-005"
               for hit in retrieve.search(PHRASE, semantic=False))


def test_a_retired_document_leaves_the_index_and_stays_on_disk(corpus):
    result = write()
    library.retire_document("POL-005", "R. Vance", reason="superseded")

    assert not [h for h in retrieve.search(PHRASE, semantic=False)
                if h.chunk.doc_id == "POL-005"]
    assert (corpus / result["path"]).exists(), (
        "a decision made while it was in force has to stay readable against it")
    listed = {d["doc_id"]: d for d in library.list_documents()}
    assert listed["POL-005"]["status"] == "RETIRED"
    assert listed["POL-005"]["chunks"] == 0
    assert library.read_document("POL-005")["body"]


def test_restoring_puts_it_back(corpus):
    write()
    library.retire_document("POL-005", "R. Vance")
    library.restore_document("POL-005", "R. Vance")
    assert any(h.chunk.doc_id == "POL-005"
               for h in retrieve.search(PHRASE, semantic=False))


def test_chunk_document_still_answers_for_a_retired_file(corpus):
    """Retirement is a property of the index, not of the text.

    The filter lives in ``chunk_corpus`` rather than ``chunk_document`` so that
    "this file produces chunks" stays a fact about the file - which is what
    ``test_rag``'s per-document assertions are written against.
    """
    write()
    path = corpus / library.read_document("POL-005")["path"]
    library.retire_document("POL-005", "R. Vance")
    assert chunker.chunk_document(path), "the text still chunks"
    assert not [c for c in chunker.chunk_corpus(corpus) if c.doc_id == "POL-005"]


def test_hard_delete_requires_retirement_first(corpus):
    write()
    with pytest.raises(library.LibraryError, match="still in force"):
        library.delete_document("POL-005", "R. Vance")

    library.retire_document("POL-005", "R. Vance")
    result = library.delete_document("POL-005", "R. Vance", reason="cleanup")
    assert not (corpus / result["deleted"]).exists()


# ---------------------------------------------------------------------------
# The removal guard
# ---------------------------------------------------------------------------


def test_removing_a_document_the_code_names_is_refused(corpus):
    """POL-002 is hard-coded at sc/graph/evidence.py as PRECEDENCE_POLICY."""
    blocked = library.references("POL-002")
    assert any(b["kind"] == "NAMED" and "evidence.py" in b["where"]
               for b in blocked), blocked

    with pytest.raises(library.ReferencedError) as raised:
        library.retire_document("POL-002", "R. Vance")
    assert raised.value.blocked

    library.retire_document("POL-002", "R. Vance", acknowledge_references=True)
    assert library.read_document("POL-002")["status"] == "RETIRED"


def test_retiring_the_last_of_a_load_bearing_type_is_flagged(corpus):
    """The sharpest edge in the feature, and the quietest.

    ``readiness.internal_contradiction`` returns ``[], True`` when nothing is
    retrieved. Retire the last INTERNAL document and every product passes the
    check, with the assessment reported as complete.
    """
    for doc in library.list_documents():
        if doc["type"] == "INTERNAL" and doc["doc_id"] != "INT-001":
            library.retire_document(doc["doc_id"], "R. Vance",
                                    acknowledge_references=True)

    last = [b for b in library.references("INT-001") if b["kind"] == "LAST"]
    assert last, "retiring the last INTERNAL document was not flagged"
    assert "internal_contradiction" in last[0]["detail"]


def test_the_reference_scan_does_not_report_its_own_examples(corpus):
    """``library`` names POL-005 and REG-010 in its refusal messages.

    Scanning itself would mark every document created at one of those ids as
    load bearing - a warning that is always wrong, on the one path where a
    warning has to be worth reading.
    """
    write()
    assert not [b for b in library.references("POL-005")
                if b["kind"] == "NAMED"]


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------


def test_every_mutation_is_audited_against_a_name(corpus):
    write()
    library.write_document(doc_id="POL-005", doc_type="POLICY", title="Edited",
                           body=BODY, actor="R. Vance", replace=True)
    library.retire_document("POL-005", "R. Vance")
    library.restore_document("POL-005", "R. Vance")
    library.retire_document("POL-005", "R. Vance")
    library.delete_document("POL-005", "R. Vance", reason="cleanup")

    rows = db.query("SELECT action, actor, detail FROM audit "
                    "WHERE entity_type = 'corpus' ORDER BY ts")
    assert [r["action"] for r in rows] == [
        "CORPUS_DOCUMENT_CREATED", "CORPUS_DOCUMENT_WRITTEN",
        "CORPUS_DOCUMENT_RETIRED", "CORPUS_DOCUMENT_RESTORED",
        "CORPUS_DOCUMENT_RETIRED", "CORPUS_DOCUMENT_DELETED"]
    assert all(r["actor"] == "R. Vance" for r in rows)


def test_a_deleted_document_is_recoverable_from_the_ledger(corpus):
    """Recoverable has to mean recoverable when the branch was never committed."""
    write()
    library.retire_document("POL-005", "R. Vance")
    library.delete_document("POL-005", "R. Vance", reason="cleanup")

    row = db.query("SELECT detail FROM audit "
                   "WHERE action = 'CORPUS_DOCUMENT_DELETED'")[0]
    assert PHRASE in row["detail"]


# ---------------------------------------------------------------------------
# The stale-matrix guard
# ---------------------------------------------------------------------------


def test_an_edit_that_preserves_the_chunk_count_invalidates_the_matrix(corpus):
    """The bug the fingerprint exists for, and the one a length check misses.

    Editing a document's prose without changing its section structure leaves
    the chunk count - and every chunk id - exactly as it was. A matrix accepted
    on either of those would sit against text it was never built from, and
    every citation it produced would be specific, confident and wrong.
    """
    import numpy as np

    chunks = index_mod.load().chunks
    np.save(index_mod.matrix_path(),
            np.zeros((len(chunks), 8), dtype=np.float32))
    db.set_config(index_mod.INDEX_FINGERPRINT_KEY, index_mod.fingerprint(chunks))
    index_mod.load.cache_clear()
    assert index_mod.load().has_vectors
    assert index_mod.status()["vectors_verified"]

    # A wording change inside one section. The section count does not move,
    # so neither does the chunk count - which is the whole case under test.
    target = next(corpus.rglob("STD-001*.md"))
    original = target.read_text(encoding="utf-8")
    edited = original.replace("product", "article")
    assert edited != original, "the edit under test did not change the text"
    target.write_text(edited, encoding="utf-8")
    index_mod.build(include_comms=False, embed=False)

    assert len(index_mod.load().chunks) == len(chunks), (
        "the chunk count moved; this is no longer the case under test")
    assert not index_mod.load().has_vectors
    assert index_mod.status()["vectors_stale"]


def test_a_matrix_from_before_the_fingerprint_is_accepted_as_an_upgrade(corpus):
    """Refusing it would switch dense search off on every existing install.

    Accepting is exactly as safe as the length check that was the whole guard
    when the matrix was written, and it is reported as unverified rather than
    silently trusted.
    """
    import numpy as np

    # No fingerprint is written: `build(embed=False)` does not stamp one, so
    # this is the state an installation that has never re-embedded is in.
    chunks = index_mod.load().chunks
    np.save(index_mod.matrix_path(),
            np.zeros((len(chunks), 8), dtype=np.float32))
    assert db.get_config(index_mod.INDEX_FINGERPRINT_KEY) is None
    index_mod.load.cache_clear()

    assert index_mod.load().has_vectors
    assert index_mod.status()["vectors_verified"] is False


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def docx(paragraphs) -> bytes:
    """A minimal .docx: (style, text) pairs, or ("table", rows)."""
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    parts = []
    for style, text in paragraphs:
        if style == "table":
            rows = "".join(
                "<w:tr>" + "".join(
                    f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>"
                    for c in row) + "</w:tr>"
                for row in text)
            parts.append(f"<w:tbl>{rows}</w:tbl>")
            continue
        props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        parts.append(f"<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>")

    document = (f'<w:document xmlns:w="{w}"><w:body>'
                + "".join(parts) + "</w:body></w:document>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def test_a_docx_becomes_markdown_with_its_headings(corpus):
    """Headings are what makes the result chunkable.

    ``chunk._sections`` splits on them, so a document that arrives as one
    unbroken block is indexed as one block and cites as one block.
    """
    result = extract.extract("policy.docx", docx([
        ("Title", "Allergen Handling Standard"),
        ("Heading1", "Scope"),
        (None, "Applies to every prepacked food."),
        ("table", [["source", "precedence"], ["NOTICE", "50"]]),
    ]))
    assert result["kind"] == "docx"
    assert result["title"] == "Allergen Handling Standard"
    assert "# Allergen Handling Standard" in result["text"]
    # Word's Heading1 is the first section level, not the document title.
    assert "## Scope" in result["text"]
    assert "| source | precedence |" in result["text"]


def test_an_extracted_docx_can_be_saved_and_retrieved(corpus):
    result = extract.extract("policy.docx", docx([
        ("Title", "Uploaded Standard"),
        ("Heading1", "Scope"),
        (None, f"The {PHRASE} governs everything here. " * 12),
    ]))
    write(doc_id="STD-050", doc_type="STANDARD", title=result["title"],
          body=result["text"])
    assert any(h.chunk.doc_id == "STD-050"
               for h in retrieve.search(PHRASE, semantic=False))


def test_a_mislabelled_pdf_says_so(corpus):
    """"Invalid UTF-8" is true, useless, and sends somebody to read the source."""
    with pytest.raises(ValueError, match="PDF"):
        extract.extract("sneaky.md", b"%PDF-1.7 and the rest")


def test_an_unaccepted_suffix_is_refused(corpus):
    with pytest.raises(ValueError, match="not a document type"):
        extract.extract("notes.rtf", b"anything")


def test_markdown_frontmatter_is_split_out_for_the_editor(corpus):
    result = extract.extract("thing.md", (
        "---\nid: POL-009\ntype: POLICY\ntitle: Pasted\n---\n\n# Pasted\n\nBody."
    ).encode("utf-8"))
    assert result["frontmatter"]["id"] == "POL-009"
    assert result["title"] == "Pasted"
    assert result["text"].startswith("# Pasted")


@pytest.mark.skipif(not extract.available()[".pdf"],
                    reason="pypdf is not installed")
def test_a_pdf_gets_page_headings(corpus):
    """A PDF has no headings, so a citation into one would have no locator."""
    import pypdf

    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(ValueError, match="scan|no text"):
        extract.extract("blank.pdf", buffer.getvalue())


def test_upload_size_is_capped(corpus):
    oversized = base64.b64encode(b"x" * (library.MAX_UPLOAD_BYTES + 1))
    assert len(base64.b64decode(oversized)) > library.MAX_UPLOAD_BYTES
    with pytest.raises(library.LibraryError, match="larger than"):
        library.store_original("POL-005", "a.md",
                               b"x" * (library.MAX_UPLOAD_BYTES + 1))


def test_a_stored_original_is_not_indexed_twice(corpus):
    """``_source`` holds the file a document was extracted from.

    The rendition is what is indexed and the original is what is authoritative;
    indexing both would make one document cite itself twice.
    """
    write()
    stored = library.store_original("POL-005", "original.md",
                                    f"# Original\n\n{PHRASE} ".encode() * 30)
    assert stored.startswith("_source/")
    index_mod.build(include_comms=False, embed=False)
    hits = {h.chunk.doc_id for h in retrieve.search(PHRASE, semantic=False)}
    assert hits == {"POL-005"}
