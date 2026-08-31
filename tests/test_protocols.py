"""A2A peers and MCP toolsets.

Both are transports over work that already existed, and both are tested for the
same property above all others: **the answer does not depend on how it was
reached**. An A2A demonstration that changed the numbers would not be showing
interoperability, it would be showing two implementations - and the trace hash
is what makes that checkable rather than a matter of opinion.

Nothing here spawns a server or opens a socket. The wire is exercised live
against the running app; what these cover is the contract - the partition, the
routing, the fallback, and the identity of the results.
"""

from __future__ import annotations

import os

os.environ.setdefault("DB_PATH", "data/test_protocols.db")

import pytest  # noqa: E402

from sc import db  # noqa: E402
from sc.a2a import agents as a2a_agents  # noqa: E402
from sc.a2a import client as a2a_client  # noqa: E402
from sc.mcp import client as mcp_client  # noqa: E402
from sc.mcp import registry as mcp_registry  # noqa: E402
from sc.replay import ingest, tape  # noqa: E402


@pytest.fixture
def seeded():
    """A database for the handful of tests that actually simulate.

    Requested rather than autouse, and function-scoped rather than module-
    scoped, for a reason worth recording: conftest pins DB_PATH per test with
    a function-scoped fixture, and a module-scoped fixture runs *before* that.
    Seeding at module scope therefore builds a schema in whichever database
    the previous module left selected, and every test here then queries an
    empty file. Most of this file is contract checks that touch no data at all,
    so paying the tape load only where it is needed costs nothing either.
    """
    db.init_db(drop=True)
    tape.load_tape(reset=True)
    released = tape.jump_to(tape.inject_seq() + 12)
    ingest.ingest(released)
    return True


# ---------------------------------------------------------------------------
# The MCP partition
# ---------------------------------------------------------------------------


def test_every_tool_belongs_to_exactly_one_toolset():
    """Overlap would make 'which system owns this' unanswerable."""
    seen: dict[str, str] = {}
    for toolset in mcp_registry.TOOLSETS:
        for tool in toolset.tools:
            assert tool not in seen, (
                f"{tool} is in both {seen[tool]} and {toolset.id}")
            seen[tool] = toolset.id


def test_mutating_tools_are_declared_and_belong_to_their_toolset():
    for toolset in mcp_registry.TOOLSETS:
        for tool in toolset.mutating:
            assert tool in toolset.tools, (
                f"{toolset.id} declares {tool} mutating but does not expose it")


def test_the_dangerous_surface_is_one_named_server():
    """The reason the partition is worth having.

    An operator can hand out the read-only toolsets and withhold the one that
    can publish. That is only true if the writes are concentrated.
    """
    writers = [t.id for t in mcp_registry.TOOLSETS if not t.read_only]
    assert "publishing-execution" in writers
    for read_only in ("product-catalog", "channel-registry", "content-store",
                      "knowledge-base"):
        assert read_only not in writers

    # The event plane writes too, and the exception is a narrow one: advancing
    # the tape moves the clock. Exactly one server can change what a channel
    # sees, and it is the one with "publishing" in its name.
    assert [t.id for t in mcp_registry.TOOLSETS
            if set(t.mutating) - {"advance_events"}] == ["publishing-execution"]


def test_commit_is_not_reachable_from_a_read_only_toolset():
    for toolset in mcp_registry.TOOLSETS:
        if toolset.read_only:
            assert "commit_plan" not in toolset.tools
            assert "rollback" not in toolset.tools


def test_owner_lookup_covers_every_declared_tool():
    for toolset in mcp_registry.TOOLSETS:
        for tool in toolset.tools:
            assert mcp_registry.owner_of(tool) == toolset.id
    assert mcp_registry.owner_of("not-a-tool") == "unknown"


def test_only_read_only_tools_are_routed_over_the_wire():
    """Committing a plan over a pipe that might have died is a worse idea than
    committing it in-process, and the approval gate is not something to put a
    transport underneath."""
    mutating = {t for toolset in mcp_registry.TOOLSETS
                for t in toolset.mutating}
    assert not (set(mcp_client.ROUTES) & mutating)


def test_every_routed_tool_names_a_real_toolset():
    for tool, toolset_id in mcp_client.ROUTES.items():
        assert toolset_id in mcp_registry.BY_ID, f"{tool} -> unknown {toolset_id}"
        assert tool in mcp_registry.BY_ID[toolset_id].tools


def test_transport_is_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv("USE_MCP", raising=False)
    assert mcp_client.enabled() is False
    monkeypatch.setenv("USE_MCP", "1")
    assert mcp_client.enabled() is True
    monkeypatch.setenv("USE_MCP", "0")
    assert mcp_client.enabled() is False


