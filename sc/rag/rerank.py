"""Reordering fused candidates by reading them.

Fusion decides what is *plausible*; this decides what is *relevant*. They are
different questions and the second one is the one a reviewer asked.

RRF has no idea what the query means. It knows that BM25 put a passage third
and the embedding put it seventh, and it has no way to notice that the passage
happens to be about a different product, or answers the opposite of what was
asked, or is the "Related documents" section of the right document rather than
the rule itself. A model reading the query beside the passage notices all
three, and that is the entire value here - a cross-encoder does the same job
without a gateway, but it arrives as ``sentence-transformers`` and a compiled
extension, which is the dependency line this application has held everywhere
else.

**This never invents and never removes.** The model is given ids and may only
return ids it was given; anything else is dropped. Candidates it fails to
mention are appended in fused order rather than discarded, so the worst a
confused reranker can do is leave the fused ordering roughly alone. If the
gateway is unreachable, the call is refused or the reply will not parse, the
fused order stands untouched and the caller is told why - the same posture
``retrieve._semantic`` already takes when embeddings are unavailable.

Off by default. It costs a model call on the path that used to cost none, and
identifier queries - which are most of them - were already answered correctly
by BM25. It earns its place on paraphrase, which is where the fused ordering is
weakest and where somebody is reading the answer rather than following a link.
"""

from __future__ import annotations

import logging

from sc import db
from sc.contracts import RetrievedChunk
from sc.llm import gateway

log = logging.getLogger(__name__)

#: How many fused candidates are read. Bounded rather than generous: the fused
#: top of a few hundred chunks is where the right answer lives, and every extra
#: passage is prompt tokens spent to reorder something that was not going to be
#: returned anyway.
CANDIDATES = 12

#: Words of each passage shown. A chunk is up to 500 and its first line already
#: carries the document title and heading path, so this is the rule plus its
#: opening rather than an arbitrary slice.
EXCERPT_WORDS = 150

ENABLED_KEY = "rerank_enabled"
MODEL_KEY = "rerank_model"

SYSTEM = """You rank retrieved passages by how well each one answers a question.

Score every passage you are given from 0 to 10:
  10  directly answers the question
   7  about the right subject and materially useful
   4  related but does not answer what was asked
   0  wrong subject, or the passage is only a list of cross-references

Rules:
- Only use passage ids exactly as given. Never invent an id.
- Score every passage you were given, once each.
- Judge the passage in front of you. Do not reward a passage for being from an
  important-sounding document if it does not answer the question.

Reply with JSON only:
{"ranking": [{"id": "<passage id>", "score": <number>}]}"""


def enabled() -> bool:
    """Whether reranking is on. Configured, not compiled in."""
    return str(db.get_config(ENABLED_KEY) or "").strip().lower() in {
        "1", "true", "yes", "on"}


def model() -> str | None:
    return (db.get_config(MODEL_KEY) or "").strip() or None


def _passage(result: RetrievedChunk) -> str:
    text = result.chunk.text
    heading = str(result.chunk.metadata.get("heading", "")).strip()
    words = text.split()
    body = " ".join(words[:EXCERPT_WORDS])
    if len(words) > EXCERPT_WORDS:
        body += "..."
    label = f"[{result.chunk.id}]"
    if heading:
        label += f" {heading}"
    return f"{label}\n{body}"


def rerank(query: str, results: list[RetrievedChunk], top_k: int,
           run_id: str = "") -> tuple[list[RetrievedChunk], str]:
    """Reorder fused candidates by relevance. Returns the list and a note.

    The note is not decoration. Reranking silently not happening - because the
    gateway is down, or the reply did not parse - looks exactly like reranking
    happening and agreeing with the fused order, and those are very different
    facts about an answer somebody is about to act on.
    """
    candidates = results[:CANDIDATES]
    if len(candidates) < 2:
        return results[:top_k], ""

    by_id = {r.chunk.id: r for r in candidates}
    prompt = ("Question: " + query.strip() + "\n\nPassages:\n\n"
              + "\n\n".join(_passage(r) for r in candidates))

    try:
        reply, _ = gateway.complete_json(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": prompt}],
            model=model(), agent="retrieval.rerank", run_id=run_id)
    except Exception as exc:  # noqa: BLE001 - a reranker is never load bearing
        log.debug("rerank unavailable", exc_info=True)
        return results[:top_k], f"not reranked: {str(exc)[:120]}"

    scored, unknown = _read(reply, by_id)
    if not scored:
        return results[:top_k], "not reranked: the reply named no known passage"

    # Anything the model did not mention keeps its fused position, behind
    # everything it did. Dropping them would let a model that answered about
    # three of twelve passages silently shorten the result set.
    ranked = [by_id[chunk_id] for chunk_id, _ in scored]
    seen = {chunk_id for chunk_id, _ in scored}
    ranked.extend(r for r in results if r.chunk.id not in seen)

    out = [
        r.model_copy(update={"rerank_score": dict(scored).get(r.chunk.id)})
        for r in ranked[:top_k]
    ]
    note = f"reranked {len(scored)} of {len(candidates)} candidates"
    if unknown:
        note += f"; dropped {unknown} invented id(s)"
    return out, note


def _read(reply: dict, by_id: dict) -> tuple[list[tuple[str, float]], int]:
    """Validated (id, score) pairs, highest first, and how many were invented.

    A reranker that hallucinates an id is not reordering the evidence, it is
    adding to it - which is the one thing retrieval must never do. So an id
    that was not in the prompt is dropped and counted rather than trusted.
    """
    rows = reply.get("ranking") if isinstance(reply, dict) else None
    if not isinstance(rows, list):
        return [], 0

    scored: dict[str, float] = {}
    unknown = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        chunk_id = str(row.get("id") or "").strip()
        if chunk_id not in by_id:
            unknown += 1
            continue
        if chunk_id in scored:  # first mention wins
            continue
        try:
            scored[chunk_id] = float(row.get("score"))
        except (TypeError, ValueError):
            continue

    ordered = sorted(scored.items(), key=lambda pair: -pair[1])
    return ordered, unknown
