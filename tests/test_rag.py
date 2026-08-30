"""Retrieval pipeline: chunking, BM25, filtering and hybrid fusion.

The lexical and structural tests run offline and always. The semantic tests
need an embedding matrix, so they skip when the index was built without one -
CI and a laptop with no gateway still get useful coverage rather than a wall of
errors.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("DB_PATH", "data/test_rag.db")

from sc import db  # noqa: E402
from sc.rag import chunk as chunker  # noqa: E402
from sc.rag import index as index_mod  # noqa: E402
from sc.rag import retrieve  # noqa: E402
from sc.rag.bm25 import BM25, tokenize  # noqa: E402

CORPUS = Path("corpus")
MATRIX = Path("data/test_rag.embeddings.npy")


@pytest.fixture(autouse=True)
def built_index():
    """Rebuild the lexical index for each test.

    The default run must not need a network, so embeddings are skipped; the
    semantic tests below skip themselves when no matrix is present.
    """
    db.init_db(drop=True)
    index_mod.load.cache_clear()
    index_mod.build(include_comms=True, embed=False)
    yield


def _has_vectors() -> bool:
    """Checked at collection time, before any fixture has run - so it looks for
    the matrix file rather than asking a database that does not exist yet."""
    return MATRIX.exists()


# ---------------------------------------------------------------------------
# Tokenisation - where identifier precision comes from
# ---------------------------------------------------------------------------


def test_identifiers_survive_tokenisation():
    """VAR-01B must not collapse into "var" + "01b".

    If it does, every variant id becomes the same two tokens and lexical search
    stops being able to tell VAR-01A from VAR-01B - which is the single
    distinction the whole finale turns on.
    """
    tokens = tokenize("Variant VAR-01B from SUP-01 rejected as MKA-4102")
    assert "var-01b" in tokens
    assert "sup-01" in tokens
    assert "mka-4102" in tokens


def test_identifier_parts_are_also_indexed():
    """A search for "VAR" alone should still find VAR-01B."""
    tokens = tokenize("VAR-01B")
    assert "var-01b" in tokens and "var" in tokens


def test_stopwords_are_dropped():
    assert "the" not in tokenize("the supplier and the channel")


def test_bm25_separates_similar_identifiers():
    """The property embeddings cannot deliver."""
    index = BM25([
        "VAR-01A AeroPure 300 is rated at 45 W and remains low-energy",
        "VAR-01B AeroPure 300 Max is rated at 65 W and loses the claim",
    ])
    ranked = index.rank("VAR-01B", top_k=2)
    assert ranked and ranked[0][0] == 1


def test_bm25_returns_nothing_for_absent_terms():
    index = BM25(["a document about shelf-edge labels"])
    assert index.rank("cryptocurrency") == []


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def test_frontmatter_is_parsed_including_lists():
    meta, body = chunker.parse_frontmatter(
        "---\nid: STD-9\ntype: STANDARD\nentities: [SUP-01, VAR-01B]\n---\n# Title\n")
    assert meta["id"] == "STD-9"
    assert meta["entities"] == ["SUP-01", "VAR-01B"]
    assert body.startswith("# Title")


def test_chunks_carry_document_and_heading_context():
    """A chunk must be findable on its own, so it is prefixed with where it
    came from rather than relying on surrounding context that is not indexed."""
    chunks = chunker.chunk_document(
        CORPUS / "standard" / "STD-001-content-standards.md")
    assert chunks
    for c in chunks:
        assert c.text.startswith("Product Content Standards")
        assert c.doc_id == "STD-001"
        assert c.doc_type == "STANDARD"


def test_every_corpus_document_produces_chunks():
    for path in sorted(CORPUS.rglob("*.md")):
        assert chunker.chunk_document(path), f"{path} produced no chunks"


def test_incident_metadata_is_retained():
    chunks = chunker.chunk_document(
        CORPUS / "incident" / "INC-2025-041-kettle-wattage-mislabel.md")
    assert chunks[0].doc_type == "POSTMORTEM"
    assert "PRD-04" in chunks[0].metadata["entities"]


# ---------------------------------------------------------------------------
# Index and filtering
# ---------------------------------------------------------------------------


def test_index_covers_the_whole_corpus():
    status = index_mod.status()
    assert status["chunks"] > 30
    for doc_type in ("STANDARD", "CHANNEL", "POLICY", "POSTMORTEM"):
        assert status["by_type"].get(doc_type, 0) > 0


def test_correspondence_is_excluded_by_default():
    """An email is evidence, not guidance. It should not answer "what is the
    standard" unless the caller asks for the mailbox."""
    default = retrieve.search("supplier correction", top_k=8)
    assert all(r.chunk.doc_type != "COMMS" for r in default)

    with_comms = retrieve.search("supplier correction", top_k=8,
                                 include_comms=True)
    assert len(with_comms) >= len(default)


