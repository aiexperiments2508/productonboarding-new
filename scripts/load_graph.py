"""Load the knowledge graph into Neo4j, over MCP.

    python scripts/load_graph.py                  # harvest over MCP, then MERGE
    python scripts/load_graph.py --dry-run        # count what would be written
    python scripts/load_graph.py --offline        # read SQLite instead of MCP
    python scripts/load_graph.py --prune          # remove what this run did not touch
    python scripts/load_graph.py --since 2026-08  # only rows newer than this

Needs the platform running, because the point of this script is that it does
*not* read the database. It dials the four back-office systems on their own MCP
endpoints and MERGEs what they answer with - the same claim
``estate_server.connect_all`` makes at startup, and for the same stated reason:
a system that is only connected because a dictionary says so has not
demonstrated anything.

**Three rules, and the middle one is the one that matters.**

1. *No partial graph.* All four systems are harvested into memory before Neo4j
   is opened. A graph missing one domain looks complete and answers two of the
   six saved queries wrongly.

2. *No silent fallback.* If the platform is not answering, this writes nothing
   and exits 1 with the real reason. ``apps/_mcp.py`` makes the argument for
   the applications - if the platform is unreachable they have nothing to fall
   back *to*, and pretending otherwise hides the one failure they exist to make
   visible - and it holds here. There **is** an offline path, and it is
   ``--offline``: explicit, printed in the banner, and it stamps every node
   ``via: sqlite`` so a graph stays answerable about how it was built.

3. *MERGE is idempotent, not convergent.* Running this twice writes the same
   graph. It does not remove a node that has left the source - nothing does,
   until ``--prune``.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from datetime import datetime
from pathlib import Path

# Run as a script from anywhere - `python scripts/load_graph.py` puts scripts/
# on sys.path, not the project root, so `sc` would not import.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sc import bootstrap  # noqa: E402
from sc.contracts import GraphNodeLabel, GraphRelType  # noqa: E402
from sc.estate import manifest  # noqa: E402
from sc.estate import server as estate_server  # noqa: E402
from sc.kg import cypher, driver, model, project  # noqa: E402

#: The event types the graph is built from. The *systems* are looked up from
#: the manifest rather than written here, so this script names no system - the
#: same rule `sc/` lives under, kept voluntarily because a script that hard-codes
#: an id is a script that breaks silently when the manifest moves it.
REFERENCE_TYPES = ("MARKET_RULE", "REGULATION", "CERTIFICATE", "AUDIENCE",
                   "CAMPAIGN", "PROMOTION", "PRICE_LIST", "STOCK_SNAPSHOT",
                   "SALES_PERIOD")

#: How many rows go into one MERGE. Batches are the unit of speed, not of
#: failure - see `_write_batch`.
BATCH = 500


def reference_systems() -> list[str]:
    """Which systems carry the reference domains, according to the manifest."""
    found: list[str] = []
    for event_type in REFERENCE_TYPES:
        for system in manifest.emitters_of(event_type):
            if system.id not in found:
                found.append(system.id)
    return found


# ---------------------------------------------------------------------------
# Harvesting over MCP


def _unwrap(result):
    """FastMCP returns either structured content or text blocks.

    The third copy of this in the repository, and the duplication is deliberate
    in one of them: `apps/_mcp.py` may not import `sc`, so its copy is the
    boundary. This one could import `sc.mcp.client`'s, and does not only
    because that module carries a background event loop this script has no use
    for.
    """
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured.get("result", structured)
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            import json

            with contextlib.suppress(ValueError):
                return json.loads(text)
    return None


def _reason(exc: BaseException) -> str:
    """Dig the real cause out of a TaskGroup exception.

    The MCP clients run their transport in a task group, so the outer message
    is always "unhandled errors in a TaskGroup" - useless to somebody who just
    wants to know the platform is not running. Same walk
    `sc/mcp/client.py:_reason` does.
    """
    seen = exc
    for _ in range(6):
        inner = getattr(seen, "exceptions", None)
        if not inner:
            break
        seen = inner[0]
    return f"{type(seen).__name__}: {str(seen)[:200]}"


async def _harvest_one(base_url: str, system_id: str,
                       limit: int) -> list[tuple[str, str, dict]]:
    """One system, one session, opened and closed by the task that owns it.

    The streamable-HTTP transport runs its reader inside the task that opened
    the session - the discipline `apps/_mcp.Endpoint` documents at length. A
    script has one task and no request lifetime to get out of step with, so the
    whole conversation happens here and the session never outlives it.
    """
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    url = estate_server.endpoint(system_id, base_url)
    async with streamable_http_client(url) as streams:
        async with ClientSession(streams[0], streams[1]) as session:
            await session.initialize()
            listing = await session.list_tools()
            offered = {tool.name for tool in listing.tools}
            missing = set(estate_server.TOOLS) - offered
            if missing:
                raise RuntimeError(
                    f"{system_id} at {url} does not offer {sorted(missing)}")

            rows = _unwrap(await session.call_tool(
                "recent_deliveries", {"limit": limit})) or []
            harvested = []
            for row in rows:
                payload = _unwrap(await session.call_tool(
                    "fetch_payload", {"event_id": row["event_id"]}))
                if not isinstance(payload, dict):
                    continue
                event_type = payload.get("type") or row.get("type")
                body = payload.get("payload", payload)
                if event_type in REFERENCE_TYPES:
                    harvested.append((system_id, event_type, body))
            return harvested


async def _harvest(base_url: str, limit: int) -> list[tuple[str, str, dict]]:
    """Every reference system, in manifest order. All of it, or none of it."""
    everything: list[tuple[str, str, dict]] = []
    for system_id in reference_systems():
        got = await _harvest_one(base_url, system_id, limit)
        print(f"    {system_id:<20} {len(got):>4} events")
        everything.extend(got)
    return everything


# ---------------------------------------------------------------------------
# Writing


def _write_batch(query, rows: list[dict]) -> int:
    """MERGE one batch, and fall back to row-by-row when it fails.

    Batches are the unit of speed and not of failure. "The load failed" is not
    something anybody can act on; "row 412, StockLevel VAR-77A:WH-LEEDS:...,
    constraint violation" is. So a failed batch is retried one row at a time,
    and the rows that survive still land.
    """
    from sc.kg.cypher import GraphQuery

    try:
        driver.run(GraphQuery(query.name, query.cypher, {"rows": rows}),
                   write=True)
        return len(rows)
    except Exception as exc:  # noqa: BLE001 - reported per row below
        print(f"    ! {query.name}: batch of {len(rows)} failed "
              f"({type(exc).__name__}), retrying row by row", file=sys.stderr)

    written = 0
    for row in rows:
        try:
            driver.run(GraphQuery(query.name, query.cypher, {"rows": [row]}),
                       write=True)
            written += 1
        except Exception as exc:  # noqa: BLE001 - this is the useful line
            key = row.get("kgId") or row.get("id") or row.get("key")
            print(f"    ! {query.name}: {key} rejected - "
                  f"{type(exc).__name__}: {str(exc)[:140]}", file=sys.stderr)
    return written


def _apply_schema() -> int:
    """Every statement in schema.cypher. Idempotent, so this is safe to repeat."""
    from sc.kg.cypher import GraphQuery

    text = (Path(__file__).resolve().parents[1] / "sc" / "kg"
            / "schema.cypher").read_text(encoding="utf-8")
    lines = [line for line in text.splitlines()
             if not line.strip().startswith("//")]
    statements = [s.strip() for s in " ".join(lines).split(";") if s.strip()]
    for statement in statements:
        driver.run(GraphQuery("schema", statement, {}), write=True)
    return len(statements)


def _rows_for(graph, since: str | None, stamp: str):
    """The graph, flattened into MERGE rows, grouped by label and by type."""
    nodes: dict[GraphNodeLabel, list[dict]] = {}
    for node in graph.nodes.values():
        updated = str(node.props.get("updatedAt") or "")
        if since and updated and updated < since:
            continue
        key = node.props.get(model.BUSINESS_KEY[node.label])
        if key is None:
            key = node.id.split(":", 1)[1]
        nodes.setdefault(node.label, []).append({
            "key": key, "kgId": node.id, "name": node.name,
            "synthetic": node.synthetic, "updatedAt": updated or stamp,
            "props": {**node.props, "kgLabel": node.label.value,
                      "kgDegree": node.degree, "loadedAt": stamp},
        })

    kept = {row["kgId"] for rows in nodes.values() for row in rows}
    edges: dict[str, list[dict]] = {}
    for edge in graph.edges:
        if edge.source not in kept or edge.target not in kept:
            continue
        edges.setdefault(edge.type.value, []).append({
            "id": edge.id, "source": edge.source, "target": edge.target,
            "synthetic": edge.synthetic,
            "props": {**edge.props, "loadedAt": stamp},
        })
    return nodes, edges


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", default=None,
                        help="where the platform is (default $API_HOST:$API_PORT)")
    parser.add_argument("--offline", action="store_true",
                        help="read SQLite instead of MCP; stamps via=sqlite")
    parser.add_argument("--dry-run", action="store_true",
                        help="count what would be written; touch nothing")
    parser.add_argument("--prune", action="store_true",
                        help="delete nodes this run did not touch")
    parser.add_argument("--since", default=None,
                        help="only rows with updatedAt at or after this")
    parser.add_argument("--reset", action="store_true",
                        help="delete the whole graph first")
    parser.add_argument("--limit", type=int, default=500,
                        help="events to ask each system for")
    args = parser.parse_args()

    bootstrap.load_env()
    host = os.environ.get("API_HOST", "127.0.0.1")
    port = os.environ.get("API_PORT", "8000")
    base_url = (args.platform or f"http://{host}:{port}").rstrip("/")
    stamp = datetime.now().isoformat(timespec="seconds")

    # --- 1. get the reference data -----------------------------------------
    if args.offline:
        print("  Reading SQLite directly (--offline).")
        print("  Nothing crosses MCP, so every node is stamped via=sqlite.")
        from sc import db
        from sc.kg import source_db

        db.init_db()
        reference = source_db.reference_events()
        route = "sqlite"
    else:
        print(f"  Harvesting over MCP from {base_url}")
        try:
            reference = asyncio.run(_harvest(base_url, args.limit))
        except BaseException as exc:  # noqa: BLE001 - reported, then exits
            print(f"\n  The platform did not answer at {base_url}", file=sys.stderr)
            print(f"    {_reason(exc)}\n", file=sys.stderr)
            print("  Nothing was written. Start the platform first:",
                  file=sys.stderr)
            print("      startup.bat", file=sys.stderr)
            print("  or point this at it:", file=sys.stderr)
            print("      python scripts/load_graph.py --platform http://host:8000",
                  file=sys.stderr)
            print("  or read the database directly:", file=sys.stderr)
            print("      python scripts/load_graph.py --offline", file=sys.stderr)
            raise SystemExit(1) from exc
        route = "mcp"

    if not reference:
        print("\n  ! The reference pack is empty.", file=sys.stderr)
        print("    python scripts/generate_backoffice.py", file=sys.stderr)
        raise SystemExit(1)

    # --- 2. project ---------------------------------------------------------
    from sc.state import baseline as baseline_mod

    graph = project.build(baseline_mod.get(), reference)
    nodes, edges = _rows_for(graph, args.since, stamp)
    node_total = sum(len(rows) for rows in nodes.values())
    edge_total = sum(len(rows) for rows in edges.values())
    print(f"\n  {len(reference)} reference events -> "
          f"{node_total} nodes, {edge_total} relationships (via {route})")

    if args.dry_run:
        print("\n  --dry-run: nothing written. By label:")
        for label in sorted(nodes, key=lambda l: l.value):
            print(f"    {label.value:<18} {len(nodes[label]):>6}")
        return

    # --- 3. write -----------------------------------------------------------
    ready, reason = driver.available(refresh=True)
    if not ready:
        print(f"\n  Neo4j is not answering: {reason}", file=sys.stderr)
        print("  No Docker needed - Neo4j Community is a zip:", file=sys.stderr)
        print("      startup.bat graph      (fetch, unpack, install driver)",
              file=sys.stderr)
        print("      startup.bat            (starts it with everything else)",
              file=sys.stderr)
        print("  and put NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD in .env.",
              file=sys.stderr)
        raise SystemExit(1)

    if args.reset:
        from sc.kg.cypher import GraphQuery

        driver.run(GraphQuery("reset",
                              "MATCH (n) WHERE n.kgId IS NOT NULL "
                              "DETACH DELETE n", {}), write=True)
        print("  --reset: the previous graph was deleted")

    print(f"  Applied {_apply_schema()} schema statements")

    written_nodes = 0
    for label in sorted(nodes, key=lambda l: l.value):
        query = cypher.node_upsert(label)
        rows = nodes[label]
        for start in range(0, len(rows), BATCH):
            written_nodes += _write_batch(query, rows[start:start + BATCH])

    written_edges = 0
    for rel_type in sorted(edges):
        query = cypher.edge_upsert(rel_type)
        rows = edges[rel_type]
        for start in range(0, len(rows), BATCH):
            written_edges += _write_batch(query, rows[start:start + BATCH])

    print(f"  MERGEd {written_nodes} nodes and {written_edges} relationships")

    if args.prune:
        removed = 0
        for label in GraphNodeLabel:
            query = cypher.prune_query(label)
            from sc.kg.cypher import GraphQuery

            result = driver.run(
                GraphQuery(query.name, query.cypher, {"runStamp": stamp}),
                write=True)
            removed += (result[0]["removed"] if result else 0)
        print(f"  --prune: removed {removed} nodes this run did not touch")

    driver.close_all()
    print()
    print(f"  Loaded at {stamp}, via {route}.")
    print("  MERGE is idempotent but not convergent: run this again and the")
    print("  counts do not move, but a node that has left the source stays")
    print("  until --prune.")


if __name__ == "__main__":
    main()
