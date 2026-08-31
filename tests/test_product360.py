"""Finding a product, and what the estate has said about it.

Two things are under test. The first is search, which is small and exact and
deliberately not the retrieval index - fusing BM25 with embeddings to answer
"which variant is AER-300-MAX" would be a slower way to get a worse answer.

The second is the record, and specifically the half that would be easy to leave
out: the values that *lost*. A disagreement precedence settled is settled, not
absent, and dropping the loser would make the record look like everybody agreed.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_product360.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db  # noqa: E402
from sc.contracts import MediaRole  # noqa: E402
from sc.readiness import record as record_mod  # noqa: E402
from sc.readiness import search as search_mod  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

PURIFIER_MAX = "VAR-01B"


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    baseline_mod.get.cache_clear()
    tape.load_tape(reset=True)
    ingest.ingest(tape.jump_to(tape.inject_seq()))
    yield
    db.close()


def _sku(entity_id: str) -> str:
    return baseline_mod.get().variants[entity_id].sku


# ---------------------------------------------------------------------------
# Finding it
# ---------------------------------------------------------------------------


def test_every_variant_has_a_distinct_sku():
    variants = baseline_mod.get().variants
    skus = [v.sku for v in variants.values()]

    assert all(skus), "a variant with no SKU cannot be found by anybody outside"
    assert len(set(skus)) == len(skus), "two variants share a SKU"


def test_a_sku_finds_exactly_one_product():
    results = search_mod.find(_sku(PURIFIER_MAX))

    assert results, "a SKU found nothing"
    assert results[0]["entity_id"] == PURIFIER_MAX
    assert results[0]["sku"] == _sku(PURIFIER_MAX)


def test_the_internal_identifier_still_finds_it():
    """The internal key stays a key. Renaming it to look friendlier would make
    the audit trail harder to read for a cosmetic gain."""
    results = search_mod.find(PURIFIER_MAX)
    assert results[0]["entity_id"] == PURIFIER_MAX


def test_a_name_finds_a_product():
    results = search_mod.find("purifier")
    assert results, "a name found nothing"
    assert all("air-treatment" in r["category"] for r in results)


def test_an_exact_identifier_outranks_a_name_match():
    """Somebody typing a SKU knows exactly what they want. Ranking a browse
    above a precise query makes the precise one the unreliable one."""
    results = search_mod.find(_sku(PURIFIER_MAX))
    assert results[0]["entity_id"] == PURIFIER_MAX

    # And a prefix of that SKU still puts its owner first, ahead of anything
    # matched only on words.
    prefix = _sku(PURIFIER_MAX)[:7]
    ranked = search_mod.find(prefix)
    assert ranked and ranked[0]["sku"].startswith(prefix)


def test_a_search_with_no_match_is_empty_not_an_error():
    """A typo is a normal thing for a person to do, and a 500 is a rude way to
    say so."""
    assert search_mod.find("nothing-matches-this") == []


def test_an_empty_query_lists_everything():
    """The product view opens on this. A page that stays empty until somebody
    types looks broken rather than ready.

    "Everything" is bounded by the limit, and asserting that is the point: a
    catalog of a few hundred variants must come back paged rather than whole,
    and the count of what matched has to travel with the page or the caller
    cannot tell a short list from a truncated one.
    """
    total_variants = len(baseline_mod.get().variants)

    page, matched = search_mod.find("", limit=25, count=True)
    assert len(page) == min(25, total_variants)
    assert matched == total_variants, "the count is of matches, not of the page"

    everything = search_mod.find("", limit=10_000)
    assert len(everything) == total_variants


def test_paging_walks_the_whole_list_without_repeating_itself():
    """A second page is the next products, not the same ones again."""
    first = search_mod.find("", limit=10)
    second = search_mod.find("", limit=10, offset=10)

    assert len(first) == len(second) == 10
    assert not ({r["entity_id"] for r in first}
                & {r["entity_id"] for r in second})


def test_filters_narrow_without_reordering():
    """A facet filter removes rows; it does not rerank the ones it keeps."""
    base = baseline_mod.get()
    supplier = base.products[next(iter(sorted(base.products)))].supplier

    unfiltered = [r["entity_id"] for r in search_mod.find("", limit=10_000)]
    filtered = search_mod.find("", limit=10_000, suppliers=[supplier])

    assert filtered, "a supplier in the catalog matched nothing"
    assert all(r["supplier"] == supplier for r in filtered)
    kept = [r["entity_id"] for r in filtered]
    assert kept == [e for e in unfiltered if e in set(kept)]


def test_search_is_ordered_so_two_queries_agree():
    assert search_mod.find("purifier") == search_mod.find("purifier")


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def test_every_value_names_its_document_and_carrier():
    base = baseline_mod.get()
    record = record_mod.build(PURIFIER_MAX)
    rendered = record_mod.as_dict(record, base)

    assert rendered["attributes"], "the record holds nothing"
    for row in rendered["attributes"]:
        assert row["path"] and row["label"]
        # "We do not know which system sent this" is an answer; a missing key
        # reads as an oversight.
        assert "system" in row
        assert "defects" in row


def test_a_settled_disagreement_is_still_visible():
    """A reviewer asking "did anything else say otherwise" is asking the
    question an estate of ten systems exists to answer."""
    from sc.contracts import Provenance, ProvenanceKind
    from sc.state import store

    now = tape.state().sim_clock
    first = store.record("variant", PURIFIER_MAX, "specs.noise_db", 41,
                         valid_from=now, recorded_at=now,
                         provenance=Provenance(kind=ProvenanceKind.RECORDED,
                                               system="gdsn-pool"))
    store.correct(first, 38, valid_from=now, recorded_at=now,
                  provenance=Provenance(kind=ProvenanceKind.RECORDED,
                                        system="label-artwork"))

    record = record_mod.build(PURIFIER_MAX)
    losers = record.superseded.get("specs.noise_db") or []

    assert losers, "the value that lost was dropped from the record"
    assert any(entry.get("system") for entry in losers), \
        "a superseded value that names no system cannot be argued with"


def test_media_carries_a_declared_role():
    """Free text would make a missing hero shot indistinguishable from one filed
    under a name nobody checked."""
    base = baseline_mod.get()
    roles = {str(r) for r in MediaRole}

    held = [a for assets in base.media_by_entity.values() for a in assets]
    assert held, "the catalog holds no media at all"
    for asset in held:
        assert str(asset.role) in roles
        assert asset.entity_id in base.variants
        assert asset.uri


def test_a_product_with_no_media_still_has_a_record():
    base = baseline_mod.get()
    record = record_mod.build(PURIFIER_MAX)
    record.media = []

    rendered = record_mod.as_dict(record, base)
    assert rendered["media"] == []
    assert rendered["attributes"], "losing media must not lose the record"


# ---------------------------------------------------------------------------
# The API is the same reads
# ---------------------------------------------------------------------------


def test_the_api_product_reads_are_the_pipelines_own():
    """Two implementations of one read become two accounts of the same product
    the first time either is edited."""
    import inspect

    from sc import main

    for route in ("product_search", "product_record", "product_readiness",
                  "product_preview"):
        body = inspect.getsource(getattr(main, route))
        assert ("search_mod" in body or "record_mod" in body
                or "readiness." in body or "preview_mod" in body), \
            f"{route} does not delegate"
        # Nothing in a route re-derives a verdict for itself.
        assert "RETURN_TO_SOURCE" not in body and "READY_TO_LAUNCH" not in body
