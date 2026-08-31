"""The estate as part of the map.

The catalog map is derived on read - that requirement predates this and is a
good one, because a stored map is a second account of a structure the catalog
already settles. The systems tier is derived the same way, from two places and
no third: the connection records say who is reachable, and the arrivals say
what each one actually carried.

The edge a system draws is deliberately to the **supplier**, not to the product.
A system is a pipe, and what it tells you is *whose* data came through it. Two
systems feeding the same supplier is the interesting case - it is where the
contradiction defect lives - and an edge to the product would draw that as two
lines to the same box with the disagreement invisible between them.

A connected system that has delivered nothing still appears. An estate that
only shows what has already spoken cannot show a silent supplier, and a silent
supplier three days before a launch is exactly what somebody needs to see.
"""

from __future__ import annotations

from sc import db
from sc.estate.manifest import BY_ID


_reach_memo: dict[str, object] = {"arrivals": None, "value": None}


def _supplier_reach() -> dict[str, set[str]]:
    """Which suppliers each system has carried data for.

    One join rather than a walk: arrivals name the event, the event's payload
    names the entity, and the catalog maps the entity to its supplier. Entities
    are read out of the payload rather than inferred from the event type,
    because an event type says what shape a thing is and not who it is about.

    The reading of the payload lives in ``sc.estate.reach`` and not here. It
    used to look at ``entity_id`` alone, which is one of five ways the tape
    names a product: a channel acknowledgement says ``variant_id``, a document
    and an email say ``entities``. Six systems had delivered nothing but those
    spellings, so the map drew them as boxes with no lines - not because they
    were silent, but because nobody was listening in their dialect.

    Memoised on the arrival count. Reach only grows, so a count that has not
    moved cannot have changed the answer - and this is read on every map draw,
    which at several thousand events means parsing every payload again to
    answer a question whose answer did not change.
    """
    from sc.estate import reach as reach_mod
    from sc.state import baseline as baseline_mod

    # Keyed on the count *and* the newest row. The count alone is enough while
    # arrivals only ever accumulate, and is wrong the moment a test drops the
    # database and refills it to the same size.
    row = db.one("SELECT COUNT(*) AS n, MAX(id) AS newest FROM arrivals")
    stamp = (int(row["n"]) if row else 0, (row["newest"] if row else "") or "")
    if _reach_memo["arrivals"] == stamp and _reach_memo["value"] is not None:
        return _reach_memo["value"]  # type: ignore[return-value]

    base = baseline_mod.get()
    reach: dict[str, set[str]] = {}
    rows = db.query(
        "SELECT a.system_id AS system_id, e.payload AS payload"
        " FROM arrivals a JOIN events e ON e.id = a.event_id")
    for row in rows:
        try:
            payload = db.loads(row["payload"])
        except Exception:  # noqa: BLE001 - a bad payload is not a bad map
            continue
        suppliers = reach_mod.suppliers_of(base, payload)
        if suppliers:
            reach.setdefault(row["system_id"], set()).update(suppliers)

    _reach_memo["arrivals"] = stamp
    _reach_memo["value"] = reach
    return reach


def nodes_and_edges() -> tuple[list[dict], list[dict]]:
    """The systems tier and its edges, derived from connections and arrivals.

    Positions are not returned. A tier whose membership changes while the
    application is running cannot be laid out from coordinates written at
    generation time, so the client computes position from the tier and the live
    membership of that tier - which also removes a way for the picture to
    disagree with the catalog.
    """
    from sc.mcp import connections

    reach = _supplier_reach()
    nodes: list[dict] = []
    edges: list[dict] = []

    for record in connections.all_connections():
        system = BY_ID.get(record["id"])
        nodes.append({
            "id": record["id"],
            "kind": "SYSTEM",
            "name": record["title"],
            "group": record["owner"],
            # Degraded is a state of the connection, not of the data it sent.
            # The map greys the node and keeps every edge it drew.
            "state": record["state"],
            "transport": record["transport"],
            "tools": len(record["discovered_tools"]),
            "conforms": bool(system.well_behaved) if system else None,
            "regulated": False,
            "single_source": False,
        })
        for supplier in sorted(reach.get(record["id"], ())):
            edges.append({
                "from": record["id"],
                "to": supplier,
                "relation": "feeds",
                "status": record["state"],
            })

    return nodes, edges
