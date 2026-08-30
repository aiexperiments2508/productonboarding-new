"""The capability directory, and the boundary it must not blur.

Agent Cards were already published one per peer, at the address the A2A
specification puts them. That is correct and it is not discoverable: a peer that
already knows an identifier can fetch a card, and a peer that knows only the
host cannot find out what is here.

The directory closes that. What it must not do is smooth over the difference
between a capability this system *implements* and one it merely knows how to
*reach* - that difference is the difference between an agent and an address
book, and it matters most to the reader least able to check it.

The second half of this file guards the other boundary: connecting a system
records what it says it can do and must not, by itself, let a model call any of
it. The evidence desk is an allowlist, and an allowlist a stranger can widen by
connecting is a formality.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_directory.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db  # noqa: E402
from sc.a2a import directory as directory_mod  # noqa: E402
from sc.a2a.agents import AGENTS  # noqa: E402
from sc.graph import evidence  # noqa: E402
from sc.mcp import connections  # noqa: E402

BASE = "http://127.0.0.1:8000"


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    yield
    db.close()


def _mounted() -> list[dict]:
    """What `a2a.server.mount` would have returned with every peer published."""
    return [{"id": a.id, "name": a.name} for a in AGENTS]


def _connect(system_id: str, tools: list[str], state: str = "connected"):
    return connections.upsert(
        system_id, title=system_id.replace("-", " ").title(), owner="external",
        url=f"http://example.invalid/{system_id}", transport="http",
        state=state, detail="declared by a test", discovered=tools)


# ---------------------------------------------------------------------------
# The directory
# ---------------------------------------------------------------------------


def test_the_directory_names_every_published_peer():
    listing = directory_mod.build(BASE, _mounted())
    peers = [c for c in listing["capabilities"] if c["kind"] == "peer"]

    assert {p["id"] for p in peers} == {a.id for a in AGENTS}
    for peer in peers:
        assert peer["card_url"].endswith("/.well-known/agent-card.json")
        assert peer["endpoint"].startswith(BASE)
        assert peer["skills"] and peer["skills"][0]["id"]


def test_the_directory_and_the_cards_agree():
    """Built from the cards rather than beside them. A directory assembled from
    its own inventory drifts within a release, and drifts silently - it still
    looks complete."""
    listing = directory_mod.build(BASE, _mounted())
    peers = {c["id"]: c for c in listing["capabilities"] if c["kind"] == "peer"}

    for agent in AGENTS:
        entry = peers[agent.id]
        assert entry["name"] == agent.name
        assert entry["description"] == agent.description
        assert entry["skills"][0]["id"] == agent.skill_id
        assert entry["skills"][0]["name"] == agent.skill_name


def test_an_unpublished_capability_is_not_advertised():
    """A directory naming something nobody can reach is worse than a short
    one."""
    partial = _mounted()[:-1]
    dropped = _mounted()[-1]["id"]

    listing = directory_mod.build(BASE, partial)
    ids = {c["id"] for c in listing["capabilities"]}

    assert dropped not in ids
    assert len(ids) == len(partial)


def test_a_peer_and_a_system_are_distinguishable():
    """Flattening the two would say this estate can do things it can only ask
    somebody else to do."""
    _connect("supplier-x", ["fetch_spec"])
    listing = directory_mod.build(BASE, _mounted())

    kinds = {c["kind"] for c in listing["capabilities"]}
    assert kinds == {"peer", "system"}

    for entry in listing["capabilities"]:
        assert entry["protocol"], "an entry with no protocol cannot be called"
        if entry["kind"] == "system":
            assert entry["state"], "a reachable capability must say if it is"


def test_the_counts_agree_with_the_entries():
    _connect("supplier-x", ["fetch_spec"])
    _connect("supplier-y", ["fetch_spec"], state=connections.DEGRADED)
    listing = directory_mod.build(BASE, _mounted())

    entries = listing["capabilities"]
    assert listing["counts"]["peers"] == sum(
        1 for c in entries if c["kind"] == "peer")
    assert listing["counts"]["systems"] == sum(
        1 for c in entries if c["kind"] == "system")
    # A degraded system is listed and is not counted as reachable.
    assert listing["counts"]["reachable"] == len(AGENTS) + 1


def test_every_peer_entry_names_its_limits():
    """The approval gate and publishing are deliberately not capabilities. A
    directory that merely omits them leaves a reader to conclude they were
    forgotten."""
    listing = directory_mod.build(BASE, _mounted())

    for entry in listing["capabilities"]:
        if entry["kind"] != "peer":
            continue
        limits = " ".join(entry["may_not"]).lower()
        assert "approve" in limits
        assert "publish" in limits


def test_the_directory_is_served_from_a_well_known_address():
    from fastapi.testclient import TestClient

    from sc.main import app

    response = TestClient(app).get("/.well-known/agent-cards.json")

    assert response.status_code == 200
    body = response.json()
    assert body["capabilities"]
    assert body["provider"]["organization"]


# ---------------------------------------------------------------------------
# Discovery is not admission
# ---------------------------------------------------------------------------


def test_connecting_a_system_does_not_widen_the_desk():
    """An allowlist a stranger can widen by connecting is a formality, and the
    allowlist is the reason handing this desk to a model is uninteresting."""
    before = evidence.catalogue()
    _connect("supplier-x", ["fetch_spec", "list_specs"])

    assert evidence.catalogue() == before


def test_an_admitted_tool_joins_the_desk_named_with_its_system():
    """A model choosing between a catalog lookup and a supplier's own answer
    should be able to see which is which."""
    _connect("supplier-x", ["fetch_spec"])
    before = evidence.catalogue().splitlines()

    connections.admit("supplier-x", ["fetch_spec"])
    after = evidence.catalogue().splitlines()

    assert len(after) == len(before) + 1
    added = [line for line in after if line not in before]
    assert len(added) == 1
    assert "fetch_spec" in added[0]
    assert "Supplier X" in added[0], "an admitted tool must name its system"


def test_a_degraded_systems_tool_leaves_the_desk():
    """A catalogue offering something unreachable spends a model's bounded
    rounds discovering that."""
    _connect("supplier-x", ["fetch_spec"])
    connections.admit("supplier-x", ["fetch_spec"])
    with_tool = evidence.catalogue().splitlines()

    connections.mark_degraded("supplier-x", "stopped answering")
    without = evidence.catalogue().splitlines()

    assert len(without) == len(with_tool) - 1
    assert not any("fetch_spec" in line for line in without)
    # And nothing built-in was disturbed on the way.
    assert all(any(t in line for line in without) for t in evidence.TOOLS)


def test_the_desk_survives_an_estate_it_cannot_read(monkeypatch):
    """A desk an unreachable supplier could bring down would make an external
    system load-bearing for a correction run."""
    def _explode():
        raise RuntimeError("the connection store is unavailable")

    monkeypatch.setattr(connections, "all_connections", _explode)

    assert evidence.admitted_tools() == []
    assert len(evidence.catalogue().splitlines()) == len(evidence.TOOLS)


def test_an_admission_is_recorded_in_the_ledger():
    """Admitting a tool changes what a model can reach. That is a governance
    decision with a person behind it - the same class of thing as an approval
    or a publish - and it belongs in the same ledger.

    An earlier note claimed the ledger's schema was shaped around a correction
    case and could not hold one. It was not: `audit` takes any entity type, and
    the claim was wrong rather than the design being awkward.
    """
    _connect("supplier-x", ["fetch_spec", "other_tool"])
    connections.admit("supplier-x", ["fetch_spec", "commit_plan"], actor="sam")

    row = db.one("SELECT actor, action, entity_type, entity_id, detail"
                 " FROM audit WHERE action = 'ADMIT' ORDER BY rowid DESC")

    assert row is not None, "an admission left no trace"
    assert row["actor"] == "sam"
    assert row["entity_type"] == "connection"
    assert row["entity_id"] == "supplier-x"

    detail = db.loads(row["detail"])
    assert detail["admitted"] == ["fetch_spec"]
    # What was asked for and refused is worth recording: an operator who tried
    # to admit a built-in name should be visible having tried.
    assert "commit_plan" in detail["refused"]


def test_an_admission_and_its_record_land_together():
    """Written in the same transaction as the change it describes, so the ledger
    cannot hold an admission the connection never got, or miss one it did."""
    _connect("supplier-x", ["fetch_spec"])

    before = db.one("SELECT COUNT(*) AS n FROM audit WHERE action='ADMIT'")["n"]
    connections.admit("supplier-x", ["fetch_spec"])
    after = db.one("SELECT COUNT(*) AS n FROM audit WHERE action='ADMIT'")["n"]

    assert after == before + 1
    assert connections.get("supplier-x")["admitted_tools"] == ["fetch_spec"]


def test_a_peer_declares_its_own_limits():
    """A limit authored beside the directory is a limit that goes stale: an
    agent whose handler quietly gained the ability to publish would carry on
    advertising that it cannot."""
    from sc.a2a.agents import UNIVERSAL_LIMITS, limits_of

    listing = directory_mod.build(BASE, _mounted())
    peers = {c["id"]: c for c in listing["capabilities"] if c["kind"] == "peer"}

    for agent in AGENTS:
        assert peers[agent.id]["may_not"] == list(limits_of(agent))
        # Each peer says something about itself beyond the universal two,
        # because "may not approve" is true of everything and therefore tells a
        # reader nothing about which capability they are looking at.
        assert agent.may_not, f"{agent.id} declares no limit of its own"
        assert set(limits_of(agent)) > set(UNIVERSAL_LIMITS)


def test_the_universal_limits_hold_for_every_peer():
    """A peer that could approve would make the reviewer optional; one that
    could publish would make the approval gate a suggestion."""
    from sc.a2a.agents import UNIVERSAL_LIMITS, limits_of

    for agent in AGENTS:
        assert set(UNIVERSAL_LIMITS) <= set(limits_of(agent))


def test_a_peer_cannot_declare_away_a_universal_limit():
    """The two that matter are not the peer's to waive."""
    from sc.a2a.agents import PeerAgent, UNIVERSAL_LIMITS, limits_of

    permissive = PeerAgent(
        id="over-eager", name="Over Eager", description="",
        skill_id="s", skill_name="S", skill_description="",
        examples=(), handler=lambda payload: {},
        may_not=("write a fact",))

    assert set(UNIVERSAL_LIMITS) <= set(limits_of(permissive))
    # And a peer repeating one does not produce it twice.
    repeated = PeerAgent(
        id="repetitive", name="Repetitive", description="",
        skill_id="s", skill_name="S", skill_description="",
        examples=(), handler=lambda payload: {},
        may_not=("publish to a channel",))
    limits = limits_of(repeated)
    assert len(limits) == len(set(limits))
