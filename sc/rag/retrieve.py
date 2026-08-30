"""Hybrid retrieval: dense semantic search fused with BM25.

The two retrievers fail in opposite directions on this corpus.

Embeddings find the right *idea* when the query does not share vocabulary with
the document - "can we still change the catalogue" finds the freeze window
without the word "freeze" appearing. But they cannot reliably separate VAR-01A
from VAR-01B, which sit almost on top of each other in vector space and have
opposite answers to the only question that matters about them.

BM25 has exactly the opposite profile: perfect on identifiers, blind to
paraphrase.

Fusion is Reciprocal Rank Fusion. RRF combines *ranks* rather than scores,
which sidesteps the fact that a cosine similarity of 0.82 and a BM25 score of
11.4 are not comparable quantities and cannot be usefully averaged or
normalised against each other.
"""

from __future__ import annotations

import numpy as np

from sc.contracts import DocChunk, RetrievedChunk
from sc.llm import gateway
from sc.rag import index as index_mod

# RRF damping. 60 is the value from the original TREC work; it is deliberately
# large so that the difference between rank 1 and rank 2 is modest and a single
# retriever cannot dominate the fused ordering.
RRF_K = 60

CANDIDATES = 24  # per retriever, before fusion

# Fusion weights. Semantic is favoured slightly because paraphrase is the
# common case - editors ask "can we still change the catalogue", not "CH-PRINT
# freeze window". BM25 keeps enough weight to win identifier queries,
# where it ranks the right document first and a modest discount cannot
# dislodge it. Tuned against the golden set in tests/test_rag.py; change these
# and run it.
SEMANTIC_WEIGHT = 1.0
LEXICAL_WEIGHT = 0.7


# What a default search reads. Correspondence is excluded and opt-in; the
# record type is included because a question about a product should find what
# the catalog holds about it without the caller having to ask twice.
REFERENCE_TYPES = ["STANDARD", "CHANNEL", "POLICY", "POSTMORTEM",
                   "REGULATION", "INTERNAL", "MARKET", "RECORD"]


def search(
    query: str,
    top_k: int = 6,
    doc_types: list[str] | None = None,
    entities: list[str] | None = None,
    tags: list[str] | None = None,
    exclude_docs: list[str] | None = None,
    semantic: bool = True,
    lexical: bool = True,
    include_comms: bool = False,
    include_unscoped: bool = False,
) -> list[RetrievedChunk]:
    """Retrieve chunks, filtered then fused.

    Filters are applied *before* ranking rather than after, so a narrow filter
    still returns a full result set instead of whatever survives from a
    globally-ranked top 20.

    Correspondence is excluded unless asked for. An email is evidence about one
    situation, not guidance on what to do, and the two answer different
    questions. Emails are also short, which flatters BM25's length
    normalisation - left in the pool they crowd out the playbook that actually
    answers the query. "Search the mailbox" is a deliberate act, so
    ``include_comms`` is opt-in.
    """
    index = index_mod.load()
    if not len(index):
        return []

    if doc_types is None:
        doc_types = REFERENCE_TYPES + (["COMMS"] if include_comms else [])

    allowed = _filter(index, doc_types, entities, tags, exclude_docs,
                      include_unscoped)
    if not allowed:
        return []

    rankings: list[tuple[list[int], float]] = []

    if lexical:
        lexical_hits = index.bm25.rank(query, CANDIDATES, allowed)
        rankings.append(([i for i, _ in lexical_hits], LEXICAL_WEIGHT))

    if semantic and index.has_vectors:
        try:
            rankings.append((_semantic(index, query, allowed), SEMANTIC_WEIGHT))
        except Exception:
            # Gateway unreachable mid-demo: lexical results still stand rather
            # than the whole retrieval failing.
            pass

    if not rankings:
        return []

    fused = _rrf(rankings)
    out: list[RetrievedChunk] = []
    for position, (row, score) in enumerate(fused[:top_k]):
        out.append(RetrievedChunk(chunk=index.chunks[row], score=round(score, 6)))
    return out


def _semantic(index, query: str, allowed: set[int]) -> list[int]:
    vector = np.asarray(gateway.embed([query])[0], dtype=np.float32)
    vector /= max(float(np.linalg.norm(vector)), 1e-9)

    # Vectors are normalised at build time, so the dot product is the cosine.
    similarity = index.vectors @ vector

    mask = np.full(len(similarity), -np.inf, dtype=np.float32)
    rows = np.fromiter(allowed, dtype=np.int64, count=len(allowed))
    mask[rows] = similarity[rows]

    take = min(CANDIDATES, len(allowed))
    top = np.argpartition(-mask, take - 1)[:take]
    return [int(i) for i in top[np.argsort(-mask[top])] if np.isfinite(mask[i])]


