"""MCP server exposing the platform's toolset.

    python -m sc.mcp_server          # stdio, for an MCP client
    python -m sc.mcp_server --list   # show the toolset without starting a server

This is a **thin wrapper**. Every function here delegates to the same module in
``sc/tools`` that the graph calls directly, so there is one implementation and
one set of tests behind both surfaces. Nothing about a tool's behaviour depends
on whether it was reached over MCP or in-process.

Two things that follow from that:

*   The graph can run either way, and now genuinely does. ``USE_MCP=1``
    routes the evidence desk's catalog lookups over stdio to the toolset that
    owns them (see ``sc/mcp/``); ``USE_MCP=0`` calls the same functions
    directly. The answer is identical either way, and a failed spawn falls
    back in-process rather than losing the run.

*   This module is the convenience form: one server with everything on it, for
    a client that wants a single connection. The partition in ``sc/mcp/`` is
    the architecture - six servers split by owning system, five of which cannot
    change what a channel sees.
*   The toolset can be attached to any MCP client (Claude Desktop, for
    instance) and driven by hand against the same live state the UI is showing.

Mutating tools keep their controls here: ``commit_plan`` still refuses without
a recorded approval, and idempotency keys still make a replayed call a no-op.
Exposing a tool over MCP does not exempt it from the safeguards.
"""

from __future__ import annotations

import argparse
import json

from mcp.server.fastmcp import FastMCP

from sc.rag import retrieve
from sc.replay import ingest, tape
from sc.tools import network as network_tools
from sc.tools import planning

mcp = FastMCP("product-intelligence-factory")


# ---------------------------------------------------------------------------
# Product catalog
# ---------------------------------------------------------------------------


@mcp.tool()
def get_network_state(as_of: str | None = None,
                      as_of_recorded: str | None = None) -> dict:
    """The catalog plus whatever has been corrected under it.

    as_of moves along valid time ("what is true then"); as_of_recorded moves
    along recorded time ("what was known then"). Both default to the simulated
    clock. ISO-8601 strings.
    """
    return network_tools.get_network_state(as_of, as_of_recorded)


@mcp.tool()
def trace_dependencies(entity_id: str, depth: int = 3,
                       as_of: str | None = None) -> dict:
    """Blast radius of a correction, from the lineage the content was built
    with. Accepts a document, attribute reference, variant, product, listing or
    channel id.
    """
    return network_tools.trace_dependencies(entity_id, depth, as_of)


@mcp.tool()
def variant_diff(product_id: str, as_of: str | None = None) -> dict:
    """The attribute table across a product's base and variants, each value
    carrying the document and version it stands on.

    This is what settles "does the correction apply to the base model or the
    variant" from the record rather than from an opinion.
    """
    return network_tools.variant_diff(product_id, as_of)


@mcp.tool()
def get_derivation(entity_id: str) -> dict:
    """What an asset or a listing was built from, and at which version."""
    return network_tools.get_derivation(entity_id)


# ---------------------------------------------------------------------------
# Channel registry
# ---------------------------------------------------------------------------


@mcp.tool()
def channel_rules(channel_id: str, field: str | None = None) -> dict:
    """The rules in force for a channel, or for one of its fields.

    Rules are data, so this is a read rather than a description of code: the
    reviewer sees the same row the validator bound on.
    """
    return network_tools.channel_rules(channel_id, field)


@mcp.tool()
def get_listing_state(listing_id: str, as_of: str | None = None) -> dict:
    """One listing as it stands: its values, its copy, and what has moved
    underneath it since that copy was written."""
    return network_tools.get_listing_state(listing_id, as_of)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@mcp.tool()
def query_events(limit: int = 50, since_seq: int = 0,
                 event_type: str | None = None) -> dict:
    """Events released so far. The future of the tape is never visible.

    event_type: SUPPLIER_FEED | SPEC_DOC | CHANNEL_STATUS | CATALOG_UPDATE |
    PUBLISH_TELEMETRY | COMMS
    """
    events = tape.released(limit=limit, since_seq=since_seq,
                           event_type=event_type)
    return {"events": [e.model_dump(mode="json") for e in events],
            "replay": tape.state().model_dump(mode="json")}


@mcp.tool()
def advance_events(steps: int = 1) -> dict:
    """Release the next events from the tape and ingest them."""
    released = tape.advance(steps)
    signals = ingest.ingest(released)
    return {"released": [e.model_dump(mode="json") for e in released],
            "signals": [s.model_dump(mode="json") for s in signals],
            "replay": tape.state().model_dump(mode="json")}


@mcp.tool()
def replay_state() -> dict:
    """Where the simulated clock currently sits."""
    return {"replay": tape.state().model_dump(mode="json"),
            "inject_seq": tape.inject_seq(),
            "ingest_cursor": ingest.cursor()}


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


