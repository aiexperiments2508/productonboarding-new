"""The reranker: what it may reorder, and what it may never do.

Every test here drives a stubbed gateway. That is deliberate rather than
convenient - what needs asserting is not whether a model ranks well, which
changes with the model, but that a *badly behaved* one cannot damage the result
set. A reranker is allowed to be wrong about the order. It is not allowed to
invent a passage, drop one, or fail quietly.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_rerank.db")

from sc import db  # noqa: E402
from sc.llm import gateway  # noqa: E402
from sc.rag import index as index_mod  # noqa: E402
from sc.rag import rerank, retrieve  # noqa: E402

QUERY = "what has to appear on a food label"


@pytest.fixture(autouse=True)
def built_index():
    db.init_db(drop=True)
    index_mod.load.cache_clear()
    index_mod.build(include_comms=False, embed=False)
    yield
    index_mod.load.cache_clear()


@pytest.fixture
def candidates():
    found = retrieve.search(QUERY, top_k=10, semantic=False, rerank=False)
    assert len(found) >= 6, "the corpus should answer this well enough to rank"
    return found


def stub(monkeypatch, reply):
    """Answer every rerank call with one canned reply."""
    def complete_json(messages, model=None, agent=None, run_id=None, **kwargs):
        if callable(reply):
            return reply(messages), None
        return reply, None
    monkeypatch.setattr(gateway, "complete_json", complete_json)


def ranking(pairs):
    return {"ranking": [{"id": i, "score": s} for i, s in pairs]}


# ---------------------------------------------------------------------------
# It is off until somebody turns it on
# ---------------------------------------------------------------------------


def test_reranking_is_off_until_configured():
    """A model call on a path that used to have none is a trade, not a win."""
    assert rerank.enabled() is False

    db.set_config(rerank.ENABLED_KEY, "true")
    assert rerank.enabled() is True
    db.set_config(rerank.ENABLED_KEY, "false")
    assert rerank.enabled() is False


def test_search_does_not_call_the_gateway_when_it_is_off(monkeypatch, candidates):
    def explode(*args, **kwargs):
        raise AssertionError("the reranker ran while disabled")

    monkeypatch.setattr(gateway, "complete_json", explode)
    assert retrieve.search(QUERY, top_k=4, semantic=False)


# ---------------------------------------------------------------------------
# What it may do
# ---------------------------------------------------------------------------


def test_it_reorders_by_score(monkeypatch, candidates):
    ids = [r.chunk.id for r in candidates]
    stub(monkeypatch, ranking([(i, float(n)) for n, i in enumerate(ids[:6])]))

    out, note = rerank.rerank(QUERY, candidates, top_k=6)
    assert [r.chunk.id for r in out] == list(reversed(ids[:6]))
    assert "reranked 6" in note


def test_the_score_it_gave_travels_with_the_passage(monkeypatch, candidates):
    """Kept beside the fused score, not on top of it.

    They answer different questions, and overwriting one with the other hides
    which of them put a passage where it is.
    """
    ids = [r.chunk.id for r in candidates]
    stub(monkeypatch, ranking([(ids[2], 9.5)]))

    out, _ = rerank.rerank(QUERY, candidates, top_k=4)
    assert out[0].chunk.id == ids[2]
    assert out[0].rerank_score == 9.5
    assert out[0].score != 9.5, "the fused score was overwritten"
    assert out[1].rerank_score is None


def test_search_applies_it_when_the_switch_is_on(monkeypatch, candidates):
    ids = [r.chunk.id for r in candidates]
    db.set_config(rerank.ENABLED_KEY, "true")
    stub(monkeypatch, ranking([(ids[5], 10)]))

    out = retrieve.search(QUERY, top_k=3, semantic=False)
    assert out[0].chunk.id == ids[5]
    assert len(out) == 3


def test_it_reads_deeper_than_the_caller_asked_for(monkeypatch, candidates):
    """The passage worth promoting is usually not already in the top three.

    Truncating to `top_k` before reranking would throw it away before anything
    looked at it, which would leave the reranker able only to shuffle what
    fusion had already chosen.
    """
    db.set_config(rerank.ENABLED_KEY, "true")
    seen: list[int] = []

    def count(messages):
        seen.append(messages[1]["content"].count("\n["))
        return {"ranking": []}

    stub(monkeypatch, count)
    retrieve.search(QUERY, top_k=2, semantic=False)
    assert seen and seen[0] > 2, f"only {seen} passages were offered to rank"


# ---------------------------------------------------------------------------
# What it may never do
# ---------------------------------------------------------------------------


def test_an_invented_id_is_dropped_and_counted(monkeypatch, candidates):
    """The one thing retrieval must never do is add to the evidence.

    A reranker that returns an id it was not given is not reordering passages,
    it is producing one - and downstream every citation gate in this system
    trusts that a retrieved id was retrieved.
    """
    ids = [r.chunk.id for r in candidates]
    stub(monkeypatch, ranking([("POL-999#42", 10.0), (ids[0], 5.0)]))

    out, note = rerank.rerank(QUERY, candidates, top_k=6)
    returned = {r.chunk.id for r in out}
    assert "POL-999#42" not in returned
    assert returned <= set(ids)
    assert "dropped 1 invented" in note


def test_passages_it_ignores_keep_their_fused_place(monkeypatch, candidates):
    """A reply about three of twelve must not shorten the result set."""
    ids = [r.chunk.id for r in candidates]
    stub(monkeypatch, ranking([(ids[4], 8.0)]))

    out, _ = rerank.rerank(QUERY, candidates, top_k=6)
    assert len(out) == 6
    assert out[0].chunk.id == ids[4]
    assert [r.chunk.id for r in out[1:]] == [i for i in ids[:6] if i != ids[4]][:5]


def test_a_duplicated_id_is_scored_once(monkeypatch, candidates):
    ids = [r.chunk.id for r in candidates]
    stub(monkeypatch, ranking([(ids[1], 9.0), (ids[1], 1.0), (ids[0], 5.0)]))

    out, _ = rerank.rerank(QUERY, candidates, top_k=6)
    assert [r.chunk.id for r in out].count(ids[1]) == 1
    assert out[0].chunk.id == ids[1]


@pytest.mark.parametrize("reply", [
    {"nonsense": True},
    {"ranking": "not a list"},
    {"ranking": [{"id": None, "score": 1}]},
    {"ranking": [{"no_id": "x"}]},
    {},
])
def test_an_unusable_reply_leaves_the_fused_order_alone(monkeypatch, candidates,
                                                        reply):
    ids = [r.chunk.id for r in candidates]
    stub(monkeypatch, reply)

    out, note = rerank.rerank(QUERY, candidates, top_k=6)
    assert [r.chunk.id for r in out] == ids[:6]
    assert note.startswith("not reranked")


def test_a_non_numeric_score_is_dropped_not_guessed(monkeypatch, candidates):
    ids = [r.chunk.id for r in candidates]
    stub(monkeypatch, ranking([(ids[3], "very relevant"), (ids[1], 7.0)]))

    out, _ = rerank.rerank(QUERY, candidates, top_k=6)
    assert out[0].chunk.id == ids[1]


def test_a_dead_gateway_leaves_the_fused_order_alone(monkeypatch, candidates):
    """The same posture `_semantic` already takes when embeddings are gone."""
    def boom(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(gateway, "complete_json", boom)
    ids = [r.chunk.id for r in candidates]

    out, note = rerank.rerank(QUERY, candidates, top_k=6)
    assert [r.chunk.id for r in out] == ids[:6]
    assert "connection refused" in note


def test_search_survives_a_dead_gateway_with_reranking_on(monkeypatch,
                                                          candidates):
    def boom(*args, **kwargs):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(gateway, "complete_json", boom)
    db.set_config(rerank.ENABLED_KEY, "true")

    notes: list[str] = []
    out = retrieve.search(QUERY, top_k=4, semantic=False, notes=notes)
    assert len(out) == 4
    assert notes and notes[0].startswith("not reranked")


def test_one_candidate_is_not_worth_a_model_call(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("the gateway was called to rank one passage")

    monkeypatch.setattr(gateway, "complete_json", explode)
    single = retrieve.search(QUERY, top_k=1, semantic=False, rerank=False)
    out, note = rerank.rerank(QUERY, single, top_k=1)
    assert len(out) == 1
    assert note == ""


def test_the_prompt_carries_the_ids_it_expects_back(monkeypatch, candidates):
    """The model can only return ids it was given, so it has to be given them."""
    captured: list[str] = []

    def capture(messages):
        captured.append(messages[1]["content"])
        return {"ranking": []}

    stub(monkeypatch, capture)
    rerank.rerank(QUERY, candidates, top_k=6)

    assert captured
    for result in candidates[:rerank.CANDIDATES]:
        assert f"[{result.chunk.id}]" in captured[0]
    assert QUERY in captured[0]
