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

import logging

import os
from datetime import datetime
from pathlib import Path

import numpy as np

from sc import db
from sc.contracts import DocChunk
from sc.llm import gateway
from sc.rag import chunk as chunker

EMBED_BATCH = 32
INDEX_VERSION_KEY = "rag_index_built_at"
INDEX_MODEL_KEY = "rag_index_model"


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
        rows.extend(gateway.embed(texts[start:start + EMBED_BATCH]))

    matrix = np.asarray(rows, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.clip(norms, 1e-9, None)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


class Index:
    """Chunks, their embedding matrix, and a lexical index over the same text."""

    def __init__(self, chunks: list[DocChunk], vectors: np.ndarray | None) -> None:
        from sc.rag.bm25 import BM25

        self.chunks = chunks
        self.vectors = vectors
        self.bm25 = BM25([c.text for c in chunks])
        self.by_id = {c.id: i for i, c in enumerate(chunks)}

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
    path = matrix_path()
    if chunks and path.exists():
        try:
            candidate = np.load(path)
            # A stale matrix from a previous corpus would misalign chunk ids
            # with vectors and return confidently wrong citations.
            if len(candidate) == len(chunks):
                vectors = candidate
        except Exception:
            vectors = None

    return Index(chunks, vectors)


def status() -> dict:
    index = load()
    return {
        "chunks": len(index),
        "documents": len({c.doc_id for c in index.chunks}),
        "vectors": bool(index.has_vectors),
        "dimensions": int(index.vectors.shape[1]) if index.has_vectors else 0,
        "built_at": db.get_config(INDEX_VERSION_KEY),
        "embed_model": db.get_config(INDEX_MODEL_KEY),
        "by_type": _counts(index.chunks),
    }