def _rrf(rankings: list[tuple[list[int], float]]) -> list[tuple[int, float]]:
    """Weighted Reciprocal Rank Fusion.

    Combines ranks rather than scores, which sidesteps the fact that a cosine
    similarity and a BM25 score are not comparable quantities and cannot be
    meaningfully normalised onto a shared scale.
    """
    scores: dict[int, float] = {}
    for ranking, weight in rankings:
        for rank, row in enumerate(ranking):
            scores[row] = scores.get(row, 0.0) + weight / (RRF_K + rank + 1)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


def for_product(query: str, entity_id: str, top_k: int = 6,
                doc_types: list[str] | None = None,
                related: list[str] | None = None) -> list[RetrievedChunk]:
    """Search, narrowed to one product.

    A readiness check that retrieved another product's regulation would report
    a finding against the wrong product, which is worse than reporting none. So
    the entity filter is not advisory here - it is the point.

    Passages about *no* entity in particular are kept. A regulation covering a
    whole category names the category and not the product, and dropping it
    because it fails to mention PRD-01 would remove the only thing that could
    have blocked PRD-01.

    ``related`` carries the entity's family - its variants, its product, its
    supplier - because a correction about a variant is answered by a passage
    about its product at least as often as by one about itself.
    """
    scope = [entity_id, *(related or [])]
    return search(query, top_k=top_k, doc_types=doc_types, entities=scope,
                  include_unscoped=True)


def _filter(index, doc_types, entities, tags, exclude_docs,
            include_unscoped: bool = False) -> set[int]:
    """Metadata filtering as a set of allowed row indices.

    With a few hundred chunks this is a linear scan and costs nothing, which is
    why arbitrary predicates are easy here and awkward in a vector database.
    """
    wanted_types = {t.upper() for t in doc_types} if doc_types else None
    wanted_entities = {e.upper() for e in entities} if entities else None
    wanted_tags = {t.lower() for t in tags} if tags else None
    excluded = set(exclude_docs or [])

    allowed: set[int] = set()
    for i, c in enumerate(index.chunks):
        if wanted_types and c.doc_type not in wanted_types:
            continue
        if c.doc_id in excluded:
            continue
        if wanted_entities:
            listed = {str(e).upper() for e in c.metadata.get("entities", [])}
            # An entity mentioned in the body counts as well as one declared in
            # the header - the header lists the document's subject, not every
            # identifier it happens to discuss.
            named = bool(listed & wanted_entities) or any(
                e in c.text.upper() for e in wanted_entities)
            # A passage about nothing in particular is category-level guidance:
            # a regulation covering purifiers names the category, not PRD-01.
            # Dropping it for failing to mention PRD-01 would remove the only
            # thing that could have blocked PRD-01. Opt-in, because the callers
            # that filter to an entity to *narrow* a result set do not want the
            # unscoped half back.
            general = include_unscoped and not listed
            if not named and not general:
                continue
        if wanted_tags:
            listed = {str(t).lower() for t in c.metadata.get("tags", [])}
            if not (listed & wanted_tags):
                continue
        allowed.add(i)
    return allowed


def get_document(doc_id: str) -> list[DocChunk]:
    index = index_mod.load()
    return sorted((c for c in index.chunks if c.doc_id == doc_id),
                  key=lambda c: c.ordinal)


def cite(results: list[RetrievedChunk]) -> list[dict]:
    """Compact citation records for a recommendation.

    A citation must be followable. Each carries the chunk id, the document, the
    heading and the source path, so a reviewer can open the exact section rather
    than the document and hunt.
    """
    return [
        {
            "chunk_id": r.chunk.id,
            "doc_id": r.chunk.doc_id,
            "doc_type": r.chunk.doc_type,
            "title": r.chunk.title,
            "heading": r.chunk.metadata.get("heading", ""),
            "source": r.chunk.metadata.get("source", ""),
            "score": r.score,
            "excerpt": _excerpt(r.chunk.text),
        }
        for r in results
    ]


def _excerpt(text: str, words: int = 45) -> str:
    # Skip the title/heading prefix added at chunk time - it is already shown
    # as its own field and repeating it wastes the excerpt.
    body = text.split("\n\n", 1)[-1]
    parts = body.split()
    return " ".join(parts[:words]) + ("..." if len(parts) > words else "")
