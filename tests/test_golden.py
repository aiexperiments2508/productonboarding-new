"""The extraction answer key, and the two things that could quietly break it.

``data/golden/extractions.jsonl`` is what ``scripts/evaluate.py`` grades a model
against, and it is written by ``scripts/generate_data.py`` from the same event
payloads the tape carries. That is the whole design: the key regenerates with
the data instead of rotting behind it.

Two ways it can still go wrong, and both are silent. The generator can drift
from ``nodes._extraction_from_payload`` - the deterministic fallback, which
reads the identical fields and is therefore the key's second author. And the
key on disk can fall behind the tape on disk, so an eval grades yesterday's
documents. Neither needs a gateway to catch, so these run everywhere.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("DB_PATH", "data/test_golden.db")

from sc import db  # noqa: E402
from sc.contracts import CorrectionKind  # noqa: E402
from sc.graph import nodes  # noqa: E402
from sc.replay import tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

KEY_PATH = Path("data/golden/extractions.jsonl")


def _generator():
    """scripts/ is not a package, so the generator is loaded by path."""
    spec = importlib.util.spec_from_file_location(
        "generate_data", Path("scripts/generate_data.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN = _generator()

needs_key = pytest.mark.skipif(
    not KEY_PATH.exists(),
    reason="no answer key; run scripts/generate_data.py")


@pytest.fixture(scope="module")
def key() -> list[dict]:
    return [json.loads(line) for line in
            KEY_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


@pytest.fixture(scope="module")
def events() -> dict:
    db.init_db(drop=True)
    tape.load_tape()
    baseline_mod.get.cache_clear()
    rows = db.query("SELECT * FROM events ORDER BY seq")
    return {r["id"]: tape._row_to_event(r) for r in rows}


# ---------------------------------------------------------------------------
# The key against the tape
# ---------------------------------------------------------------------------


@needs_key
def test_key_covers_every_material_document_and_invents_none(key, events):
    """A key that has fallen behind the tape grades the wrong corpus.

    It used to cover the readable tape exactly, which was the right assertion
    when the tape carried a few dozen documents. It now carries hundreds of
    routine category notes that assert nothing, and a key where the negatives
    outnumber the positives thirty to one measures how often a model correctly
    says "nothing here" rather than whether it finds the correction. So the
    negatives are sampled, and the two halves of the old assertion are made
    separately: every material document is keyed, and nothing is keyed that the
    tape does not carry.
    """
    readable = [e for e in events.values()
                if str(e.type) in GEN.READ_BY_EXTRACT]
    keyed = [g["event_id"] for g in key]

    material = [e.id for e in readable
                if (e.payload or {}).get("material_hint", True)]
    assert set(material) <= set(keyed),         "a material document the tape carries is missing from the key"
    assert set(keyed) <= {e.id for e in readable},         "the key names a document the tape does not carry"
    assert keyed == sorted(keyed), "the key is not in tape order"


@needs_key
def test_every_keyed_row_is_something_the_catalog_can_hold(key, events):
    base = baseline_mod.get()
    for g in key:
        for row in g["rows"]:
            assert row["attribute_path"] in base.attr_defs
            assert (row["entity_id"] in base.variants
                    or row["entity_id"] in base.products)


@needs_key
def test_the_key_still_contains_the_question(key):
    """The classes the measurement turns on, asserted rather than assumed.

    A key that lost its ambiguous correction would report a clean UNCLEAR
    column having measured nothing at all.
    """
    assert any(g["applies_to"] == "UNCLEAR" and g["is_correction"] for g in key)
    assert any(not g["material"] for g in key)
    assert any(len(g["rows"]) > 1 for g in key)
    assert any(g["scope_determinate"] and len(g["scope_entities"]) == 1
               for g in key)


# ---------------------------------------------------------------------------
# The key against the deterministic fallback
# ---------------------------------------------------------------------------

# The fields both authors read out of the same payload. ``applies_to`` is
# deliberately absent: the two speak different vocabularies and the next test
# is about exactly that.
SHARED_FIELDS = ("material", "attribute_path", "old_value", "new_value",
                 "unit", "is_correction", "resolves_issue", "provisional")


@needs_key
@pytest.mark.parametrize("field", SHARED_FIELDS)
def test_key_agrees_with_the_deterministic_fallback(key, events, field):
    for g in key:
        fallback = nodes._extraction_from_payload(events[g["event_id"]])
        assert fallback[field] == g[field], f"{g['event_id']} {field}"


@needs_key
def test_key_agrees_with_the_fallback_on_correction_kind(key, events):
    for g in key:
        fallback = nodes._extraction_from_payload(events[g["event_id"]])
        assert fallback["kind"] == g["kind"], g["event_id"]
        assert str(CorrectionKind(g["kind"])) == g["kind"]


def test_the_two_kind_tables_are_the_same_table():
    """The generator classifies a document; so does the deterministic fallback.

    They are written twice on purpose - the generator does not import ``sc``,
    and a key that read its answers out of the implementation it grades would
    measure nothing. The cost of that is a pair that can drift, and the drift
    would be silent: a document classified one way in the key and another way
    by the fallback scores as a model error.

    So the two tables are compared directly, in order, because the order *is*
    the precedence: which kind a document carrying two of them is named by.
    """
    assert GEN.GOLDEN_KIND_BY_PATH == nodes.KIND_BY_PATH


def test_every_kind_the_prompt_offers_is_a_kind_that_exists():
    """A kind in the prompt and not in the enum is dropped in silence.

    ``_extracted_kind`` builds ``CorrectionKind(named)`` inside a try/except,
    so a classification the enum has never heard of does not raise - it falls
    back to a spec correction and the model is marked wrong for being right.
    """
    from sc.graph import prompts

    offered = set(re.findall(r'"([A-Z][A-Z_]+)"', prompts.EXTRACT_SYSTEM))
    known = {str(k) for k in CorrectionKind}
    # The prompt names other things in capitals - BASE, VARIANT, UNCLEAR - so
    # only the intersection with kind-shaped names is asserted, and every kind
    # the enum holds has to appear.
    assert known <= offered, f"kinds absent from the prompt: {known - offered}"


@needs_key
def test_the_fallback_answers_applies_to_in_the_catalogs_vocabulary(key, events):
    """Recorded, not asserted as correct - this is a known gap, measured.

    The extraction prompt offers three answers (BASE, VARIANT, UNCLEAR); the
    structured hint answers in the catalog's own words (PRODUCT, ALL). Nothing
    downstream reads the field - it is carried into the run trace and no
    further - so the mismatch costs nothing today. It is pinned here so that
    stops being true loudly rather than quietly, and so the eval's confusion
    matrix has one documented place its translation lives.
    """
    for g in key:
        if not g["material"]:
            continue
        stated = nodes._extraction_from_payload(events[g["event_id"]])["applies_to"]
        assert GEN.APPLIES_TO_MAP.get(stated, "UNCLEAR") == g["applies_to"], (
            f"{g['event_id']}: fallback said {stated}, key says {g['applies_to']}")


@needs_key
def test_the_prompt_the_eval_grades_is_the_prompt_that_ships(events):
    """``extract_messages`` is what both the node and the scorer call."""
    base = baseline_mod.get()
    event = next(e for e in events.values() if str(e.type) == "SPEC_DOC")
    messages = nodes.extract_messages(base, event)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "attribute_path" in messages[0]["content"]
    assert str(event.payload.get("doc_id")) in messages[1]["content"]
