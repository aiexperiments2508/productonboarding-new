"""The external estate: who feeds the retailer, and how badly.

Two properties are under test here and they pull against each other, which is
why the file exists.

The estate has to look alive. Ten systems, batches of varying size, irregular
pauses, deliveries that interleave. A reader watching the Ingest Fabric should
see several systems talking at once, because that is what a retailer's morning
actually looks like.

The record has to be reproducible. Same seed, same facts, same trace hash -
the audit trail is worth nothing otherwise, and a demo that cannot be rehearsed
is not a demo.

Both hold because the randomness is in the *schedule*, drawn from the seed, and
the ordering is in *ingestion*, which sorts by sequence. The tests below check
each half and then check the seam: that arrivals landing in any order leave the
same record behind.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("DB_PATH", "data/test_estate.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db  # noqa: E402
from sc.estate import arrivals, emitter, manifest  # noqa: E402
from sc.estate.defects import ALL, Defect  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    yield
    db.close()


def _owned() -> dict[str, list[int]]:
    """Every sequence on the tape, dealt to the system that carried it."""
    owned: dict[str, list[int]] = {s.id: [] for s in manifest.SYSTEMS}
    for row in db.query("SELECT seq, type, source FROM events ORDER BY seq"):
        owner = emitter.owner_of(row["type"], row["source"], row["seq"])
        owned[owner].append(row["seq"])
    return owned


def _event_ids() -> dict[int, str]:
    return {r["seq"]: r["id"]
            for r in db.query("SELECT seq, id FROM events")}


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------


def test_the_manifest_declares_ten_systems_with_owners():
    systems = manifest.SYSTEMS

    assert len(systems) >= 10
    assert len({s.id for s in systems}) == len(systems), "duplicate system id"
    for system in systems:
        assert system.title and system.owner and system.why
        assert system.emits, f"{system.id} emits nothing"
        assert 0.0 <= system.defect_rate <= 1.0
        for defect in system.defects:
            assert defect in ALL


def test_no_system_is_named_outside_the_manifest():
    """A system that has to be mentioned by name in code is a system nobody can
    add. The manifest is where they live; everything else asks it."""
    allowed = {ROOT / "sc" / "estate" / "manifest.py",
               ROOT / "sc" / "estate" / "emitter.py",
               Path(__file__)}
    offenders: list[str] = []
    for path in sorted((ROOT / "sc").rglob("*.py")):
        if path in allowed or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for system in manifest.SYSTEMS:
            if f'"{system.id}"' in text or f"'{system.id}'" in text:
                offenders.append(f"{path.relative_to(ROOT)} names {system.id}")
    assert not offenders, "; ".join(offenders)


def test_the_estate_spans_good_and_bad_citizens():
    """An estate where everything is equally suspect measures nothing: with no
    contrast, no finding tells a reviewer which system to go and fix."""
    clean = [s for s in manifest.SYSTEMS if s.well_behaved]
    messy = [s for s in manifest.SYSTEMS if len(s.defects) > 1]

    assert clean, "no system is trustworthy, so nothing can arbitrate"
    assert messy, "no system is unreliable, so validation is never exercised"


# ---------------------------------------------------------------------------
# Delivering in batches, at irregular times
# ---------------------------------------------------------------------------


def test_a_system_delivers_in_batches_of_varying_size_and_spacing():
    owned = _owned()
    plan = emitter.schedule(owned)

    busiest = max(plan, key=lambda k: len(plan[k]))
    batches = plan[busiest]
    assert len(batches) > 1, f"{busiest} delivered everything in one go"
    assert len({b.size for b in batches}) > 1, "every batch is the same size"
    assert len({b.after for b in batches}) > 1, "every pause is the same"

    for system_id, owned_seqs in owned.items():
        carried = [s for b in plan[system_id] for s in b.sequences]
        assert carried == sorted(owned_seqs), \
            f"{system_id} lost, duplicated or reordered its own events"


def test_the_estate_delivers_concurrently():
    """Several systems in flight at once, not a queue being drained."""
    plan = emitter.schedule(_owned())
    assert len(emitter.overlaps(plan)) >= 1


def test_the_same_seed_produces_the_same_schedule():
    owned = _owned()
    assert emitter.schedule(owned, 20802) == emitter.schedule(owned, 20802)
    # And a different seed genuinely reshuffles it, or the first assertion is
    # only telling us the function is pure.
    assert emitter.schedule(owned, 20802) != emitter.schedule(owned, 999)


def test_adding_a_system_does_not_reshuffle_the_others():
    """Each system draws from its own named stream. Sharing one generator would
    make every schedule depend on how many systems came before it, so adding an
    eleventh would invalidate every expectation about the ten."""
    owned = _owned()
    first = manifest.SYSTEMS[0]
    before = emitter.schedule_for(first, owned[first.id])
    trimmed = {k: v for k, v in owned.items() if k != manifest.SYSTEMS[-1].id}
    after = emitter.schedule_for(first, trimmed[first.id])
    assert before == after


# ---------------------------------------------------------------------------
# Arrival, then sequencing
# ---------------------------------------------------------------------------


def test_an_arrival_names_its_system_batch_and_instant():
    plan = emitter.schedule(_owned())
    ids = _event_ids()
    system_id = next(k for k, v in plan.items() if v)
    batch = plan[system_id][0]

    rows = arrivals.record(batch, ids)
    assert rows
    for row in rows:
        assert row["system_id"] == system_id
        assert row["batch_id"].startswith("BAT-")
        assert row["arrived_at"]
        assert row["seq"] in batch.sequences
    # One batch identifier shared across the delivery, not one per event.
    assert len({r["batch_id"] for r in rows}) == 1


def test_a_redelivered_batch_is_recorded_once():
    """A system retrying after a dropped connection has done nothing wrong."""
    plan = emitter.schedule(_owned())
    ids = _event_ids()
    batch = next(b for bs in plan.values() for b in bs)

    arrivals.record(batch, ids)
    arrivals.record(batch, ids)
    held = db.one("SELECT COUNT(*) AS n FROM arrivals")["n"]
    assert held == len(batch.sequences)


def test_ingestion_follows_sequence_not_arrival():
    """The release point walks forward from the cursor and stops at the first
    gap. Releasing to the highest arrived sequence instead would push the
    watermark past an event still in flight, and that event would then be
    refused when it landed - silently, on a run that reports success."""
    ids = _event_ids()
    ordered = sorted(ids)[:6]

    late, rest = ordered[0], ordered[1:]
    for sequence in rest:
        arrivals.record(
            emitter.Batch(system_id="supplier-portal", ordinal=sequence,
                          sequences=(sequence,), after=0.0, defects={}), ids)

    # Everything except the first has landed, so nothing may be released yet.
    assert arrivals.releasable(late - 1) == late - 1

    arrivals.record(
        emitter.Batch(system_id="supplier-portal", ordinal=0,
                      sequences=(late,), after=0.0, defects={}), ids)
    assert arrivals.releasable(late - 1) == ordered[-1]


def test_arrival_order_does_not_change_the_record():
    """The property the whole split exists to protect."""
    ids = _event_ids()
    window = sorted(ids)[:24]

    def facts_after(order: list[int]) -> list[tuple]:
        db.init_db(drop=True)
        tape.load_tape(reset=True)
        fresh_ids = _event_ids()
        for sequence in order:
            arrivals.record(
                emitter.Batch(system_id="supplier-portal", ordinal=sequence,
                              sequences=(sequence,), after=0.0, defects={}),
                fresh_ids)
        ingest.ingest(tape.jump_to(arrivals.releasable(0)))
        return [(r["entity_id"], r["attr"], r["value"], r["valid_from"])
                for r in db.query(
                    "SELECT entity_id, attr, value, valid_from FROM facts"
                    " ORDER BY entity_id, attr, value, valid_from")]

    forward = facts_after(window)
    backward = facts_after(list(reversed(window)))

    assert forward, "nothing was recorded, so this proves nothing"
    assert forward == backward


# ---------------------------------------------------------------------------
# Defects
# ---------------------------------------------------------------------------


def test_every_defect_is_named_and_attributed():
    plan = emitter.schedule(_owned())
    ids = _event_ids()
    for batches in plan.values():
        for batch in batches:
            arrivals.record(batch, ids)

    named = {d for row in arrivals.recent(10_000) for d in row["defects"]}
    assert named, "the estate introduced no defects at all"
    assert named <= {str(d) for d in ALL}, f"undeclared defect: {named}"

    for row in arrivals.recent(10_000):
        if row["defects"]:
            system = manifest.BY_ID[row["system_id"]]
            for defect in row["defects"]:
                assert Defect(defect) in system.defects, \
                    f"{system.id} stamped {defect}, which it does not declare"


def test_a_well_behaved_system_stamps_nothing():
    plan = emitter.schedule(_owned())
    for system in manifest.SYSTEMS:
        if not system.well_behaved:
            continue
        stamped = [d for b in plan[system.id] for d in b.defects.values()]
        assert not stamped, f"{system.id} is declared clean and stamped {stamped}"


def test_every_stamped_defect_is_detected():
    """A defect the estate can produce and nothing downstream reports is a lie
    in the answer key. This is the check that keeps the closed set honest.

    Detection is asserted against the deterministic surfaces rather than a
    model: each defect has to be nameable by a rule, or it is not a defect this
    system can claim to catch.
    """
    from sc.estate import detection

    undetected = [d for d in ALL if not detection.detector_for(d)]
    assert not undetected, \
        f"the estate stamps {undetected} and nothing reports them"


# ---------------------------------------------------------------------------
# Each system is reachable over a protocol
# ---------------------------------------------------------------------------


def test_every_system_exposes_an_mcp_surface():
    """Ten servers, not one server with a system argument.

    Built per system so that a client asking `tools/list` gets an answer scoped
    to who it is talking to. Checked by building each one and listing its
    tools - the HTTP round-trip needs a running application and is exercised by
    starting it; what this asserts is that every declared system has a surface
    at all, which is the thing that would silently stop being true if somebody
    added a system to the manifest and nowhere else.
    """
    import asyncio

    from sc.estate import server as estate_server

    for system in manifest.SYSTEMS:
        built = estate_server.build(system)
        names = sorted(t.name for t in asyncio.run(built.list_tools()))
        assert names == sorted(estate_server.TOOLS), \
            f"{system.id} exposes {names}"


def test_a_system_will_not_hand_over_another_systems_payload():
    """An estate where every system can read every other one's traffic is a
    single database with ten front doors."""
    from sc.estate import delivery, server as estate_server

    released = tape.jump_to(tape.inject_seq())
    delivery.deliver(released)

    landed = arrivals.recent(200)
    assert landed, "nothing was delivered, so this proves nothing"
    row = landed[0]
    owner = manifest.BY_ID[row["system_id"]]
    other = next(s for s in manifest.SYSTEMS if s.id != owner.id)

    mine = estate_server._payload(owner, row["event_id"])
    theirs = estate_server._payload(other, row["event_id"])

    assert mine.get("event_id") == row["event_id"]
    assert "error" in theirs and other.id in theirs["error"]


def test_a_systems_endpoint_ends_in_a_slash():
    """Starlette's Mount strips the prefix before the sub-app sees the request,
    so `/mcp/{id}` arrives as an empty path and the only route is `/`. Without
    the slash the endpoint answers 405, which reads as a broken server rather
    than a wrong address - and the address is what a connection record holds."""
    from sc.estate import server as estate_server

    for system in manifest.SYSTEMS:
        assert estate_server.endpoint(system.id).endswith("/")
    for entry in [e for e in [{"url": estate_server.endpoint(s.id)}
                              for s in manifest.SYSTEMS]]:
        assert not entry["url"].endswith("//")


# ---------------------------------------------------------------------------
# The map's systems tier
# ---------------------------------------------------------------------------


def test_every_system_that_has_delivered_draws_an_edge():
    """The regression test for six boxes with no lines.

    The map resolves a system-to-source edge by reading the product out of an
    event's payload, and the tape names products five different ways: a
    supplier feed says ``entity_id``, a channel acknowledgement says
    ``variant_id``, a document and an email say ``entities``. Only the first was
    read, so six of the eleven systems had delivered dozens of events and drew
    as islands - not because they were silent, but because nobody was listening
    in their dialect.

    A system that has genuinely delivered nothing is still allowed to draw no
    edge. That is the estate showing a source that has gone quiet, which is a
    thing somebody needs to see.
    """
    from sc import db
    from sc.estate import reach as reach_mod
    from sc.estate import topology
    from sc.replay import ingest, tape
    from sc.state import baseline as baseline_mod

    db.init_db(drop=True)
    baseline_mod.get.cache_clear()
    tape.load_tape(reset=True)
    ingest.ingest(tape.jump_to(10_000))

    base = baseline_mod.get()
    # The reach, not `nodes_and_edges`. The systems *tier* is built from the
    # connection records, which only exist once the application has dialled
    # each system at startup - so asserting on the drawn nodes here would test
    # whether the app had booted rather than whether the payload reader works.
    drawn = {system for system, sources in topology._supplier_reach().items()
             if sources}

    delivered: dict[str, bool] = {}
    rows = db.query(
        "SELECT a.system_id AS system_id, e.payload AS payload"
        "  FROM arrivals a JOIN events e ON e.id = a.event_id")
    for row in rows:
        payload = db.loads(row["payload"])
        delivered[row["system_id"]] = (
            delivered.get(row["system_id"], False)
            or bool(reach_mod.suppliers_of(base, payload)))

    silent = sorted(s for s, any_product in delivered.items()
                    if any_product and s not in drawn)
    assert not silent, f"these systems delivered product data and drew no edge: {silent}"


def test_the_payload_reader_understands_every_spelling_the_tape_uses():
    """One reader, shared by the map and the arrival window.

    Two copies would drift, and the first thing they would drift about is the
    spelling nobody remembered to add.
    """
    from sc.estate import reach as reach_mod
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    variant = sorted(base.variants)[0]
    product = base.product_of_variant[variant]
    listing = base.listings_of[variant][0]

    for payload in (
        {"entity_id": variant},
        {"variant_id": variant},
        {"product": product},
        {"entities": [variant]},
        {"listing_id": listing},
    ):
        assert reach_mod.products_of(base, payload) == {product}, payload
        assert reach_mod.suppliers_of(base, payload) == {
            base.products[product].supplier}, payload

    # A payload about a document is not a payload about a product.
    assert reach_mod.products_of(base, {"doc_id": "DOC-01"}) == set()


# ---------------------------------------------------------------------------
# A quiet system is still a system


def test_recent_deliveries_finds_a_quiet_system_behind_a_busy_one():
    """A feed that delivers in ones and twos must not be crowded off its own
    console by one that delivers in thousands.

    `_recent` used to read the newest five hundred arrivals across the whole
    estate and filter to one system afterwards, which is not a slower way to
    the same answer - it is a different answer. Once a busy system has filled
    that window, a quiet one reports having delivered nothing while its rows
    sit in the table just past the cut, and the console it feeds goes blank
    with no error anywhere.

    `label-artwork` is the live example: thirteen documents on the tape against
    a data pool delivering thousands. This reproduces it with two systems and
    no tape at all.
    """
    from sc.estate import server as estate_server

    busy, quiet = manifest.SYSTEMS[0], manifest.SYSTEMS[1]

    # The quiet system delivers first, so every one of its rows is older than
    # every one of the busy system's - which is exactly the case an estate-wide
    # window truncates away.
    quiet_batch = emitter.Batch(system_id=quiet.id, ordinal=1,
                                sequences=(1, 2, 3), after=0.0, defects={})
    arrivals.record(quiet_batch, {1: "EVT-Q1", 2: "EVT-Q2", 3: "EVT-Q3"})

    for ordinal in range(2, 12):
        base = ordinal * 100
        seqs = tuple(range(base, base + 60))
        arrivals.record(
            emitter.Batch(system_id=busy.id, ordinal=ordinal, sequences=seqs,
                          after=0.0, defects={}),
            {s: f"EVT-B{s}" for s in seqs})

    assert db.one("SELECT COUNT(*) AS n FROM arrivals")["n"] > 500

    rows = estate_server._recent(quiet, limit=20)
    assert [r["event_id"] for r in rows] == ["EVT-Q3", "EVT-Q2", "EVT-Q1"], \
        "the quiet system's own deliveries were truncated away by the busy one"

    # And the busy system is still capped by what it was asked for.
    assert len(estate_server._recent(busy, limit=20)) == 20
