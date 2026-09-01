"""Build and load the retrieval index.

Two artefacts, both derived and both disposable:

*   ``doc_chunks`` in SQLite - the chunk text and metadata, with ``row_index``
    pointing at a row of the embedding matrix.
*   ``embeddings.npy`` - a dense float32 matrix, one row per chunk.

No vector database. The corpus is a few hundred chunks; the whole matrix is
around a megabyte and a similarity search is one matrix multiply. An
approximate-nearest-neighbour index would add a dependency, a failure mode and
an approximation, in exchange for speeding up an operation that already takes
under a millisecond.

Embeddings are produced through the LiteLLM gateway like every other model
call, so the same alias, key handling and cost accounting apply.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from datetime import date

import os
from datetime import datetime
from pathlib import Path

import numpy as np

from sc import db
from sc.contracts import DocChunk
from sc.llm import gateway
from sc.rag import chunk as chunker

#: Serialises rebuilds. Two concurrent builds race on ``np.save`` while
#: ``doc_chunks`` ends up holding the other one's rows - which is precisely the
#: misalignment the fingerprint below exists to detect, arriving by a route the
#: fingerprint cannot prevent. FastAPI runs ``def`` routes in a threadpool, so
#: two reindex requests in flight is an ordinary Tuesday, not a stress test.
_BUILD_LOCK = threading.Lock()

EMBED_BATCH = 32
INDEX_VERSION_KEY = "rag_index_built_at"
INDEX_MODEL_KEY = "rag_index_model"
#: Identity of the chunk list the matrix on disk was built from. Written only
#: when a matrix is written, and checked on every load.
INDEX_FINGERPRINT_KEY = "rag_index_fingerprint"


def corpus_root() -> Path:
    return Path(os.environ.get("CORPUS_DIR", "corpus"))


def matrix_path() -> Path:
    """Where the embedding matrix lives, derived from the database path.

    The matrix and the ``doc_chunks`` rows are two halves of one artefact -
    row N of the matrix is only meaningful against the chunk that claims
    ``row_index = N``. Naming the file after its database keeps them together,
    so a test run cannot silently load the production matrix against its own
    chunks and return confidently mismatched citations.
    """
    database = db.db_path()
    return database.with_suffix(".embeddings.npy")


def fingerprint(chunks: list[DocChunk]) -> str:
    """Identity of a chunk list, for pairing it with an embedding matrix.

    Covers the text, not only the ids, and that distinction is the whole point.
    A chunk id is ``{doc_id}#{ordinal}``, so correcting a sentence inside a
    document leaves every id in the corpus exactly as it was - and an id-only
    hash would wave the old matrix through to sit against text it was never
    built from. Row N would still be *a* vector for chunk N, just the wrong
    one, and the citation that follows is specific, confident and wrong.

    Reading the text costs a few milliseconds over a corpus this size, once
    per process, behind an ``lru_cache``. The failure it rules out is silent.
    """
    digest = hashlib.sha256()
    for c in chunks:
        digest.update(c.id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(c.text.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


# ---------------------------------------------------------------------------
log = logging.getLogger(__name__)


# Build
# ---------------------------------------------------------------------------


def collect_chunks(include_comms: bool = True) -> list[DocChunk]:
    from sc.state import baseline as baseline_mod

    chunks = chunker.chunk_corpus(corpus_root())
    if include_comms:
        comms_dir = baseline_mod.data_dir() / "comms"
        if comms_dir.exists():
            chunks.extend(chunker.chunk_comms(comms_dir))

    # The catalog's own held values, rebuilt with the index rather than carried
    # beside it. A record passage that has fallen behind a correction is a
    # citation supporting the wrong answer, which is worse than no passage.
    #
    # Guarded: the corpus is committed and always readable, the catalog is
    # generated and might not be. An index missing its record passages is a
    # narrower index; an index that will not build is no index.
    try:
        chunks.extend(chunker.chunk_records(baseline_mod.get()))
    except Exception:  # noqa: BLE001 - a narrower index beats none
        log.debug("no catalog to index records from", exc_info=True)
    return chunks


def build(include_comms: bool = True, embed: bool = True) -> dict:
    """Chunk the corpus, embed it, and persist both artefacts.

    ``embed=False`` builds the lexical half only. That is not a degraded mode
    to be ashamed of - BM25 alone answers identifier queries well, so the
    system still retrieves usefully when the gateway is unreachable.
    """
    with _BUILD_LOCK:
        return _build(include_comms, embed)


def _build(include_comms: bool, embed: bool) -> dict:
    chunks = collect_chunks(include_comms)
    if not chunks:
        return {"error": "no documents found", "root": str(corpus_root())}

    vectors: np.ndarray | None = None
    embed_error: str | None = None

    if embed:
        try:
            vectors = _embed_all([c.text for c in chunks])
        except Exception as exc:  # gateway down, no key, rate limited
            embed_error = str(exc)[:300]

    with db.transaction() as conn:
        conn.execute("DELETE FROM doc_chunks")
        conn.executemany(
            "INSERT INTO doc_chunks (id, doc_id, doc_type, title, text, ordinal,"
            " metadata, row_index) VALUES (?,?,?,?,?,?,?,?)",
            [(c.id, c.doc_id, c.doc_type, c.title, c.text, c.ordinal,
              db.dumps(c.metadata), i) for i, c in enumerate(chunks)],
        )

    if vectors is not None:
        matrix_path().parent.mkdir(parents=True, exist_ok=True)
        np.save(matrix_path(), vectors)
        db.set_config(INDEX_MODEL_KEY, gateway.embed_model())
        db.set_config(INDEX_FINGERPRINT_KEY, fingerprint(chunks))
    db.set_config(INDEX_VERSION_KEY, datetime.now().isoformat())
    load.cache_clear()

    return {
        "chunks": len(chunks),
        "documents": len({c.doc_id for c in chunks}),
        "embedded": vectors is not None,
        "dimensions": int(vectors.shape[1]) if vectors is not None else 0,
        "model": gateway.embed_model() if vectors is not None else None,
        "embed_error": embed_error,
        "by_type": _counts(chunks),
    }


def _counts(chunks: list[DocChunk]) -> dict:
    out: dict[str, int] = {}
    for c in chunks:
        out[c.doc_type] = out.get(c.doc_type, 0) + 1
    return out


def _embed_all(texts: list[str]) -> np.ndarray:
    """Embed in batches and L2-normalise.

    Normalising once at build time turns every later cosine similarity into a
    plain dot product, which is what makes search a single matmul.
    """
    rows: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        rows.extend(gateway.embed(texts[start:start + EMBED_BATCH],
                                  agent="retrieval.index"))

    matrix = np.asarray(rows, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.clip(norms, 1e-9, None)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def effective_date(chunk: DocChunk) -> date | None:
    """When this passage's document commences, if it says.

    ``None`` covers both "no date" and "a date that will not parse", and the
    caller treats them the same way - as always in force. A typo in front
    matter should cost a document its commencement date, not its presence.
    """
    raw = str(chunk.metadata.get("effective", "")).strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


class Index:
    """Chunks, their embedding matrix, and a lexical index over the same text."""

    def __init__(self, chunks: list[DocChunk], vectors: np.ndarray | None,
                 vectors_stale: bool = False,
                 vectors_verified: bool = False) -> None:
        from sc.rag.bm25 import BM25

        self.chunks = chunks
        self.vectors = vectors
        #: A matrix exists on disk and was refused. Distinct from "never
        #: embedded": the first is a rebuild away from correct, the second
        #: needs the gateway. The UI has to say which.
        self.vectors_stale = vectors_stale
        #: The matrix in use carries a fingerprint matching these chunks.
        #: False for one accepted on absence - in use, but on trust.
        self.vectors_verified = vectors_verified
        self.bm25 = BM25([c.text for c in chunks])
        self.by_id = {c.id: i for i, c in enumerate(chunks)}
        #: Commencement date per row, or None for a passage that has no date
        #: and is therefore always in force.
        #:
        #: Precomputed rather than read per query. `retrieve._filter` is a
        #: linear scan over every chunk, so doing the dict lookup, the strip
        #: and the parse inside it cost 0.6ms of a 1.0ms lexical search -
        #: measured, and most of the search. Here it is one list index.
        self.effective = [effective_date(c) for c in chunks]

    @property
    def has_vectors(self) -> bool:
        return self.vectors is not None and len(self.vectors) == len(self.chunks)

    def __len__(self) -> int:
        return len(self.chunks)


from functools import lru_cache  # noqa: E402


@lru_cache(maxsize=1)
def load() -> Index:
    """Process-wide cached index. Cleared on rebuild."""
    rows = db.query("SELECT * FROM doc_chunks ORDER BY row_index")
    chunks = [
        DocChunk(id=r["id"], doc_id=r["doc_id"], doc_type=r["doc_type"],
                 title=r["title"], text=r["text"], ordinal=r["ordinal"],
                 metadata=db.loads(r["metadata"]))
        for r in rows
    ]

    vectors = None
    stale = False
    verified = False
    path = matrix_path()
    if chunks and path.exists():
        try:
            candidate = np.load(path)
            stamped = db.get_config(INDEX_FINGERPRINT_KEY)
            current = fingerprint(chunks)
            # A stale matrix from a previous corpus would misalign chunk ids
            # with vectors and return confidently wrong citations. The length
            # is a cheap pre-filter; the fingerprint is what catches an edit
            # that left the chunk count alone.
            #
            # Absence is treated as an upgrade rather than a mismatch. A matrix
            # built before this check existed passed the length test that was
            # the whole guard at the time, so accepting it is exactly as safe
            # as yesterday - whereas refusing it would silently switch off
            # dense retrieval on every installation that had not reindexed,
            # which is a worse failure than the one being fixed and a much
            # quieter one. It is reported as unverified instead.
            if len(candidate) == len(chunks) and stamped in (None, current):
                vectors = candidate
                verified = stamped == current
            else:
                stale = True
        except Exception:
            vectors = None
            stale = True

    return Index(chunks, vectors, vectors_stale=stale, vectors_verified=verified)


def status() -> dict:
    index = load()
    return {
        "chunks": len(index),
        "documents": len({c.doc_id for c in index.chunks}),
        "vectors": bool(index.has_vectors),
        "dimensions": int(index.vectors.shape[1]) if index.has_vectors else 0,
        "vectors_stale": bool(index.vectors_stale),
        "vectors_verified": bool(index.vectors_verified),
        "built_at": db.get_config(INDEX_VERSION_KEY),
        "embed_model": db.get_config(INDEX_MODEL_KEY),
        "by_type": _counts(index.chunks),
    }
