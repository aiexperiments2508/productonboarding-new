"""What is connected right now.

The six built-in toolsets are declared in ``registry.py`` and stay exactly as
they are: their ownership invariants are true, nine tests assert them, and a
system that ships in the box is not less real for having shipped in the box.
What they were not is *extensible*. Nothing could join or leave while the
application was running, so "plug and play" was a claim the code could not make
good on.

This module is the other half. A connection is a runtime record - persisted, so
it survives a restart and so "what was the estate when this ran" is answerable
afterwards - carrying an address, a transport, a state, and what the system
said it could do when it was asked.

Three rules are worth stating up front, because each one is a decision rather
than an implementation detail.

**Discovery is not admission.** ``discovered_tools`` is what the system says it
has. ``admitted_tools`` is the subset an operator has allowed a model to call.
They are separate columns because connecting a system must not silently widen
the evidence desk's allowlist. A system you have just met is a system you have
just met.

**A discovered tool never shadows a built-in one.** If a connected system
declares ``commit_plan``, the built-in keeps that name, the collision is
recorded on the connection, and the discovered tool remains reachable only
through its own system. A connected peer quietly redefining the tool that
publishes to a channel is the exact failure the toolset partition exists to
prevent.

**Unreachable is a state, not an exception.** Connecting to an address nothing
answers records a degraded connection with the reason and returns. A demo that
cannot boot because a mock supplier was slow is a worse outcome than a demo
missing one supplier.
"""

from __future__ import annotations

from datetime import datetime

from sc import db
from sc.contracts import Provenance, ProvenanceKind
from sc.mcp.registry import BY_ID as BUILTIN_BY_ID
from sc.mcp.registry import TOOLSETS, describe as describe_builtins
from sc.tools import planning

CONNECTED = "connected"
DEGRADED = "degraded"

#: How long a handshake may take before the system is called degraded. Short on
#: purpose: this runs while somebody is watching, and an address that needs more
#: than a couple of seconds to say hello is one to report rather than wait for.
HANDSHAKE_TIMEOUT = 4.0

#: Every tool name the built-in toolsets own. A discovered tool matching one of
#: these is a collision, never a replacement.
BUILTIN_TOOLS: frozenset[str] = frozenset(
    tool for toolset in TOOLSETS for tool in toolset.tools)


def _now() -> str:
    return datetime.now().isoformat()


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


def _row_to_dict(row) -> dict:
    record = dict(row)
    for key in ("discovered_tools", "admitted_tools", "collisions"):
        record[key] = db.loads(record[key])
    record["source"] = "connected"
    record["read_only"] = not record["admitted_tools"]
    return record


def all_connections() -> list[dict]:
    """Every connection on record, connected and degraded alike."""
    return [_row_to_dict(r) for r in
            db.query("SELECT * FROM connections ORDER BY connected_at, id")]


def get(connection_id: str) -> dict | None:
    row = db.one("SELECT * FROM connections WHERE id = ?", (connection_id,))
    return _row_to_dict(row) if row else None


def upsert(connection_id: str, *, title: str, owner: str, url: str,
           transport: str, state: str, detail: str = "",
           discovered: list[str] | None = None) -> dict:
    """Record a connection, or update the one already under this id.

    Reconnecting an id that is already present updates it rather than adding a
    second row - a system that dropped and came back is the same system, and an
    estate that grew a duplicate every time the network hiccuped would be
    unreadable within an hour.

    ``admitted_tools`` is deliberately not a parameter. Admission is a separate
    decision taken by a person, and a function that could grant it as a side
    effect of connecting is a function that will.
    """
    discovered = sorted(set(discovered or []))
    collisions = sorted(set(discovered) & BUILTIN_TOOLS)
    existing = get(connection_id)
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO connections (id, title, owner, url, transport, state,"
            " detail, discovered_tools, admitted_tools, collisions,"
            " connected_at, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            "  title = excluded.title, owner = excluded.owner,"
            "  url = excluded.url, transport = excluded.transport,"
            "  state = excluded.state, detail = excluded.detail,"
            "  discovered_tools = excluded.discovered_tools,"
            "  collisions = excluded.collisions,"
            "  last_seen = excluded.last_seen",
            (connection_id, title, owner, url, transport, state, detail,
             db.dumps(discovered),
             # Admissions already granted survive a reconnect; a system coming
             # back is not a reason to re-approve it, and revoking silently
             # would be its own surprise.
             db.dumps(existing["admitted_tools"] if existing else []),
             db.dumps(collisions), _now() if not existing else
             existing["connected_at"], _now()))
    return get(connection_id)  # type: ignore[return-value]


