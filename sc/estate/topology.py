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


def _supplier_reach() -> dict[str, set[str]]:
    """Which suppliers each system has carried data for.

    One join rather than a walk: arrivals name the event, the event's payload
    names the entity, and the catalog maps the entity to its supplier. Entities
    are read out of the payload rather than inferred from the event type,
    because an event type says what shape a thing is and not who it is about.
    """
    from sc.state import baseline as baseline_mod

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
        entity = payload.get("entity_id") or payload.get("product_id")
        if not isinstance(entity, str):
            continue
        product = base.product_of_variant.get(entity, entity)
        supplier = getattr(base.products.get(product), "supplier", None)
        if supplier:
            reach.setdefault(row["system_id"], set()).add(supplier)
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