def test_doc_type_filter_restricts_results():
    hits = retrieve.search("prior channel rejection", top_k=5,
                           doc_types=["POSTMORTEM"])
    assert hits
    assert all(r.chunk.doc_type == "POSTMORTEM" for r in hits)


def test_entity_filter_matches_header_or_body():
    hits = retrieve.search("wattage", top_k=5, entities=["VAR-01B"])
    assert hits
    for r in hits:
        listed = [str(e).upper() for e in r.chunk.metadata.get("entities", [])]
        assert "VAR-01B" in listed or "VAR-01B" in r.chunk.text.upper()


def test_filters_that_match_nothing_return_nothing():
    assert retrieve.search("correction", entities=["NO-SUCH-ENTITY-9999"]) == []


# ---------------------------------------------------------------------------
# Golden set - lexical half
# ---------------------------------------------------------------------------


LEXICAL_GOLDEN = [
    ("MKA-4102 required attribute missing or wrong type",
     {"CHN-002", "INC-2025-041"}),
    ("MKB-2208 ingredient order does not match declared list",
     {"CHN-003", "INC-2025-063"}),
    ("source precedence LABEL_ARTWORK SPREADSHEET", {"POL-002"}),
    ("CH-PRINT freeze window stale version", {"CHN-004", "INC-2026-002"}),
    ("claim substantiation ultra-quiet low-energy", {"STD-001"}),
]


@pytest.mark.parametrize("query,expected", LEXICAL_GOLDEN)
def test_lexical_golden_set(query, expected):
    """These queries name things. BM25 alone must find them."""
    hits = retrieve.search(query, top_k=4, semantic=False, lexical=True)
    found = {r.chunk.doc_id for r in hits}
    assert found & expected, f"{query!r} returned {found}, expected one of {expected}"


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


def test_citations_are_followable():
    """An editor must be able to open the exact section a claim came from."""
    hits = retrieve.search(
        "when may a correction be applied inside the print freeze window",
        top_k=3)
    for c in retrieve.cite(hits):
        assert c["chunk_id"] and c["doc_id"] and c["source"]
        assert Path(c["source"]).exists()
        assert c["excerpt"]


def test_document_fetch_returns_ordered_chunks():
    chunks = retrieve.get_document("STD-001")
    assert chunks
    assert [c.ordinal for c in chunks] == sorted(c.ordinal for c in chunks)


# ---------------------------------------------------------------------------
# Semantic half - only when an embedding matrix exists
# ---------------------------------------------------------------------------


needs_vectors = pytest.mark.skipif(
    not _has_vectors(),
    reason="no embedding matrix; run scripts/build_index.py with the gateway up",
)

SEMANTIC_GOLDEN = [
    ("can we still change the catalogue before it goes to the printer",
     {"CHN-004", "INC-2026-002"}),
    ("the note tells us the wrong number but not which model it is about",
     {"INC-2025-041", "POL-002"}),
    ("do we still get to say no peanuts after the factory changed",
     {"POL-001", "INC-2025-058"}),
    ("how long is a headline allowed to be on our own site",
     {"CHN-001", "STD-001"}),
    ("who signs off on going back to the manufacturer", {"POL-003"}),
]


@needs_vectors
@pytest.mark.parametrize("query,expected", SEMANTIC_GOLDEN)
def test_hybrid_golden_set(query, expected):
    """Paraphrase queries that share little vocabulary with their answer."""
    hits = retrieve.search(query, top_k=3)
    found = {r.chunk.doc_id for r in hits}
    assert found & expected, f"{query!r} returned {found}, expected one of {expected}"


@needs_vectors
def test_hybrid_beats_lexical_alone_on_paraphrase():
    query = "the note tells us the wrong number but not which model it is about"
    lexical_only = {r.chunk.doc_id for r in
                    retrieve.search(query, top_k=3, semantic=False)}
    hybrid = {r.chunk.doc_id for r in retrieve.search(query, top_k=3)}
    precedent = {"INC-2025-041"}
    assert hybrid & precedent and not (lexical_only & precedent)
