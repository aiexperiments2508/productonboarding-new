"""The back-office reference pack, and what it must not disturb.

Four systems deliver stock, trading, campaigns and a certificate register. None
of it is an assertion about a product, and the whole risk of adding it is that
some part of this platform treats it as one anyway - because three modules read
the ``events`` table with no lane predicate and four more read payloads looking
for keys they recognise.

So the tests here come in two halves. The first half checks the pack is what it
claims: reproducible, delivered, and still carrying the conditions the insight
views are built to find. The second half checks the pack is *invisible* - that
the transport's denominator, the live feed, the fact store, a readiness verdict
and the arrival window all read exactly as they did before it existed.

The second half is the important one. A failure there is not a broken feature;
it is a readiness verdict moving because a depot counted a pallet.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pytest

os.environ.setdefault("DB_PATH", "data/test_kg_data.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db  # noqa: E402
from sc.estate import manifest, reach as reach_mod  # noqa: E402
from sc.kg import payloads, synth  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402

REFERENCE_EVENTS = 220


@pytest.fixture(scope="module")
def pack_file(tmp_path_factory):
    """The pack, written once into the test's own directory.

    Not into ``data/``. A test that wrote the real pack would make the suite's
    result depend on whether somebody had run the generator, and would leave a
    file behind that the next run silently reused.
    """
    target = tmp_path_factory.mktemp("kg") / "backoffice.jsonl"
    synth.write(target)
    return target


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    baseline_mod.get.cache_clear()
    tape.load_tape(reset=True)
    yield
    db.close()


def _payloads(kind: str) -> list[dict]:
    return [json.loads(e["payload"]) if isinstance(e["payload"], str)
            else e["payload"]
            for e in synth.build() if e["type"] == kind]


# ---------------------------------------------------------------------------
# The pack is what it claims


def test_the_reference_pack_is_byte_identical_for_a_seed():
    """Same seed, same bytes. The property the whole generator is arranged for.

    A demo rehearsed on Friday has to behave identically on Sunday, on somebody
    else's laptop. Drawing from a shared generator, or from ``random``, or from
    a clock would each break this in a way that only shows up on the machine
    you are not holding.
    """
    first = json.dumps(synth.build(), sort_keys=True)
    second = json.dumps(synth.build(), sort_keys=True)
    assert first == second
    assert len(json.loads(first)) == REFERENCE_EVENTS


def test_every_reference_event_lands_as_an_arrival(pack_file):
    """An event with no arrival row is an event nothing can read.

    The estate's MCP servers answer out of the ``arrivals`` table, so the back
    office and the graph loader both reach this data through it. A reference
    event that arrived nowhere would exist in the database and be unreachable
    from outside the process - which is the one failure mode that looks like
    success from in here.
    """
    tape.load_reference(pack_file, reset=True)

    events = db.one("SELECT COUNT(*) AS n FROM events WHERE lane = 'REF'")["n"]
    arrived = db.one(
        "SELECT COUNT(*) AS n FROM arrivals a JOIN events e ON e.id = a.event_id"
        " WHERE e.lane = 'REF'")["n"]
    assert events == REFERENCE_EVENTS
    assert arrived == REFERENCE_EVENTS

    carriers = {r["system_id"] for r in db.query(
        "SELECT DISTINCT system_id FROM arrivals a JOIN events e"
        " ON e.id = a.event_id WHERE e.lane = 'REF'")}
    assert len(carriers) == 4
    for system_id in carriers:
        system = manifest.BY_ID[system_id]
        assert system.well_behaved, f"{system_id} declares defects"
        assert not system.accepts, f"{system_id} has an intake surface"


def test_nothing_in_the_pack_is_stamped_with_a_defect(pack_file):
    """These four systems declare no defects, so nothing may stamp one.

    Every detector in `sc/estate/detection.py` reads an attribute path, a
    document version or a media requirement. None of them can say anything
    true about a pallet count, so a defect here would be an assertion no rule
    could ever check - which is what `test_every_stamped_defect_is_detected`
    exists to prevent, from the other direction.
    """
    tape.load_reference(pack_file, reset=True)

    stamped = db.query(
        "SELECT a.defects FROM arrivals a JOIN events e ON e.id = a.event_id"
        " WHERE e.lane = 'REF' AND a.defects != '[]'")
    assert stamped == []


def test_loading_the_pack_twice_changes_nothing(pack_file):
    """Boot is not a one-time event. The second one must be a no-op.

    `append_live` inserts without OR IGNORE and would raise on a repeat, which
    is one of the reasons this lane is loaded rather than appended.
    """
    tape.load_reference(pack_file, reset=True)
    again = tape.load_reference(pack_file)

    assert again["skipped"] is True
    assert db.one(
        "SELECT COUNT(*) AS n FROM events WHERE lane = 'REF'")["n"] == \
        REFERENCE_EVENTS
    assert db.one(
        "SELECT COUNT(*) AS n FROM arrivals a JOIN events e ON e.id = a.event_id"
        " WHERE e.lane = 'REF'")["n"] == REFERENCE_EVENTS


def test_a_missing_pack_is_not_an_error(tmp_path):
    """A checkout that has not run the generator still has to boot.

    `bootstrap.ensure_ready` calls this, and a front door that refuses to open
    because an optional artefact is absent is a worse failure than a graph that
    says it holds nothing.
    """
    result = tape.load_reference(tmp_path / "absent.jsonl")
    assert result["missing"] is True
    assert result["loaded"] == 0


# ---------------------------------------------------------------------------
# The pack is invisible


def test_no_reference_event_becomes_a_product_fact(pack_file):
    """The requirement, tested directly.

    Warehouse stock, a month's takings and a campaign are not launch-readiness
    attributes. `ingest._handle` dispatches through `HANDLERS.get`, so absence
    from that four-entry table is the whole of the skip - but "the skip works"
    is worth asserting rather than reasoning about, because the cost of being
    wrong is a verdict that moved on evidence with nothing to say about it.
    """
    before = db.one("SELECT COUNT(*) AS n FROM facts")["n"]
    tape.load_reference(pack_file, reset=True)
    assert db.one("SELECT COUNT(*) AS n FROM facts")["n"] == before

    # And directly: handed to the ingester, it produces nothing and writes
    # nothing.
    events = [tape._row_to_event(r) for r in db.query(
        "SELECT * FROM events WHERE lane = 'REF' ORDER BY seq")]
    assert ingest.ingest(events) == []
    assert db.one("SELECT COUNT(*) AS n FROM facts")["n"] == before


def test_a_readiness_verdict_is_unchanged_by_the_reference_pack(pack_file):
    """The consequence a reader would actually notice.

    If any of this leaked into the fact store or the arrival window, the first
    visible symptom would be a product's verdict or its open findings changing
    for no reason a reviewer could name. This asserts they do not.
    """
    from sc import readiness

    base = baseline_mod.get()
    sample = sorted(base.variants)[:8]

    before = {vid: readiness.assess(vid, use_model=False, include_record=False)
              for vid in sample}
    tape.load_reference(pack_file, reset=True)
    after = {vid: readiness.assess(vid, use_model=False, include_record=False)
             for vid in sample}

    for vid in sample:
        assert before[vid]["verdict"] == after[vid]["verdict"], vid
        assert before[vid]["checks_complete"] == after[vid]["checks_complete"]
        # The whole finding, not a code: the check, the subject it names, the
        # system it blames and the severity all have to be untouched.
        assert before[vid]["findings"] == after[vid]["findings"], vid


def test_the_reference_lane_is_invisible_to_the_transport(pack_file):
    """The tape's denominator, its end, its feed and its clock all stand still.

    Each of these is a query that could have widened. `total_events` is the
    progress bar's denominator; `last_tape_seq` is the jump clamp; `released`
    is the one query in the module that spans lanes; `live_events` is the
    Ingest Fabric's live half; `sim_now` drives every as-of read in the system.
    A reference row reaching any of them is a silent fault, which is why they
    are checked together rather than trusted individually.
    """
    before = (tape.total_events(), tape.last_tape_seq(),
              [e.id for e in tape.released(limit=500)],
              [e.id for e in tape.live_events()], tape.sim_now())

    tape.load_reference(pack_file, reset=True)

    after = (tape.total_events(), tape.last_tape_seq(),
             [e.id for e in tape.released(limit=500)],
             [e.id for e in tape.live_events()], tape.sim_now())

    assert before == after

    # And a rewind does not take the reference data with it.
    tape.load_tape(reset=True)
    assert db.one(
        "SELECT COUNT(*) AS n FROM events WHERE lane = 'REF'")["n"] == \
        REFERENCE_EVENTS


def test_reference_payloads_name_no_product_the_window_would_count():
    """A depot's weekly count is not "six things arrived for this product".

    `sc/estate/reach.py` reads seven top-level keys, and three modules with no
    lane predicate go through it - the arrival window on the product screen,
    a product's lifecycle timeline, and the estate map's supplier edges. A
    reference payload that named a variant where `refs_of` looks would inflate
    all three, plausibly, with no error anywhere.

    So every payload is checked against the real function rather than against a
    list of key names copied into this file.
    """
    base = baseline_mod.get()
    for event in synth.build():
        payload = event["payload"]
        assert reach_mod.refs_of(payload) == [], event["type"]
        assert reach_mod.products_of(base, payload) == set(), event["type"]
        assert reach_mod.suppliers_of(base, payload) == set(), event["type"]
        # The guard the generator itself runs, asserted independently.
        payloads.assert_safe(payload)


# ---------------------------------------------------------------------------
# The planted conditions are still planted


def test_the_certificate_register_has_a_lapsing_cohort():
    """Insight one needs certificates that genuinely lapse soon.

    Measured against the horizon and never against today: every as-of read in
    this system runs on the replay clock, so a window anchored to real time
    would pass on the day it was written and fail silently a year later.

    The cohort is also chosen so it is unexpired at *every* point in the
    replay - the soon bucket sits past the horizon's end - which is what stops
    the count depending on how far somebody has played the tape.
    """
    pack = synth._load()
    start, days = pack.horizon_start, pack.horizon_days
    horizon_end = start + timedelta(days=days)

    certificates = _payloads("CERTIFICATE")
    assert len(certificates) == 72

    expires = {c["certificate_ref"]: date.fromisoformat(c["expires_on"])
               for c in certificates}
    soon = [ref for ref, when in expires.items()
            if start <= when <= start + timedelta(days=90)]
    expired = [ref for ref, when in expires.items() if when < start]

    assert len(soon) == synth.EXPIRING_SOON
    assert len(expired) == synth.ALREADY_EXPIRED
    assert all(expires[ref] > horizon_end for ref in soon), \
        "a lapsing certificate expires mid-replay, so the count would drift"

    # The register keys off the catalog's own references, so a certificate
    # shared by two variants is one node with two products hanging off it -
    # which is the whole basis of "products sharing a certification".
    shared = [c for c in certificates if len(c["scope"]) > 1]
    assert shared, "no certificate covers more than one variant"


def test_the_scheme_is_read_off_the_catalogs_own_reference():
    """Not drawn. The catalog encoded it in the prefix and this reads it.

    That is what makes the compliance domain sit on the retailer's data instead
    of beside it: `UKCA-2411` is a real value on a real variant, and the node
    it becomes is joined by that value rather than by an invented key.
    """
    pack = synth._load()
    for certificate in _payloads("CERTIFICATE"):
        ref = certificate["certificate_ref"]
        assert certificate["scheme"] == synth.dom.scheme_of(ref)
        for variant in certificate["scope"]:
            assert pack.cert_ref[variant] == ref


def test_stock_sits_where_it_cannot_lawfully_ship():
    """Insight three needs a depot holding stock for a market it cannot serve.

    UKCA does not satisfy CE. Rotterdam serves Germany and France, both of
    which require CE. Every UKCA-certified variant in CE scope is stocked
    there, so the finding is real: nobody did anything wrong, no single system
    can see it, and it stops a shipment.
    """
    pack = synth._load()
    eligible = set(synth.ce_scope_ukca(pack))
    assert len(eligible) >= 10, "not enough real UKCA lines to make the point"

    rotterdam = [s for s in _payloads("STOCK_SNAPSHOT")
                 if s["warehouse_id"] == "WH-ROTTERDAM"]
    assert rotterdam
    stocked = {line["variant_id"] for line in rotterdam[0]["lines"]}
    assert eligible <= stocked

    serves = set(rotterdam[0]["serves_markets"])
    requiring = {m.code for m in synth.dom.MARKETS
                 if "REG-CE-768-2008" in m.requires}
    assert serves & requiring, "the depot no longer serves a CE market"

    # And UKCA genuinely does not satisfy the regulation those markets require.
    ce = synth.dom.BY_REGULATION["REG-CE-768-2008"]
    assert "UKCA" not in ce.accepted_schemes


def test_the_best_sellers_without_media_are_real_gaps():
    """Insight two ranks a real finding rather than inventing one.

    The missing role is genuine - fifty-three variants lack one their branch
    requires, and `sc/readiness/checks.py` already reports it. Only the ranking
    is arranged, because sales figures do not exist in this catalog at all and
    without them "top selling" has nothing to sort by.
    """
    pack = synth._load()
    gaps = set(synth._gaps(pack))
    assert len(gaps) > 40, "the real media gap has gone away"

    boosted = set(synth._bestsellers_without_media(pack, synth.DEFAULT_SEED))
    assert len(boosted) == synth.BESTSELLERS_WITHOUT_MEDIA
    assert boosted <= gaps, "a boosted variant is not actually missing media"

    ranked_first = set()
    for period in _payloads("SALES_PERIOD"):
        for line in period["lines"]:
            if line["rank_in_category"] == 1:
                ranked_first.add(line["variant_id"])
    assert boosted <= ranked_first


def test_cross_sell_pairs_share_more_than_one_campaign():
    """Insight four needs an overlap stronger than coincidence.

    One shared campaign happens by accident when a campaign draws twenty
    members. Two is a signal, so the question asks for two and the pack
    supplies pairs that have them - drawn from different products, because two
    variants of one product in two sizes is not a cross-sell candidate.
    """
    pack = synth._load()
    pairs = synth._cross_sell_pairs(pack, synth.DEFAULT_SEED)
    assert len(pairs) == synth.CROSS_SELL_PAIRS

    members = [set(c["members"]) for c in _payloads("CAMPAIGN")]
    for left, right in pairs:
        assert pack.variants[left]["product_id"] != \
            pack.variants[right]["product_id"]
        shared = sum(1 for group in members if left in group and right in group)
        assert shared >= 2, f"{left} and {right} share only {shared} campaigns"


def test_every_planted_condition_is_named():
    """The plants are documented where somebody changing them will look.

    A condition arranged in code and explained nowhere is one the next person
    removes while tidying, and the insight it fed then returns an empty table
    that reads exactly like a correct answer.
    """
    assert set(synth.PLANTED) == {
        "certificates-expiring", "bestsellers-without-media",
        "stock-it-cannot-ship", "cross-sell-pairs",
    }
    for description in synth.PLANTED.values():
        assert len(description) > 30