def test_an_unrouted_tool_still_runs(monkeypatch):
    """A tool with no MCP route is not a tool that stops working."""
    monkeypatch.setenv("USE_MCP", "1")
    called = {}

    def direct(**kwargs):
        called.update(kwargs)
        return {"ok": True}

    assert mcp_client.call("not_routed", {"x": 1}, direct) == {"ok": True}
    assert called == {"x": 1}


# ---------------------------------------------------------------------------
# The A2A roster
# ---------------------------------------------------------------------------


def test_peers_are_split_at_real_seams():
    ids = {a.id for a in a2a_agents.AGENTS}
    assert ids == {"lineage-analyst", "resolution-planner", "validator",
                   "copywriter"}


def test_the_approval_gate_is_not_a_peer():
    """A human decision is not a capability to delegate, and a peer that could
    publish is a peer that could publish."""
    ids = {a.id for a in a2a_agents.AGENTS}
    for forbidden in ("approver", "publisher", "publish", "approval"):
        assert forbidden not in ids


def test_every_peer_declares_a_skill_a_caller_could_discover():
    for agent in a2a_agents.AGENTS:
        assert agent.skill_id and agent.skill_name
        assert len(agent.skill_description) > 30, agent.id
        assert agent.examples, f"{agent.id} publishes no example prompts"


def test_delegation_is_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv("USE_A2A", raising=False)
    assert a2a_client.enabled() is False
    monkeypatch.setenv("USE_A2A", "true")
    assert a2a_client.enabled() is True


def test_base_url_follows_the_port_the_server_is_on(monkeypatch):
    """A card advertising the wrong port is a card nothing can call."""
    monkeypatch.delenv("A2A_BASE_URL", raising=False)
    monkeypatch.setenv("API_PORT", "9137")
    assert a2a_client.base_url() == "http://127.0.0.1:9137"
    monkeypatch.setenv("A2A_BASE_URL", "https://peer.example/")
    assert a2a_client.base_url() == "https://peer.example"


def test_a_degraded_peer_falls_back_rather_than_failing(seeded, monkeypatch):
    """A peer that stops answering costs a log line, not a correction run."""
    monkeypatch.setenv("USE_A2A", "1")
    monkeypatch.setenv("A2A_BASE_URL", "http://127.0.0.1:1")  # nothing listens

    a2a_client.revive()
    result = a2a_client.call("validator",
                             {"delta": {"id": "D-FALLBACK", "actions": []}})

    # The in-process handler answered.
    assert "trace_hash" in result
    # And the failure was recorded rather than swallowed.
    assert any(c["agent"] == "validator" and not c["ok"]
               for c in a2a_client.calls())
    a2a_client.revive()


def test_reviving_clears_the_degraded_set(seeded, monkeypatch):
    monkeypatch.setenv("USE_A2A", "1")
    monkeypatch.setenv("A2A_BASE_URL", "http://127.0.0.1:1")
    a2a_client.revive()
    a2a_client.call("validator", {"delta": {"id": "D-X", "actions": []}})
    assert a2a_client.status()["degraded"]
    a2a_client.revive()
    assert not a2a_client.status()["degraded"]


# ---------------------------------------------------------------------------
# The property both transports exist to preserve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("delta", [
    {"id": "D-EMPTY", "actions": []},
])
def test_the_validator_peer_is_the_validator(seeded, delta):
    """Delegating must not change the answer.

    The peer handler and the in-process tool have to agree to the digit,
    because the trace hash is the project's determinism claim and routing it
    through an agent must not weaken it.
    """
    from sc.tools import planning

    via_peer = a2a_agents._validate({"delta": delta})
    direct = planning.run_scenario(delta)

    assert via_peer["trace_hash"] == direct["trace_hash"]
    assert via_peer["kpis"] == direct["kpis"]
    assert via_peer["feasible"] == direct["feasible"]


def test_the_copywriter_works_without_a_gateway(seeded):
    """The peer's own implementation is the deterministic renderer.

    That is what makes the seam swappable: another team's brand-voice model can
    replace this handler, and until they do the factory still produces publish-
    ready copy with nothing but the catalog. The graph's regenerate node is what
    adds a model call on top.
    """
    result = a2a_agents._copy({"values": {"VAR-01B:specs.power_w": 65}})
    by_id = {row["asset_id"]: row for row in result["copy"]}

    # A wattage quoted in a marketplace title is a substitution, not a judgement.
    assert "65W" in by_id["AST-020"]["proposed_text"]
    assert "45W" not in by_id["AST-020"]["proposed_text"]
    # The feed row is rebuilt under the channel's own field name.
    assert '"wattage": 65' in by_id["AST-023"]["proposed_text"]
    # A claim the corrected value no longer supports is flagged before it is
    # written, not after the validator rejects it.
    assert "low-energy" in by_id["AST-018"]["claims_at_risk"]


