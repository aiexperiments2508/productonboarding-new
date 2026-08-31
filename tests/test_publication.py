"""Getting a fix out to the systems that own the listings.

The blast radius already answered which listings a correction reaches. It
answered in internal identifiers, which is a blast radius only this system can
read - everybody who has to *act* on one works in SKUs and thinks in terms of
"which of my channels do I have to tell".

Two properties carry the risk here.

**Dispatch is per system and so is the report.** A marketplace connector that is
down must not hold up the four channels that are answering, and a caller told
"failed" cannot tell the difference between nothing having gone out and almost
everything having.

**The refusals did not move.** Approval on record, evidence unmoved, no open
safety violation - all three are still enforced at the planning boundary. This
layer dispatches and reports; it decides nothing, and a test here would be
worthless if it could publish something the gate would have refused.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_publication.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db  # noqa: E402
from sc.estate import publication, remediation  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402
from sc.state import baseline as baseline_mod  # noqa: E402
from sc.tools import network as network_tools  # noqa: E402

#: The Max. Correcting it reaches the base model's own page too, because a
#: comparison table there quotes both - which is the case this whole system was
#: built around and the one worth asserting SKU resolution against.
MAX_MODEL = "VAR-01B"


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    baseline_mod.get.cache_clear()
    tape.load_tape(reset=True)
    ingest.ingest(tape.jump_to(tape.inject_seq()))
    yield
    db.close()


def _trace(entity_id: str = MAX_MODEL) -> dict:
    return network_tools.trace_dependencies(entity_id)


# ---------------------------------------------------------------------------
# The estate on the publication side
# ---------------------------------------------------------------------------


def test_publication_systems_are_derived_from_the_channels():
    """A publication estate that could disagree with the channel list is a
    second account of where content goes, and the first thing it would disagree
    about is the channel somebody just added."""
    base = baseline_mod.get()
    systems = publication.systems(base)

    assert {s.channel_id for s in systems} == set(base.channels)
    assert len({s.id for s in systems}) == len(systems)
    for system in systems:
        assert system.endpoint.startswith("/mcp/publish/")
        assert system.title and system.owner


def test_a_channel_that_cannot_be_recalled_says_so():
    """A freeze window exists *because* the artefact cannot be pulled back. The
    two facts are the same fact and are not stored twice."""
    base = baseline_mod.get()
    systems = {s.channel_id: s for s in publication.systems(base)}

    for channel_id, system in systems.items():
        expected = base.channels[channel_id].freeze_days == 0
        assert system.recallable is expected


# ---------------------------------------------------------------------------
# The blast radius, in SKUs
# ---------------------------------------------------------------------------


def test_the_blast_radius_answers_in_skus():
    base = baseline_mod.get()
    rows = publication.affected_skus(_trace(), base)

    assert rows, "the correction reached nothing"
    for row in rows:
        assert row["sku"], "a SKU nobody outside can read is not an answer"
        assert row["entity_id"] in base.variants
        assert row["channels"], "a SKU with no channel is not affected"


def test_a_correction_to_one_variant_names_the_siblings_it_reaches():
    """The case this system exists for: a correction scoped to the Max still
    lands on the base model's own page, because a comparison table there quotes
    both. A blast radius that named only the Max would be wrong in the one place
    it matters."""
    base = baseline_mod.get()
    skus = {row["sku"] for row in publication.affected_skus(_trace(), base)}

    assert len(skus) > 1, f"only {skus} - the sibling was not reached"
    assert base.variants[MAX_MODEL].sku in skus


def test_the_systems_to_tell_are_grouped_with_their_skus():
    """"Eleven listings" is a number. "These four SKUs on these three systems"
    is a work list."""
    base = baseline_mod.get()
    groups = publication.blast_to_systems(_trace(), base)

    assert groups
    seen = set()
    for group in groups:
        assert group["system"] not in seen, "a system appears twice"
        seen.add(group["system"])
        assert group["listings"] and group["skus"]
        assert group["listings"] == sorted(group["listings"])
        assert group["skus"] == sorted(group["skus"])


def test_grouping_is_stable_across_reads():
    base = baseline_mod.get()
    trace = _trace()
    assert (publication.blast_to_systems(trace, base)
            == publication.blast_to_systems(trace, base))


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_a_frozen_channel_is_deferred_rather_than_attempted():
    """Attempting it would produce a printed catalogue nobody can correct, which
    is strictly worse than an entry in a report saying it was not attempted."""
    base = baseline_mod.get()
    planned = remediation.plan_dispatch(_trace(), base)

    deferred = [row for row in planned if row["outcome"] == remediation.DEFERRED]
    assert deferred, "nothing was deferred; the print channel should have been"
    for row in deferred:
        assert not row["recallable"]
        assert "freeze" in row["reason"], "a deferral must say why"


def test_planning_a_dispatch_sends_nothing():
    """A reviewer should see that the print channel is frozen before deciding,
    not from a report afterwards - and looking must not publish."""
    base = baseline_mod.get()
    before = db.one("SELECT COUNT(*) AS n FROM committed_actions")["n"]

    remediation.plan_dispatch(_trace(), base)

    assert db.one("SELECT COUNT(*) AS n FROM committed_actions")["n"] == before


def test_a_dispatch_without_an_approval_refuses_every_system():
    """The refusals are properties of the resolution rather than of any one
    channel. Publishing to four channels a resolution nobody approved would be
    four problems instead of none."""
    base = baseline_mod.get()
    result = remediation.dispatch("INC-NONE", "SC-NONE", _trace(), base)

    assert result["committed"] is False
    assert result["reason"], "a refusal must say why"
    assert result["sent"] == 0
    assert result["refused"] == len(result["systems"])
    assert all(row["outcome"] == remediation.REFUSED
               for row in result["systems"])


def test_a_refused_dispatch_reports_one_reason_not_six():
    """Two accounts of why a publish was refused is one account too many."""
    base = baseline_mod.get()
    result = remediation.dispatch("INC-NONE", "SC-NONE", _trace(), base)

    reasons = {row["reason"] for row in result["systems"]}
    assert len(reasons) == 1
    assert reasons == {result["reason"]}


def test_the_dispatch_report_counts_agree_with_its_rows():
    base = baseline_mod.get()
    result = remediation.dispatch("INC-NONE", "SC-NONE", _trace(), base)
    rows = result["systems"]

    assert result["sent"] == sum(
        1 for r in rows if r["outcome"] == remediation.SENT)
    assert result["deferred"] == sum(
        1 for r in rows if r["outcome"] == remediation.DEFERRED)
    assert result["refused"] == sum(
        1 for r in rows if r["outcome"] == remediation.REFUSED)


def test_a_channel_never_sent_to_is_not_reported_as_reverted():
    """A channel that could not be recalled was never sent to, so it has nothing
    to roll back - and reporting it as reverted would be a lie about a printed
    page."""
    base = baseline_mod.get()
    result = remediation.revert("INC-NONE", "SC-NONE", _trace(), base)

    deferred = [r for r in result["systems"]
                if r["outcome"] == remediation.DEFERRED]
    assert deferred
    for row in deferred:
        assert row["reason"].startswith("never sent")


# ---------------------------------------------------------------------------
# The API
# ---------------------------------------------------------------------------


def test_the_impact_route_answers_in_skus_and_systems():
    from fastapi.testclient import TestClient

    from sc.main import app

    body = TestClient(app).get(f"/api/publication/impact/{MAX_MODEL}").json()

    assert body["skus"] and body["systems"] and body["dispatch_plan"]
    assert body["totals"]["listings"] >= len(body["systems"])
    assert {row["sku"] for row in body["skus"]}


def test_a_dispatch_route_without_its_identifiers_refuses():
    from fastapi.testclient import TestClient

    from sc.main import app

    response = TestClient(app).post("/api/publication/dispatch", json={})
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Each publisher, as its own MCP endpoint
#
# The ingest estate is ten servers because ten systems send data. This is six
# because six channels own listings, and the partition matters more here rather
# than less: these are the only servers in the estate that can change what a
# shopper sees.
# ---------------------------------------------------------------------------


def test_every_publisher_declares_which_of_its_tools_mutate():
    """An operator who wants to show somebody a blast radius should not have to
    hand over the ability to act on it.

    The count used to be in this test's name, which made the name wrong the
    moment the surface grew. What matters is not how many tools there are but
    that the server serves exactly what it declares, and that the mutating set
    is declared rather than guessed at from the verbs.
    """
    import asyncio

    from sc.estate import publication_server

    base = baseline_mod.get()
    for system in publication.systems(base):
        built = publication_server.build(system)
        names = sorted(t.name for t in asyncio.run(built.list_tools()))
        assert names == sorted(publication_server.TOOLS)
        assert set(publication_server.MUTATING) <= set(names)
        assert "publish_correction" in publication_server.MUTATING


def test_the_declared_verbs_cover_every_tool_that_can_write():
    """``/api/publication/systems`` hands out ``VERBS``. A surface that could
    write in a way the verb list did not name would be a listing that lies
    about what the estate can do."""
    from sc.estate import publication_server

    assert len(publication.VERBS) >= len(publication_server.MUTATING)
    for verb in ("redact", "discharge"):
        assert verb in publication.VERBS


def test_a_publisher_will_not_report_another_channels_impact():
    """A marketplace connector has no business enumerating what the print
    channel is about to publish."""
    from sc.estate import publication_server

    base = baseline_mod.get()
    systems = {s.channel_id: s for s in publication.systems(base)}
    trace = _trace()
    reached = {g["channel_id"] for g in publication.blast_to_systems(trace, base)}

    hit = systems[sorted(reached)[0]]
    missed = next(s for cid, s in systems.items() if cid not in reached)

    assert publication_server._impact(hit, MAX_MODEL)["affected"] is True
    answer = publication_server._impact(missed, MAX_MODEL)
    assert answer["affected"] is False
    assert answer["skus"] == []


def test_a_publisher_refuses_a_run_it_could_not_stop():
    """A tool that would start a print run inside its freeze window should not
    exist, rather than existing and expecting its caller to check first."""
    from sc.estate import publication_server

    base = baseline_mod.get()
    frozen = next(s for s in publication.systems(base) if not s.recallable)

    answer = publication_server._publish(frozen, "INC-X", "SC-X", MAX_MODEL)

    assert answer["sent"] is False
    assert "freeze" in answer["reason"]


def test_reaching_a_publisher_over_a_pipe_does_not_exempt_it():
    """The safeguards travel with the tool rather than the caller. There is
    deliberately no code in the server that could publish on its own."""
    from sc.estate import publication_server

    base = baseline_mod.get()
    recallable = next(s for s in publication.systems(base) if s.recallable)

    answer = publication_server._publish(recallable, "INC-NONE", "SC-NONE",
                                         MAX_MODEL)

    assert answer["sent"] is False
    assert answer["committed"] is False
    assert answer["reason"], "a refusal reached over MCP must still say why"


def test_a_publisher_endpoint_is_distinct_from_an_ingest_one():
    """An operator handing out endpoints should be able to see which can change
    a live listing from the path alone."""
    from sc.estate import server as ingest_server

    base = baseline_mod.get()
    publishers = {s.endpoint for s in publication.systems(base)}
    ingest = {ingest_server.endpoint(s.id)
              for s in __import__("sc.estate.manifest", fromlist=["SYSTEMS"]).SYSTEMS}

    assert not (publishers & ingest)
    assert all("/publish/" in path for path in publishers)
    assert not any("/publish/" in path for path in ingest)
