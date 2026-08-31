"""Where a product has got to.

The board is a join, not a new source of truth. Every lane is derived from
state that already exists - the verdict a check reached, the status a listing
is in, what has been committed, what is being held back downstream - and the
tests here are mostly about that: that nothing is stored, that the derivation
uses the same numbers every other surface uses, and that the one lane the
demonstration turns on fills when it should and empties when it should.

The lane that matters is LATE_CHANGE. It means something wrong is in front of a
shopper right now, and a board that filed such a product under "on sale" would
be hiding the only row anybody needs to look at.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_lifecycle.db")

from sc import db  # noqa: E402
from sc.estate import intake  # noqa: E402
from sc.lifecycle import board, drafts, stages, timeline  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.readiness.verdict import BLOCKED, READY, RETURN  # noqa: E402

VARIANT = "VAR-05A"
PRODUCT = "PRD-05"
SUPPLIER = "SUP-02"
SAFETY = "food.allergens.may_contain"


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    # Accepted lines are written beside the seed pack, and a test that wrote
    # into the real one would leave a product behind for every other module in
    # the run. The pack is copied by reference: DATA_DIR still points at the
    # generated files, and only the extension is redirected.
    from sc.state import baseline as baseline_mod

    monkeypatch.setattr(baseline_mod, "EXTENSION",
                        str(tmp_path / "catalog.live.json"), raising=False)
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    baseline_mod.get.cache_clear()
    ingest.ingest(tape.jump_to(tape.inject_seq() + 12))
    yield
    baseline_mod.get.cache_clear()
    db.close()


def _lane_of(product_id: str, built=None) -> str:
    built = built or board.build(limit=400)
    for lane in built["lanes"]:
        if any(p["product_id"] == product_id for p in lane["products"]):
            return lane["stage"]
    return ""


def _submit():
    return intake.submit_specification_change(
        supplier=SUPPLIER, system_id="supplier-portal", entity_id=VARIANT,
        attribute_path=SAFETY, new_value=["milk", "peanuts"],
        note="Peanut handling introduced on the packing line.")


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def test_a_late_change_outranks_being_on_sale():
    """A product that is live *and* carrying a correction is not simply live.
    The whole point of the lane is that something wrong is in front of a
    shopper, and filing it under "on sale" would bury the one row that matters.
    """
    assert stages.stage_of(verdict=READY, listings={"LIVE": 4},
                           dispatched=True, corrected=True,
                           redacted=False) == stages.LATE_CHANGE


def test_a_redaction_alone_puts_a_product_in_the_late_lane():
    """Something being held back downstream is itself the finding, whether or
    not a signal is still in force."""
    assert stages.stage_of(verdict=READY, listings={"LIVE": 2},
                           dispatched=True, corrected=False,
                           redacted=True) == stages.LATE_CHANGE


def test_being_sent_back_outranks_being_on_sale():
    """A product that is both is one whose finding somebody has to act on."""
    assert stages.stage_of(verdict=RETURN, listings={"LIVE": 3},
                           dispatched=True, corrected=False,
                           redacted=False) == stages.WITH_SUPPLIER
    assert stages.stage_of(verdict=BLOCKED, listings={"LIVE": 3},
                           dispatched=False, corrected=False,
                           redacted=False) == stages.WITH_SUPPLIER


def test_every_lane_the_rule_can_return_is_a_lane_the_board_renders():
    """A stage nothing renders is a product that vanishes off the board."""
    built = board.build(limit=20)
    rendered = {lane["stage"] for lane in built["lanes"]}
    assert rendered == set(stages.STAGES)
    for stage in stages.STAGES:
        assert stages.DESCRIPTIONS[stage]


# ---------------------------------------------------------------------------
# The board
# ---------------------------------------------------------------------------


def test_every_product_lands_in_exactly_one_lane():
    built = board.build(limit=400)
    seen: list[str] = []
    for lane in built["lanes"]:
        seen += [p["product_id"] for p in lane["products"]]
    assert len(seen) == len(set(seen))
    assert len(seen) == built["products"]


def test_the_board_agrees_with_the_product_list_about_verdicts():
    """A board and a list of the same population that disagreed about whether a
    product is fit to launch would be two populations."""
    import sc.readiness as readiness
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    built = board.build(limit=400)
    for lane in built["lanes"]:
        for product in lane["products"][:3]:
            for variant in product["variants"]:
                summary = readiness.assess(variant["entity_id"],
                                           use_model=False)
                assert summary["verdict"] == variant["verdict"]
            assert product["product_id"] in base.products


def test_a_product_is_as_blocked_as_its_worst_variant():
    """A multipack nobody can launch holds the line for the product."""
    built = board.build(limit=400)
    for lane in built["lanes"]:
        for product in lane["products"]:
            worst = max((v["verdict"] for v in product["variants"]),
                        key=lambda v: {READY: 0, RETURN: 1, BLOCKED: 2}[v])
            assert product["verdict"] == worst


def test_the_board_says_when_it_was_placed_without_a_model():
    """Six checks of nine have found fewer things. A cleared lane that did not
    say so would be laundering the difference."""
    built = board.build(limit=20)
    assert built["checks_complete"] is False
    assert "six checks rather than nine" in built["caveat"]


# ---------------------------------------------------------------------------
# The late lane, live
# ---------------------------------------------------------------------------


def test_a_supplier_submission_moves_a_product_into_the_late_lane():
    """Before any run has read it. Waiting for the graph would mean the board
    said "on sale, all well" for as long as it took somebody to notice - which
    is exactly the interval this lane exists to make visible."""
    assert _lane_of(PRODUCT) != stages.LATE_CHANGE
    _submit()
    assert _lane_of(PRODUCT) == stages.LATE_CHANGE


def test_the_late_lane_says_what_landed_and_that_it_has_not_been_read():
    _submit()
    built = board.build(limit=400)
    late = next(l for l in built["lanes"] if l["stage"] == stages.LATE_CHANGE)
    product = next(p for p in late["products"] if p["product_id"] == PRODUCT)

    assert product["correction"]["source"] == "submission"
    assert product["correction"]["awaiting_extraction"] is True
    assert product["correction"]["supplier"] == SUPPLIER
    assert product["correction"]["doc_ref"]


def test_a_submission_stops_counting_once_a_run_has_read_it():
    """After that the signal speaks for itself - and if there is no signal, the
    platform has read the document and found nothing to do, which is an answer
    rather than a silence."""
    from sc.tools import planning

    result = _submit()
    assert _lane_of(PRODUCT) == stages.LATE_CHANGE

    planning.audit("extract", "EXAMINE", "event", result["event_id"], {})
    assert _lane_of(PRODUCT) != stages.LATE_CHANGE


# ---------------------------------------------------------------------------
# The timeline
# ---------------------------------------------------------------------------


def test_a_timeline_shows_a_submission_beside_what_the_estate_delivered():
    _submit()
    story = timeline.build(PRODUCT)
    kinds = {event["kind"] for event in story["events"]}
    assert "submission" in kinds
    assert "arrival" in kinds


def test_a_timeline_runs_forwards():
    _submit()
    story = timeline.build(PRODUCT)
    stamps = [event["at"] for event in story["events"]]
    assert stamps == sorted(stamps)


def test_a_timeline_for_a_product_nobody_has_is_a_refusal_not_an_empty_page():
    assert timeline.build("PRD-NOPE")["error"]


def test_a_submission_names_the_system_that_carried_it():
    _submit()
    story = timeline.build(PRODUCT)
    entry = next(e for e in story["events"] if e["kind"] == "submission")
    assert entry["system"] == "supplier-portal"
    assert entry["doc_ref"]


# ---------------------------------------------------------------------------
# Proposed lines
# ---------------------------------------------------------------------------


def _propose(name: str = "Harrowfield Oat Bites",
             category: str = "food.snacks.bars") -> dict:
    return intake.create_product_draft(
        supplier=SUPPLIER, system_id="supplier-portal", name=name,
        category=category, note="New line for spring.")


def test_a_proposed_line_is_on_the_board_before_anybody_has_decided():
    """Otherwise it sits in a mailbox for a fortnight. The catalog has never
    heard of it, which is exactly why it needs somewhere to be seen."""
    _propose()
    built = board.build(limit=400)
    lane = next(l for l in built["lanes"] if l["stage"] == stages.DRAFT)
    assert lane["count"] == 1
    assert lane["products"][0]["name"] == "Harrowfield Oat Bites"
    assert lane["products"][0]["supplier"] == SUPPLIER


def test_a_proposed_line_is_not_in_the_catalog_until_it_is_accepted():
    from sc.state import baseline as baseline_mod

    before = len(baseline_mod.get().products)
    result = _propose()
    assert result["in_catalog"] is False
    assert len(baseline_mod.get().products) == before


def test_accepting_a_line_puts_it_in_the_catalog():
    from sc.state import baseline as baseline_mod

    before = len(baseline_mod.get().products)
    proposal = _propose()

    accepted = drafts.accept(proposal["submission_id"], actor="k.mensah")
    assert accepted["accepted"] is True

    base = baseline_mod.get()
    assert len(base.products) == before + 1
    product = base.products[accepted["product_id"]]
    assert product.name == "Harrowfield Oat Bites"
    assert product.supplier == SUPPLIER
    assert product.regulated is True, "a food line is regulated"


def test_an_accepted_line_is_assessed_like_any_other_and_is_not_ready():
    """It is not ready because somebody accepted it. It has no specification
    and no imagery, and the checks say so."""
    import sc.readiness as readiness

    proposal = _propose()
    accepted = drafts.accept(proposal["submission_id"], actor="k.mensah")

    summary = readiness.assess(accepted["variant_id"], use_model=False)
    assert summary["verdict"] != "READY_TO_LAUNCH"
    assert summary["findings"]


def test_accepting_a_line_is_recorded_against_the_person_who_did_it():
    proposal = _propose()
    accepted = drafts.accept(proposal["submission_id"], actor="k.mensah")

    row = db.one("SELECT actor, detail FROM audit WHERE action = 'ACCEPT_LINE'")
    assert row["actor"] == "k.mensah"
    detail = db.loads(row["detail"])
    assert detail["submission_id"] == proposal["submission_id"]
    assert detail["sku"] == accepted["sku"]


def test_a_line_cannot_be_accepted_twice():
    """The ledger is the record of what was decided, and asking it is cheaper
    than a column that could disagree with it."""
    proposal = _propose()
    drafts.accept(proposal["submission_id"], actor="k.mensah")

    again = drafts.accept(proposal["submission_id"], actor="k.mensah")
    assert again["accepted"] is False
    assert "already been accepted" in again["error"]
    assert drafts.pending() == []


def test_an_accepted_line_leaves_the_draft_lane_for_a_real_one():
    proposal = _propose()
    assert _lane_of(_draft_id(proposal)) == stages.DRAFT

    accepted = drafts.accept(proposal["submission_id"], actor="k.mensah")
    built = board.build(limit=400)
    assert _lane_of(_draft_id(proposal), built) == ""
    assert _lane_of(accepted["product_id"], built) == stages.WITH_SUPPLIER


def _draft_id(proposal: dict) -> str:
    return proposal["draft_id"]


def test_a_submission_that_is_not_a_proposal_cannot_be_accepted():
    result = intake.submit_specification_change(
        supplier=SUPPLIER, system_id="supplier-portal", entity_id=VARIANT,
        attribute_path=SAFETY, new_value=["milk", "peanuts"],
        note="Peanut handling introduced.")
    refused = drafts.accept(result["submission_id"], actor="k.mensah")
    assert refused["accepted"] is False
    assert "not a proposed line" in refused["error"]
