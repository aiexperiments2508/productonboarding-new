"""Systems joining and leaving while the application is running.

The six built-in toolsets were a frozen tuple. They still are, and the nine
assertions in ``test_protocols.py`` that read it still pass unmodified - that is
deliberate, and it is the first thing checked here. What is new is everything
beside them: a connection is a record, made by asking an address what it is, and
it can appear and disappear without a restart.

Three properties carry most of the risk and get most of the tests.

**Unreachable is a state.** An address that does not answer produces a degraded
connection with a reason, not an exception. These tests run with nothing
listening anywhere, which makes that the path they exercise - the same bargain
the rest of the suite makes with the model gateway.

**Discovery is not admission.** Connecting records what a system says it can do.
It does not make any of it callable by a model.

**A discovered tool never shadows a built-in one.** A connected system declaring
`commit_plan` must not become the owner of `commit_plan`.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DB_PATH", "data/test_connections.db")
os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:4999"

from sc import db  # noqa: E402
from sc.mcp import connections  # noqa: E402
from sc.mcp import registry as mcp_registry  # noqa: E402

#: Nothing listens here. Every connection made in this file is therefore a
#: degraded one, which is the case worth testing anyway: the happy path needs a
#: server and the failure path needs to not need one.
DEAD = "http://127.0.0.1:4999/mcp"


@pytest.fixture(autouse=True)
def fresh():
    db.init_db(drop=True)
    yield
    db.close()


def _declare(connection_id: str, tools: list[str], state: str = "connected"):
    """A connection recorded without a handshake.

    Used where the point under test is what the store does with a declaration,
    not whether an address answers. Going through `upsert` rather than writing
    the row keeps the collision detection and the admission rules in the path.
    """
    return connections.upsert(
        connection_id, title=connection_id.title(), owner="external",
        url=f"http://example.invalid/{connection_id}", transport="http",
        state=state, detail="declared by a test", discovered=tools)


# ---------------------------------------------------------------------------
# The built-in six are undisturbed
# ---------------------------------------------------------------------------


def test_the_built_in_toolsets_are_unchanged_by_the_connection_store():
    """The partition and its ownership rules predate this and outrank it."""
    _declare("supplier-x", ["fetch_thing"])

    builtin = [t for t in connections.toolsets() if t["source"] == "built-in"]
    assert [t["id"] for t in builtin] == [t.id for t in mcp_registry.TOOLSETS]
    assert [t["tools"] for t in builtin] == [list(t.tools)
                                             for t in mcp_registry.TOOLSETS]


def test_a_discovered_toolset_is_listed_beside_the_built_in_ones():
    _declare("supplier-x", ["fetch_thing", "list_things"])

    listing = connections.toolsets()
    discovered = [t for t in listing if t["source"] == "connected"]

    assert len(listing) == len(mcp_registry.TOOLSETS) + 1
    assert len(discovered) == 1
    assert discovered[0]["id"] == "supplier-x"
    assert discovered[0]["owner"]
    assert sorted(discovered[0]["tools"]) == ["fetch_thing", "list_things"]
    # Labelled with where it came from, because "can I hand this out" is a
    # different question for a server that ships here.
    assert {t["source"] for t in listing} == {"built-in", "connected"}


def test_a_discovered_tool_does_not_shadow_a_built_in_one():
    """The failure the toolset partition exists to prevent: a system connected
    five minutes ago quietly becoming the owner of the tool that publishes."""
    record = _declare("impostor", ["commit_plan", "fetch_thing"])

    assert "commit_plan" in record["collisions"]
    assert connections.owner_of("commit_plan") == "publishing-execution"
    assert connections.owner_of("fetch_thing") == "impostor"

    # And it cannot be admitted under that name either.
    admitted = connections.admit("impostor", ["commit_plan", "fetch_thing"])
    assert admitted["admitted_tools"] == ["fetch_thing"]


# ---------------------------------------------------------------------------
# Discovery is not admission
# ---------------------------------------------------------------------------


def test_connecting_admits_nothing():
    """A system you have just met is a system you have just met. The evidence
    desk is an allowlist, and connecting must not widen it by itself."""
    record = _declare("supplier-x", ["fetch_thing", "list_things"])

    assert record["discovered_tools"] == ["fetch_thing", "list_things"]
    assert record["admitted_tools"] == []


def test_admission_is_narrowed_to_what_the_system_declared():
    _declare("supplier-x", ["fetch_thing"])
    admitted = connections.admit("supplier-x", ["fetch_thing", "invented"])
    assert admitted["admitted_tools"] == ["fetch_thing"]


def test_admission_survives_a_reconnect():
    """A system coming back is not a reason to re-approve it, and revoking
    silently on a reconnect would be its own surprise."""
    _declare("supplier-x", ["fetch_thing"])
    connections.admit("supplier-x", ["fetch_thing"])

    again = _declare("supplier-x", ["fetch_thing", "list_things"])
    assert again["admitted_tools"] == ["fetch_thing"]


# ---------------------------------------------------------------------------
# Reaching an address
# ---------------------------------------------------------------------------


def test_an_unreachable_address_is_recorded_not_raised():
    record = connections.connect_url(DEAD, title="Nothing There")

    assert record["state"] == connections.DEGRADED
    assert record["detail"], "a degraded connection must say why"
    assert record["discovered_tools"] == []
    assert connections.get(record["id"]) is not None


def test_a_failed_handshake_says_something_a_person_can_act_on():
    """The MCP clients run their transport in a task group, so the raw failure
    is an ExceptionGroup whose message is "unhandled errors in a TaskGroup" -
    true, and no help to somebody who has just pasted an address."""
    record = connections.connect_url("not-a-url", title="Typo")
    assert "TaskGroup" not in record["detail"]
    assert "http" in record["detail"].lower()


def test_disconnecting_then_reconnecting_leaves_one_connection():
    first = connections.connect_url(DEAD, title="Nothing There")
    assert connections.disconnect(first["id"]) is True
    assert connections.get(first["id"]) is None

    again = connections.connect_url(DEAD, title="Nothing There")
    assert again["id"] == first["id"]
    assert len(connections.all_connections()) == 1

    # Disconnecting something that is already gone is not an error.
    assert connections.disconnect(first["id"]) is True
    assert connections.disconnect(first["id"]) is False


def test_connecting_the_same_address_twice_updates_one_record():
    connections.connect_url(DEAD, title="First")
    connections.connect_url(DEAD, title="Second")

    held = connections.all_connections()
    assert len(held) == 1
    assert held[0]["title"] == "Second"


def test_an_unreachable_system_degrades_rather_than_failing():
    """No external system is load-bearing. One that stops answering is marked,
    and the facts it already delivered stay exactly where they are."""
    _declare("supplier-x", ["fetch_thing"])
    marked = connections.mark_degraded("supplier-x", "stopped answering")

    assert marked["state"] == connections.DEGRADED
    assert "stopped answering" in marked["detail"]
    assert marked["discovered_tools"] == ["fetch_thing"], \
        "degrading must not erase what the system said it could do"
    assert connections.mark_degraded("never-connected", "x") is None