@mcp.tool()
def search_docs(query: str, top_k: int = 5, doc_types: str | None = None,
                entities: str | None = None,
                include_comms: bool = False) -> dict:
    """Hybrid search over standards, channel specs, policies and postmortems.

    Runs BM25 and dense retrieval and fuses the rankings, so identifier queries
    ("VAR-01B") and paraphrase queries ("can we still change the catalogue")
    both work.

    doc_types / entities: comma-separated filters, e.g. "POSTMORTEM" or
    "SUP-01,VAR-01B". Correspondence is excluded unless include_comms is set -
    an email is evidence, not guidance.
    """
    results = retrieve.search(
        query, top_k=top_k,
        doc_types=_csv(doc_types), entities=_csv(entities),
        include_comms=include_comms)
    return {"query": query, "results": retrieve.cite(results)}


@mcp.tool()
def get_doc(doc_id: str) -> dict:
    """Full text of one document, in order."""
    chunks = retrieve.get_document(doc_id)
    if not chunks:
        return {"error": f"no document {doc_id}"}
    return {"doc_id": doc_id, "title": chunks[0].title,
            "doc_type": chunks[0].doc_type,
            "metadata": chunks[0].metadata,
            "text": "\n\n".join(c.text for c in chunks)}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@mcp.tool()
def run_scenario(change_set: dict, as_of: str | None = None,
                 as_of_recorded: str | None = None) -> dict:
    """Validate one candidate resolution against the catalog and the channels.

    This is the only way any number enters the system - readiness,
    completeness, republish effort, safety flags and the publish verdict all
    come from here, never from a model.

    change_set: {"id": "...", "scope": {"level": "VARIANT",
    "entities": ["VAR-01B"]}, "actions": [{"kind": "SET_ATTRIBUTE", ...}, ...]}
    Action kinds: SET_ATTRIBUTE, REGENERATE_COPY, REMAP_TAXONOMY, SET_FACET,
    WITHHOLD_CHANNEL, REQUEST_SUPPLIER_INPUT.
    """
    return planning.run_scenario(change_set, as_of=as_of,
                                 as_of_recorded=as_of_recorded)


@mcp.tool()
def compare_scenarios(deltas: list[dict], weights: dict | None = None,
                      as_of: str | None = None) -> dict:
    """Validate several candidates, score them, and mark the Pareto front.

    weights: {"readiness": 0.45, "precision": 0.30, "effort": 0.15,
              "completeness": 0.10}
    Safety is not among them: a resolution with an open safety flag never
    outranks one without, whatever the weights say.
    """
    return planning.compare_scenarios(deltas, weights, as_of=as_of)


# ---------------------------------------------------------------------------
# Publishing - approval-gated and idempotent
# ---------------------------------------------------------------------------


@mcp.tool()
def propose_change(incident_id: str, scenario_id: str, change_set: dict,
                   idempotency_key: str | None = None) -> dict:
    """Take soft publish locks on the (channel, product) pairs a candidate
    would republish.

    Conflicts surface here, at proposal time, rather than after a reviewer has
    approved something that cannot be published.
    """
    return planning.propose_change(incident_id, scenario_id, change_set,
                                   idempotency_key=idempotency_key)


@mcp.tool()
def reserve_publish(resource_id: str, bucket_date: str, incident_id: str,
                    scenario_id: str, status: str = "SOFT") -> dict:
    """Claim one (channel, product) for one publish batch date.

    A HARD claim is exclusive and the exclusivity is enforced by a partial
    unique index. The second one to arrive is refused - this is what makes two
    runs publishing different corrections of the same product to the same
    channel impossible rather than merely unlikely.
    """
    return planning.reserve_publish(resource_id, bucket_date, incident_id,
                                    scenario_id, status)


@mcp.tool()
def commit_plan(incident_id: str, scenario_id: str, actions: list[dict],
                actor: str = "publisher",
                idempotency_key: str | None = None) -> dict:
    """Publish an approved resolution.

    REFUSES without a recorded APPROVE decision for this resolution, if a
    source document has moved since it was validated, or if a safety or
    allergen declaration is still open on an affected listing. The checks live
    in the tool, not in the caller, so no client - MCP or otherwise - can route
    around them.
    """
    return planning.commit_plan(incident_id, scenario_id, actions,
                                actor=actor, idempotency_key=idempotency_key)


@mcp.tool()
def rollback(incident_id: str, scenario_id: str, reason: str = "",
             idempotency_key: str | None = None) -> dict:
    """Unpublish: release the exclusive locks and mark the actions reversed."""
    return planning.rollback(incident_id, scenario_id, reason=reason,
                             idempotency_key=idempotency_key)


@mcp.tool()
def open_reservations(incident_id: str | None = None) -> dict:
    """Publish locks currently held, by (channel, product) and batch date."""
    return {"reservations": planning.open_reservations(incident_id)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


def _bootstrap() -> None:
    """Bring up the same state the API uses.

    An MCP client attaches to a live system, so the database, the event tape
    and the retrieval index all need to exist before the first tool call.
    """
    from sc import bootstrap

    # Lexical index only - a stdio server should start without waiting on the
    # gateway, and BM25 alone answers identifier queries.
    bootstrap.ensure_ready()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true",
                        help="print the toolset and exit")
    args = parser.parse_args()

    _bootstrap()

    if args.list:
        import asyncio

        tools = asyncio.run(mcp.list_tools())
        print(json.dumps([{"name": t.name,
                           "description": (t.description or "").split("\n")[0]}
                          for t in tools], indent=2))
        return

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