def connect_url(url: str, *, connection_id: str | None = None,
                title: str = "", owner: str = "",
                transport: str = "http") -> dict:
    """Connect to an address, by asking it what it is.

    The handshake is real: ``initialize`` then ``tools/list``, over the
    transport named. Nothing is inferred from the URL, because an address that
    looks like an MCP server and is not is precisely the case a connection
    record exists to distinguish.

    An address that does not answer is recorded as degraded and returned. That
    is not swallowing an error - the reason is on the record, the state says
    degraded, and the listing shows it - it is refusing to let one unreachable
    supplier end the request.
    """
    from sc.mcp import client

    identifier = connection_id or _id_from_url(url)
    tools, error = client.handshake(url, transport, HANDSHAKE_TIMEOUT)
    return upsert(
        identifier,
        title=title or identifier,
        owner=owner or "external",
        url=url,
        transport=transport,
        state=DEGRADED if error else CONNECTED,
        detail=error or f"{len(tools)} tool(s) declared",
        discovered=tools,
    )


def _id_from_url(url: str) -> str:
    """A stable identifier for an address nobody named.

    Derived from the address rather than minted randomly, so connecting the
    same endpoint twice updates one record instead of accumulating two.
    """
    trimmed = url.rstrip("/")
    tail = trimmed.rsplit("/", 1)[-1] or trimmed
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in tail)
    return cleaned.strip("-").lower() or "external"


def disconnect(connection_id: str) -> bool:
    """Remove a connection. The facts it delivered stay.

    A bitemporal store does not retract history because a socket closed: what
    that system asserted was true when it asserted it, and the audit trail has
    to keep saying so.
    """
    with db.transaction() as conn:
        cursor = conn.execute("DELETE FROM connections WHERE id = ?",
                              (connection_id,))
    return cursor.rowcount > 0


def mark_degraded(connection_id: str, detail: str) -> dict | None:
    """A system that stopped answering. Marked, never deleted."""
    if get(connection_id) is None:
        return None
    with db.transaction() as conn:
        conn.execute(
            "UPDATE connections SET state = ?, detail = ? WHERE id = ?",
            (DEGRADED, detail[:400], connection_id))
    return get(connection_id)


def admit(connection_id: str, tools: list[str],
          actor: str = "operator") -> dict | None:
    """Allow a model to call these tools on this system.

    Only tools the system actually declared, and never one whose name a
    built-in already owns. Both refusals are silent narrowing rather than
    errors: an operator ticking a box should not have to know the built-in
    tool list to avoid tripping over it, and the collision is already recorded
    on the connection for them to read.
    """
    record = get(connection_id)
    if record is None:
        return None
    allowed = sorted(
        set(tools) & set(record["discovered_tools"]) - BUILTIN_TOOLS)
    with db.transaction() as conn:
        conn.execute("UPDATE connections SET admitted_tools = ? WHERE id = ?",
                     (db.dumps(allowed), connection_id))
        # Admitting a tool changes what a model can reach, which is a governance
        # decision with a person behind it - the same class of thing as an
        # approval or a publish, and it belongs in the same ledger.
        #
        # Recorded in the same transaction as the change it describes, so the
        # ledger cannot hold an admission the connection never got, or miss one
        # it did.
        planning.audit(
            actor, "ADMIT", "connection", connection_id,
            {"admitted": allowed,
             "was": record["admitted_tools"],
             "refused": sorted(set(tools) - set(allowed))},
            Provenance(kind=ProvenanceKind.DECIDED, agent="operator",
                       note=f"tools admitted on {connection_id}"),
            conn=conn)
    return get(connection_id)


def owner_of(tool: str) -> str:
    """Which surface owns a tool name, built-in first.

    Built-in wins, always. This is the function that makes "a discovered tool
    does not shadow a built-in one" true rather than intended.
    """
    for toolset in TOOLSETS:
        if tool in toolset.tools:
            return toolset.id
    for record in all_connections():
        if tool in record["discovered_tools"]:
            return record["id"]
    return "unknown"


def toolsets() -> list[dict]:
    """The built-in six plus whatever is connected, as one listing.

    Labelled by where each came from, because "which of these can I hand out"
    is a different question for a server that ships here and one somebody
    connected five minutes ago.
    """
    builtin = [{**t, "source": "built-in", "state": CONNECTED}
               for t in describe_builtins()]
    connected = [{
        "id": c["id"],
        "module": "",
        "title": c["title"],
        "owner": c["owner"],
        "why": c["detail"] or "connected at runtime",
        "tools": c["discovered_tools"],
        "mutating": [],
        "read_only": True,
        "command": c["url"],
        "source": "connected",
        "state": c["state"],
        "admitted": c["admitted_tools"],
        "collisions": c["collisions"],
    } for c in all_connections() if c["id"] not in BUILTIN_BY_ID]
    return builtin + connected