def test_the_copywriter_refuses_an_ambiguous_literal(seeded):
    """The comparison table quotes both variants' wattage, and at baseline both
    read 45 W. Substituting would rewrite the base model's row - the exact error
    the whole base-versus-variant story is about, reached by regex instead of by
    a bad decision. The record cannot say which occurrence is which, so it does
    not guess."""
    result = a2a_agents._copy({"values": {"VAR-01B:specs.power_w": 65}})
    table = next(r for r in result["copy"] if r["asset_id"] == "AST-004")

    assert table["changed"] is False
    assert table["unresolved"] == ["VAR-01B:specs.power_w"]
    # The values it could not place travel with it, so the model that picks the
    # work up is handed the table rather than asked to recall it.
    assert table["targets"] == {"VAR-01B:specs.power_w": 65}


# ---------------------------------------------------------------------------
# The vendor intake
#
# The estate is read-only into the catalog, and this surface is the one place
# that accepts anything. What keeps that safe is not a permission check - it is
# that the module has no way to write a value: it appends events, and the
# platform's own ingestion judges them.
#
# That is an argument about imports, so it is checked by reading them. A
# comment saying "this cannot reach the fact store" stops being true the first
# time somebody adds a convenient import, and nothing else in the suite would
# notice.
# ---------------------------------------------------------------------------

#: Modules that would give the intake a way to write a value directly, and the
#: two functions that publish. `store` and `overlay` are the fact plane;
#: `remediation` dispatches to live channels.
FORBIDDEN_TO_INTAKE = {
    "sc.state.store", "sc.state.overlay", "sc.estate.remediation",
}
FORBIDDEN_NAMES = {"commit_plan", "rollback", "commit_redaction", "record"}

INTAKE_MODULES = ("sc/estate/intake.py", "sc/estate/intake_server.py")


@pytest.mark.parametrize("path", INTAKE_MODULES)
def test_the_intake_surface_cannot_reach_the_fact_store(path):
    """A supplier appends an event. It does not write a value.

    Enforced structurally rather than by a check somebody could route around:
    there is no function in this surface that takes an entity, an attribute and
    a value, and there is no import that would let one be written.
    """
    import ast
    from pathlib import Path

    source = Path(path)
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=path)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in FORBIDDEN_TO_INTAKE, (
                    f"{path} imports {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            assert node.module not in FORBIDDEN_TO_INTAKE, (
                f"{path} imports from {node.module}")
            for alias in node.names:
                full = f"{node.module}.{alias.name}"
                assert full not in FORBIDDEN_TO_INTAKE, f"{path} imports {full}"
                if node.module.startswith("sc."):
                    assert alias.name not in FORBIDDEN_NAMES, (
                        f"{path} imports {alias.name} from {node.module}")


def test_the_only_write_the_intake_makes_is_an_appended_event():
    """One write path, and it takes an event rather than a triple.

    ``tape.append_live`` is the whole of it. Anything else that reached the
    store would be a second way in, and the first thing it would skip is the
    precedence policy.
    """
    import ast
    from pathlib import Path

    tree = ast.parse(Path("sc/estate/intake.py").read_text(encoding="utf-8"))
    called = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "append_live" in called
    assert "record" not in called, "the intake wrote a fact directly"


def test_no_intake_tool_shadows_a_built_in_toolset_name():
    """The rule the connection registry already enforces for a system somebody
    plugs in applies just as much to one that ships here."""
    from sc.estate import intake_server

    built_in = {tool for toolset in mcp_registry.BY_ID.values()
                for tool in toolset.tools}
    for system in intake_server.vendor_facing():
        assert not (set(intake_server.tools_for(system)) & built_in)


def test_intake_endpoints_are_not_registered_as_outbound_connections():
    """A connection record means "a system we reach out to". An intake endpoint
    is an address others reach us at, and folding the two together would make
    "what can this platform reach" unanswerable."""
    from sc.estate import intake_server, server as estate_server

    intake_ids = {s.id for s in intake_server.vendor_facing()}
    for system_id in intake_ids:
        # The read-only estate server owns that identifier for connections.
        assert estate_server.endpoint(system_id, "") != \
            intake_server.endpoint(system_id, "")
