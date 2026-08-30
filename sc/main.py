"""FastAPI application: REST API, live event stream, and the built UI.

One process serves everything. There is no separate web server and no BFF hop -
the domain logic sits next to the graph, and the API is a thin layer over the
same tool functions the graph calls.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from sc import db
from sc.contracts import ReplayAction, ReplayCommand
from sc.graph import build as graph_build
from sc.graph import nodes as graph_nodes
from sc.llm import gateway, models
from sc.rag import index as rag_index
from sc.rag import retrieve
from sc.replay import ingest, tape
from sc.state import baseline as baseline_mod
from sc.tools import network as network_tools
from sc.tools import planning

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="Autonomous Product Intelligence Factory")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGIN", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Live broadcast - replaces the broker's fan-out to subscribers
# ---------------------------------------------------------------------------


class Broadcaster:
    """In-process pub/sub for SSE subscribers.

    Queues are bounded and drop their oldest entry when full: a browser tab
    left open overnight must not grow the process without limit.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, kind: str, payload: dict) -> None:
        message = {"kind": kind, "ts": datetime.now().isoformat(), **payload}
        for queue in list(self._subscribers):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(message)


bus = Broadcaster()
_clock_task: asyncio.Task | None = None
#: Holds the estate systems' session managers open for the life of the app.
_estate_stack = None


def _on_events(events) -> None:
    """Clock callback: ingest, then tell the UI what happened.

    Ingest returns the corrections it detected, and each one goes out on its own
    so the live feed can distinguish "a supplier document arrived" from "that
    document contradicts what the copy was written against".
    """
    signals = ingest.ingest(events)
    bus.publish("events", {
        "events": [e.model_dump(mode="json") for e in events],
        "replay": tape.state().model_dump(mode="json"),
    })
    for signal in signals:
        bus.publish("signal", {"signal": signal.model_dump(mode="json")})


@app.on_event("startup")
async def startup() -> None:
    global _clock_task, _estate_stack
    from contextlib import AsyncExitStack

    from sc import bootstrap

    bootstrap.ensure_ready()
    _clock_task = asyncio.create_task(tape.run_clock(_on_events))

    # Each estate system is a mounted Starlette sub-app, and mounting does not
    # run a sub-app's lifespan. A streamable-HTTP server whose session manager
    # was never started accepts the connection and then fails the first
    # request, which reads as a broken supplier rather than an unstarted one.
    try:
        from sc.estate import server as _estate_server

        _estate_stack = AsyncExitStack()
        await _estate_stack.__aenter__()
        started = await _estate_server.start(_estate_stack)

        from sc.estate import publication_server as _publishers

        started += await _publishers.start(_estate_stack)
        log.info("estate: %d system server(s) listening", started)

        # Dial them, in the background. Ten handshakes is a second or two, and
        # the application must not spend that before it will answer anything -
        # a demo that cannot boot because a mock supplier was slow is a worse
        # outcome than a demo whose estate fills in a moment later.
        async def _dial() -> None:
            import os as _os

            base = f"http://127.0.0.1:{_os.environ.get('API_PORT', '8000')}"
            await asyncio.to_thread(_estate_server.connect_all, base)

        asyncio.create_task(_dial())
    except Exception as exc:  # noqa: BLE001 - the app must start regardless
        log.warning("estate session managers not started: %s", exc)


@app.on_event("shutdown")
async def shutdown() -> None:
    if _clock_task is not None:
        _clock_task.cancel()
    if _estate_stack is not None:
        try:
            await _estate_stack.aclose()
        except Exception:  # noqa: BLE001 - shutdown is not a place to fail
            log.debug("estate shutdown was untidy", exc_info=True)
        with contextlib.suppress(asyncio.CancelledError):
            await _clock_task


# ---------------------------------------------------------------------------
# Health and system
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    base = baseline_mod.get()
    return {
        "ok": True,
        "gateway": gateway.health(),
        "replay": tape.state().model_dump(mode="json"),
        "data": {
            "nodes": len(base.catalog.nodes),
            "listings": len(base.listings),
            "assets": len(base.assets),
            "events": tape.total_events(),
        },
        "ingest_cursor": ingest.cursor(),
    }


@app.get("/api/llm/models")
def llm_models(refresh: bool = False) -> dict:
    """Live model list, read from the gateway's /v1/models.

    ``source`` tells the UI whether this came from the gateway or from the
    configured fallback, so a stale list is never presented as current.
    """
    listing = models.list_models(refresh=refresh)
    return {**listing,
            "active": gateway.default_model(),
            "embed": gateway.embed_model(),
            "cache_enabled": gateway.cache_enabled(),
            "gateway_url": gateway.base_url()}


@app.post("/api/llm/config")
def llm_config(body: dict) -> dict:
    """Change model selection. Hot-loaded now, written back to .env."""
    result = models.select(
        model=body.get("model"),
        embed_model=body.get("embed_model"),
        cache_enabled=body.get("cache_enabled"),
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result)
    bus.publish("llm_config", {"config": result})
    return {**result, **models.list_models(refresh=True)}


@app.post("/api/llm/test")
def llm_test(body: dict | None = None) -> dict:
    return models.test_model((body or {}).get("model"))


@app.get("/api/llm/usage")
def llm_usage(run_id: str | None = None) -> dict:
    return gateway.usage_summary(run_id)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@app.get("/api/network")
def get_network(as_of: str | None = None,
                as_of_recorded: str | None = None) -> dict:
    """The factory map: suppliers, products, variants, channels and listings,
    plus whatever corrections are in force at the instant asked for."""
    return network_tools.get_network_state(as_of, as_of_recorded)


@app.get("/api/network/trace/{entity_id}")
def trace(entity_id: str, depth: int = 3) -> dict:
    """The blast radius of one correction, counted in fields, copy and channels."""
    return network_tools.trace_dependencies(entity_id, depth)


@app.get("/api/catalog/variants/{product_id}")
def catalog_variants(product_id: str, as_of: str | None = None) -> dict:
    """The attribute table across a product's base and its variants.

    Flattened to path -> variant -> cell, with the paths the variants disagree
    on named separately. That last list is the whole of the base-versus-variant
    question: a correction naming the product and not the variant is only
    answerable against the columns that actually differ.

    The cell is the tool's own - value, version, doc, provenance, confidence -
    rather than the bare value. The document is the argument: the base model
    was independently certified at 45 W by a named document a fortnight before
    the ambiguous correction, and a reviewer cannot check that against a
    number on its own. It is also what keeps this route and the MCP tool
    saying the same thing about the same table.
    """
    diff = network_tools.variant_diff(product_id, as_of)
    if diff.get("error"):
        raise HTTPException(status_code=404, detail=diff["error"])

    base = baseline_mod.get()
    return {
        "product": diff["product"]["id"],
        "variants": [{**v, "listings": base.listings_of.get(v["id"], [])}
                     for v in diff["variants"]],
        "attributes": {row["path"]: row["values"] for row in diff["attributes"]},
        "differs": [row["path"] for row in diff["attributes"] if row["differs"]],
    }


@app.get("/api/catalog/derivation/{entity_id}")
def catalog_derivation(entity_id: str, as_of: str | None = None) -> dict:
    """Lineage in both directions for an attribute, an asset or a listing.

    Composed from the reads that already exist rather than from a third
    traversal: ``get_derivation`` for what the output was built from,
    ``trace_dependencies`` for everything still carrying it, and
    ``get_listing_state`` for whether each asset the walk reaches is standing on
    a value that has since moved. Staleness is the half a reviewer acts on, and
    only the listing read knows it.
    """
    lineage = network_tools.get_derivation(entity_id)
    trace = network_tools.trace_dependencies(entity_id, as_of=as_of)
    affected = trace["affected"]
    reached = set(affected["assets"])

    assets = []
    for listing_id in affected["listings"]:
        state = network_tools.get_listing_state(listing_id, as_of)
        channel_id = state["listing"]["channel_id"]
        assets += [{"id": asset["id"], "listing_id": listing_id,
                    "field": asset["field"], "channel_id": channel_id,
                    "built_at_version": asset["built_at_version"],
                    "stale": asset["stale"]}
                   for asset in state["assets"] if asset["id"] in reached]

    # An attribute reference has no derivation of its own - it *is* the source -
    # so the refs the walk stands on are the honest answer in that case.
    if lineage.get("kind") == "asset":
        derived_from = [field["ref"] for field in lineage["derived_from"]]
    elif lineage.get("kind") == "listing":
        derived_from = lineage["sources"]
    else:
        derived_from = affected["attributes"]

    return {"id": entity_id,
            "derived_from": derived_from,
            "assets": assets,
            "listings": affected["listings"],
            "channels": affected["channels"],
            "totals": trace["totals"]}


# ---------------------------------------------------------------------------
# Events and replay control
# ---------------------------------------------------------------------------


@app.get("/api/events")
def get_events(limit: int = 100, since_seq: int = 0,
               type: str | None = None) -> dict:
    events = tape.released(limit=limit, since_seq=since_seq, event_type=type)
    return {"events": [e.model_dump(mode="json") for e in events],
            "replay": tape.state().model_dump(mode="json")}


@app.get("/api/events/stream")
async def stream_events():
    """Server-sent events. The UI's live feed rides this."""
    queue = bus.subscribe()

    async def generator():
        try:
            yield _sse({"kind": "hello",
                        "replay": tape.state().model_dump(mode="json")})
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield _sse(message)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # keeps proxies from closing us
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


@app.post("/api/control/replay")
def control_replay(command: ReplayCommand) -> dict:
    """Drive the tape: start, pause, step, speed, jump, reset."""
    action = command.action
    released = []

    if action == ReplayAction.START:
        tape.set_running(True)
    elif action == ReplayAction.PAUSE:
        tape.set_running(False)
    elif action == ReplayAction.STEP:
        tape.set_running(False)
        released = tape.advance(command.steps)
    elif action == ReplayAction.SPEED:
        tape.set_speed(command.speed or 1.0)
    elif action == ReplayAction.JUMP:
        target = command.to_seq if command.to_seq is not None else tape.inject_seq()
        released = tape.jump_to(target)
    elif action == ReplayAction.RESET:
        tape.reset()
        db.connect().execute("DELETE FROM event_cursors")
        db.connect().commit()

    if released:
        _on_events(released)

    return {"replay": tape.state().model_dump(mode="json"),
            "released": len(released),
            "inject_seq": tape.inject_seq()}


@app.get("/api/control/state")
def control_state() -> dict:
    return {"replay": tape.state().model_dump(mode="json"),
            "inject_seq": tape.inject_seq(),
            "ingest_cursor": ingest.cursor()}


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


@app.get("/api/sop/search")
def sop_search(q: str, top_k: int = 6, doc_types: str | None = None,
               entities: str | None = None, tags: str | None = None,
               semantic: bool = True, lexical: bool = True) -> dict:
    """Hybrid retrieval over the standards, channel-spec, policy and postmortem
    corpus.

    Both retrievers run by default; the flags exist so the UI can show what
    each contributes, which is the clearest way to explain why the hybrid is
    there at all.
    """
    results = retrieve.search(
        q, top_k=top_k,
        doc_types=_csv(doc_types), entities=_csv(entities), tags=_csv(tags),
        semantic=semantic, lexical=lexical)
    return {"query": q, "results": retrieve.cite(results),
            "index": rag_index.status()}


@app.get("/api/sop/{doc_id}")
def sop_document(doc_id: str) -> dict:
    chunks = retrieve.get_document(doc_id)
    if not chunks:
        raise HTTPException(status_code=404, detail=f"no document {doc_id}")
    return {"doc_id": doc_id, "title": chunks[0].title,
            "doc_type": chunks[0].doc_type,
            "metadata": chunks[0].metadata,
            "chunks": [c.model_dump(mode="json") for c in chunks]}


@app.get("/api/sop")
def sop_index_status() -> dict:
    return rag_index.status()


@app.post("/api/sop/reindex")
def sop_reindex(body: dict | None = None) -> dict:
    """Rebuild the index. Exposed in System Control so the corpus can be
    edited and re-indexed without restarting."""
    options = body or {}
    result = rag_index.build(
        include_comms=options.get("include_comms", True),
        embed=options.get("embed", True))
    bus.publish("reindex", {"result": result})
    return result


def _csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


# ---------------------------------------------------------------------------
# Change sets - validated, never simulated
# ---------------------------------------------------------------------------


@app.post("/api/scenarios/simulate")
def simulate_change_set(body: dict) -> dict:
    """Validate one candidate change set. Drives the what-if panel.

    ``as_of_recorded`` checks a resolution against what was known when it was
    proposed rather than against corrections that have landed since.
    """
    delta = body.get("delta")
    if not delta:
        raise HTTPException(status_code=400, detail="missing 'delta'")
    return planning.run_scenario(delta, as_of=body.get("as_of"),
                                 as_of_recorded=body.get("as_of_recorded"))


@app.post("/api/scenarios/compare")
def compare_change_sets(body: dict) -> dict:
    """Validate several candidates and rank them - the reviewer's table."""
    deltas = body.get("deltas") or []
    if not deltas:
        raise HTTPException(status_code=400, detail="missing 'deltas'")
    return planning.compare_scenarios(deltas, body.get("weights"),
                                      as_of=body.get("as_of"))


# ---------------------------------------------------------------------------
# Correction runs - the LangGraph loop
# ---------------------------------------------------------------------------


@app.get("/api/cases")
def open_cases() -> dict:
    """The open correction cases at the replay clock, worst first.

    One case is one product, because that is the unit a reviewer commits and the
    unit the publish lock is taken on. This is the list the UI offers, and the
    ``case_id`` it returns is what a run is started against.
    """
    now = tape.sim_now()
    cases = graph_nodes.open_cases(graph_nodes._signals_in_force(now),
                                   baseline_mod.get())
    return {"cases": cases, "as_of": now.isoformat()}


@app.post("/api/runs")
def start_run(body: dict | None = None) -> dict:
    """Start a correction run. Returns when the graph finishes or stops for
    approval - the interrupt is the normal outcome, not an error.

    ``case_id`` scopes the run to one product's correction. Omitting it is not
    "look at everything": monitor takes the worst case open, so the reviewer
    still gets one coherent decision.
    """
    options = body or {}
    incident_id = options.get("incident_id") or f"INC-{uuid.uuid4().hex[:8]}"
    thread_id = options.get("thread_id") or incident_id

    result = graph_build.start_run(incident_id, thread_id,
                                   weights=options.get("weights"),
                                   case_id=options.get("case_id"))
    bus.publish("run", {"thread_id": thread_id, "status": result["status"],
                        "awaiting_approval": result["awaiting_approval"]})
    return {"incident_id": incident_id, **result}


@app.post("/api/runs/stream")
async def start_run_streaming(body: dict | None = None):
    """Same run, streamed node by node.

    The graph's own progress drives the trace view, so what the reviewer watches
    is the reasoning actually happening rather than a progress bar imitating it.
    """
    options = body or {}
    incident_id = options.get("incident_id") or f"INC-{uuid.uuid4().hex[:8]}"
    thread_id = options.get("thread_id") or incident_id
    weights = options.get("weights")
    case_id = options.get("case_id")

    async def generator():
        queue: asyncio.Queue = asyncio.Queue()

        def produce():
            try:
                for item in graph_build.stream_run(incident_id, thread_id,
                                                   weights, case_id):
                    queue.put_nowait(item)
            except Exception as exc:
                queue.put_nowait({"node": "error", "error": str(exc)[:400]})
            finally:
                queue.put_nowait(None)

        # The graph is synchronous and CPU/IO mixed; running it in a worker
        # thread keeps the event loop free to flush the stream as it arrives.
        task = asyncio.get_running_loop().run_in_executor(None, produce)
        yield _sse({"kind": "run_started", "thread_id": thread_id,
                    "incident_id": incident_id})
        while True:
            item = await queue.get()
            if item is None:
                break
            yield _sse({"kind": "node", **item})
        await task
        yield _sse({"kind": "run_finished",
                    **graph_build.snapshot(thread_id)})

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.post("/api/runs/{thread_id}/replan")
def replan(thread_id: str, body: dict | None = None) -> dict:
    """Revise an existing resolution against evidence that arrived after it.

    Same thread, same correction case, next revision. The response carries a
    ``plan_diff`` computed by the validator: which resolution led before, which
    leads now, and what that move costs.
    """
    reason = (body or {}).get("reason", "")
    try:
        result = graph_build.replan_run(thread_id, reason)
    except graph_build.ReplanRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    bus.publish("run", {"thread_id": thread_id, "status": result["status"],
                        "awaiting_approval": result["awaiting_approval"],
                        "revision": result["values"].get("revision")})
    return result


@app.post("/api/runs/{thread_id}/replan/stream")
async def replan_streaming(thread_id: str, body: dict | None = None):
    """The revision, streamed node by node."""
    reason = (body or {}).get("reason", "")

    async def generator():
        queue: asyncio.Queue = asyncio.Queue()

        def produce():
            try:
                for item in graph_build.stream_replan(thread_id, reason):
                    queue.put_nowait(item)
            except Exception as exc:
                queue.put_nowait({"node": "error", "error": str(exc)[:400]})
            finally:
                queue.put_nowait(None)

        task = asyncio.get_running_loop().run_in_executor(None, produce)
        yield _sse({"kind": "run_started", "thread_id": thread_id,
                    "replan": True})
        while True:
            item = await queue.get()
            if item is None:
                break
            yield _sse({"kind": "node", **item})
        await task
        yield _sse({"kind": "run_finished", **graph_build.snapshot(thread_id)})

    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


@app.get("/api/evidence/tools")
def evidence_tools() -> dict:
    """The scope resolver's allowlist, as served rather than as documented.

    Reading it from ``evidence.TOOLS`` means the governance claim in the UI
    cannot drift from the governance actually in force.
    """
    from sc.graph import evidence

    return {
        "max_passes": evidence.MAX_PASSES,
        "max_requests_per_pass": evidence.MAX_REQUESTS_PER_PASS,
        "tools": [{"name": t.name, "takes": t.takes, "describes": t.describes}
                  for t in evidence.TOOLS.values()],
    }


log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# A2A peers - mounted at import, so the cards are discoverable whether or not
# the graph is configured to use the protocol. Discovery and delegation are
# different switches: another organisation's agent can read these cards and
# call these skills even when this process is talking to itself.
# ---------------------------------------------------------------------------

try:
    from sc.a2a import server as a2a_server

    from sc.a2a import client as _a2a_client
    A2A_MOUNTED = a2a_server.mount(app, base_url=_a2a_client.base_url())
except Exception as _exc:  # noqa: BLE001 - the app must start regardless
    A2A_MOUNTED = []
    log.warning("A2A peers not mounted: %s", _exc)


# ---------------------------------------------------------------------------
# The estate, each system its own MCP server at /mcp/{system_id}
#
# Mounted here for the same reason the peers are: the calls still cross the
# protocol and each system is separately addressable, and running ten processes
# to prove a point about boundaries would cost a demo ten things that can fail.
# Moving one system to its own host is a change to a URL.
# ---------------------------------------------------------------------------

try:
    from sc.estate import server as estate_server

    ESTATE_MOUNTED = estate_server.mount(app)
except Exception as _exc:  # noqa: BLE001 - the app must start regardless
    ESTATE_MOUNTED = []
    log.warning("estate systems not mounted: %s", _exc)

# The other end of the pipe: one server per channel that owns live listings.
# Mounted apart from the ingest estate because these can change what a shopper
# sees, and an operator handing out endpoints should be able to see which is
# which from the path alone.
try:
    from sc.estate import publication_server

    PUBLISHERS_MOUNTED = publication_server.mount(app)
except Exception as _exc:  # noqa: BLE001 - the app must start regardless
    PUBLISHERS_MOUNTED = []
    log.warning("publication systems not mounted: %s", _exc)


@app.get("/.well-known/agent-cards.json")
def agent_directory() -> dict:
    """Every capability this estate publishes, in one document.

    The per-agent cards were already served at the address the A2A
    specification puts them, and that is correct and not discoverable: a peer
    that already knows an identifier can fetch a card, and a peer that knows
    only the host cannot find out what is here.

    Built from the same cards rather than beside them, so a directory cannot
    quietly drift from the capabilities it claims to index.
    """
    from sc.a2a import client as a2a_client
    from sc.a2a import directory as a2a_directory

    return a2a_directory.build(a2a_client.base_url(), A2A_MOUNTED)


@app.get("/api/a2a/agents")
def a2a_agents() -> dict:
    """The peer roster, their cards, and how delegation is currently running."""
    from sc.a2a import client as a2a_client

    return {"agents": A2A_MOUNTED, "transport": a2a_client.status()}


@app.get("/api/a2a/calls")
def a2a_calls(limit: int = 60) -> dict:
    """Recent delegations, newest first, with the transport each one used."""
    from sc.a2a import client as a2a_client

    return {"calls": a2a_client.calls(limit)}


@app.post("/api/a2a/transport")
def a2a_transport(body: dict) -> dict:
    """Switch A2A delegation on or off without restarting."""
    import os as _os

    from sc.a2a import client as a2a_client

    _os.environ["USE_A2A"] = "1" if body.get("enabled") else "0"
    a2a_client.revive()
    return a2a_client.status()


@app.get("/api/mcp/servers")
def mcp_servers() -> dict:
    """Every toolset: the six that ship here, plus whatever is connected.

    One listing rather than two endpoints, because the console's question is
    "what can be reached", and a reader should not have to join two lists to
    answer it. Each entry says where it came from, because "can I hand this
    out" is a different question for a server that ships here and one somebody
    connected five minutes ago.
    """
    from sc.mcp import client as mcp_client
    from sc.mcp import connections as mcp_connections
    from sc.mcp import _runtime

    return {
        "servers": mcp_connections.toolsets(),
        "transport": mcp_client.status(),
        "counts": _runtime.counts(),
    }


# ---------------------------------------------------------------------------
# The external estate
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Product 360
#
# Every read here delegates to the same functions the rest of the system calls.
# Two implementations of one read become two accounts of the same product the
# first time either is edited, and this surface is the one a reviewer trusts
# last before a launch.
# ---------------------------------------------------------------------------


@app.get("/api/products")
def product_search(q: str = "", limit: int = 20) -> dict:
    """Find a product by SKU, internal identifier or name.

    An empty query lists everything rather than refusing: the product view opens
    on this, and a page that opens empty until you type is a page that looks
    broken.
    """
    from sc.readiness import search as product_search_mod

    # Verdicts alongside, because the list view exists to show which products
    # are holding a launch up and a row without one is a row nobody can act on.
    # The reading checks stay off here: twenty products would otherwise be sixty
    # model calls to render a page nobody has clicked into.
    return {"query": q,
            "results": product_search_mod.with_readiness(q, limit)}


@app.get("/api/products/{entity_id}")
def product_record(entity_id: str) -> dict:
    """One product's merged record - values, media, carriers and disagreements."""
    from sc.readiness import record as record_mod

    record = record_mod.build(entity_id)
    if record is None:
        raise HTTPException(status_code=404, detail="no such product")
    return record_mod.as_dict(record, baseline_mod.get())


@app.get("/api/products/{entity_id}/readiness")
def product_readiness(entity_id: str, use_model: bool = True) -> dict:
    """The nine checks, their findings, and the verdict.

    ``use_model=false`` runs the six deterministic checks only, and the response
    says so. An assessment that could not reach a model has found fewer things,
    and reporting that as clean is the most dangerous thing this surface could
    do.
    """
    import sc.readiness as readiness

    summary = readiness.assess(entity_id, use_model=use_model)
    if summary is None:
        raise HTTPException(status_code=404, detail="no such product")
    return summary


@app.get("/api/products/{entity_id}/preview")
def product_preview(entity_id: str, use_model: bool = True,
                    actor: str = "") -> dict:
    """The staging page, for a record that is ready.

    A record that is not ready is refused with its verdict and findings rather
    than rendered with a warning across the top: a page that renders a blocked
    product is a page somebody screenshots.

    **On authorisation, plainly.** This route requires a named actor, and that
    is exactly - and only - what the approval gate requires. Neither is
    authenticated: this system has no identity provider, no session and no
    password anywhere, and inventing one here would protect unpublished copy
    more carefully than it protects the decision to publish it, which would be
    the wrong way round.

    What the actor buys is accountability rather than access control. A preview
    is a view of unpublished commercial content, and "who looked at this before
    it launched" becomes answerable from the audit ledger instead of being a
    question nobody can ask.
    """
    import sc.readiness as readiness
    from sc.readiness import preview as preview_mod

    who = (actor or "").strip()
    if not who:
        raise HTTPException(
            status_code=403,
            detail="a named actor is required to preview unpublished content, "
                   "the same as for an approval decision")

    summary = readiness.assess(entity_id, use_model=use_model)
    if summary is None:
        raise HTTPException(status_code=404, detail="no such product")

    page = preview_mod.build(entity_id, summary, use_model=use_model)
    # Recorded whether or not it rendered. "Somebody tried to preview a blocked
    # product" is at least as interesting as somebody previewing a ready one.
    planning.audit(
        who, "PREVIEW", "variant", entity_id,
        {"rendered": page.get("rendered"), "verdict": page.get("verdict")})
    return page


# ---------------------------------------------------------------------------
# The publication estate
#
# The other end of the pipe. These read the blast radius the catalog already
# derives and answer it in the vocabulary the people who have to act on it use:
# SKUs, and the systems that own the listings carrying them.
# ---------------------------------------------------------------------------


@app.get("/api/publication/systems")
def publication_systems() -> dict:
    """The systems that own live listings, derived from the channels.

    Derived rather than configured: a publication estate that could disagree
    with the channel list is a second account of where content goes, and the
    first thing it would disagree about is the channel somebody just added.
    """
    from sc.estate import publication

    base = baseline_mod.get()
    mounted = {entry.get("id"): entry for entry in PUBLISHERS_MOUNTED}
    return {"systems": [
        {"id": s.id, "channel_id": s.channel_id, "title": s.title,
         "owner": s.owner, "recallable": s.recallable,
         "freeze_days": s.freeze_days,
         # The address it actually answers on, where it mounted. Falling back
         # to the derived path rather than omitting it: a system that failed to
         # mount should still be nameable.
         "endpoint": mounted.get(s.id, {}).get("url", s.endpoint),
         "mounted": s.id in mounted and "error" not in mounted[s.id],
         "verbs": list(publication.VERBS)}
        for s in publication.systems(base)]}


@app.get("/api/publication/impact/{entity_id}")
def publication_impact(entity_id: str, as_of: str | None = None) -> dict:
    """What a correction to this entity reaches, in SKUs and systems.

    A blast radius expressed in internal identifiers is one only this system can
    read. Everybody who has to act on one - a buyer, a supplier, a marketplace
    account manager - works in SKUs.
    """
    from sc.estate import publication, remediation

    base = baseline_mod.get()
    trace = network_tools.trace_dependencies(entity_id, as_of=as_of)
    return {
        "root": entity_id,
        "totals": trace["totals"],
        "skus": publication.affected_skus(trace, base),
        "systems": publication.blast_to_systems(trace, base),
        # What would happen if this were dispatched now, without dispatching.
        # A reviewer should see that the print channel is frozen before
        # deciding, not from a report afterwards.
        "dispatch_plan": remediation.plan_dispatch(trace, base),
    }


@app.post("/api/publication/dispatch")
def publication_dispatch(body: dict) -> dict:
    """Push an approved resolution out, reporting per system.

    The approval gate, the stale-evidence check and the safety gate are all
    still enforced at the planning boundary and are not re-implemented here. A
    commit that refuses refuses everything, because those refusals are
    properties of the resolution rather than of any one channel.
    """
    from sc.estate import remediation

    incident_id = (body or {}).get("incident_id", "")
    scenario_id = (body or {}).get("scenario_id", "")
    entity_id = (body or {}).get("entity_id", "")
    if not (incident_id and scenario_id and entity_id):
        raise HTTPException(
            status_code=400,
            detail="incident_id, scenario_id and entity_id are required")

    base = baseline_mod.get()
    trace = network_tools.trace_dependencies(entity_id)
    return remediation.dispatch(incident_id, scenario_id, trace, base,
                                actor=(body or {}).get("actor", "publisher"))


@app.post("/api/publication/revert")
def publication_revert(body: dict) -> dict:
    """Roll a published resolution back, reporting per system."""
    from sc.estate import remediation

    incident_id = (body or {}).get("incident_id", "")
    scenario_id = (body or {}).get("scenario_id", "")
    entity_id = (body or {}).get("entity_id", "")
    if not (incident_id and scenario_id and entity_id):
        raise HTTPException(
            status_code=400,
            detail="incident_id, scenario_id and entity_id are required")

    base = baseline_mod.get()
    trace = network_tools.trace_dependencies(entity_id)
    return remediation.revert(incident_id, scenario_id, trace, base,
                              reason=(body or {}).get("reason", ""),
                              actor=(body or {}).get("actor", "publisher"))


@app.get("/api/estate")
def estate() -> dict:
    """The systems that feed the retailer, and what each has delivered.

    The manifest is what the estate *is*; the connections are what is reachable
    right now; the arrivals are what has actually landed. Three different
    questions, answered together because the panel asks all three at once.
    """
    from sc.estate import arrivals as estate_arrivals
    from sc.estate import manifest as estate_manifest
    from sc.estate.defects import ALL as ALL_DEFECTS
    from sc.mcp import connections as mcp_connections

    delivered = {row["system_id"]: row for row in estate_arrivals.summary()}
    return {
        "systems": [{**system, **delivered.get(system["id"], {})}
                    for system in estate_manifest.describe()],
        "connections": mcp_connections.all_connections(),
        "defects": [str(d) for d in ALL_DEFECTS],
        "defect_counts": estate_arrivals.counts_by_defect(),
    }


def _publish_topology(change: str, system_id: str, state: str) -> None:
    """Tell every open reader the estate moved.

    A view of the connection records rather than a second account of them: the
    message names what happened and the reader re-reads the map, so a reader
    that missed a message and re-reads the listing arrives at the same picture.
    Carrying the whole estate in the message would be the second account.
    """
    from sc.mcp import connections as mcp_connections

    bus.publish("topology", {
        "change": change,
        "system_id": system_id,
        "state": state,
        "connected": sum(1 for c in mcp_connections.all_connections()
                         if c["state"] == "connected"),
    })


@app.get("/api/estate/servers")
def estate_servers() -> dict:
    """Where each system answers, and what it exposes.

    The addresses are real and separately reachable, which is what makes
    "connect another system" the same operation whether the system ships here
    or somebody else runs it.
    """
    return {"servers": ESTATE_MOUNTED}


@app.get("/api/estate/arrivals")
def estate_arrivals_feed(limit: int = 120) -> dict:
    """What has landed, newest first, with the batch and the system."""
    from sc.estate import arrivals as estate_arrivals

    return {"arrivals": estate_arrivals.recent(limit)}


@app.post("/api/estate/connections")
def estate_connect(body: dict) -> dict:
    """Connect a system by address.

    The handshake is real - `initialize` then `tools/list` - so what comes back
    is what the system says about itself rather than what the URL implies. An
    address nothing answers returns a degraded connection carrying the reason,
    with status 200: an unreachable supplier is a thing to report, not a reason
    to fail the request the operator made.
    """
    from sc.mcp import connections as mcp_connections

    url = (body or {}).get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="a url is required")
    record = mcp_connections.connect_url(
        url,
        connection_id=(body or {}).get("id") or None,
        title=(body or {}).get("title", ""),
        owner=(body or {}).get("owner", ""),
        transport=(body or {}).get("transport", "http"))
    _publish_topology("connected", record["id"], record["state"])
    return record


@app.delete("/api/estate/connections/{connection_id}")
def estate_disconnect(connection_id: str) -> dict:
    """Disconnect a system. What it delivered stays on the record.

    A bitemporal store does not retract history because a socket closed.
    """
    from sc.mcp import connections as mcp_connections

    removed = mcp_connections.disconnect(connection_id)
    if removed:
        _publish_topology("disconnected", connection_id, "")
    return {"removed": removed,
            "connections": mcp_connections.all_connections()}


@app.post("/api/estate/connections/{connection_id}/admit")
def estate_admit(connection_id: str, body: dict) -> dict:
    """Allow a model to call these tools on a connected system.

    Discovery is not admission. Connecting a system records what it can do;
    this is the separate, deliberate act that lets any of it be reached from
    inside a run. Narrowed to what the system actually declared, and never to a
    name a built-in toolset already owns.
    """
    from sc.mcp import connections as mcp_connections

    record = mcp_connections.admit(connection_id, (body or {}).get("tools") or [])
    if record is None:
        raise HTTPException(status_code=404, detail="no such connection")
    return record


@app.get("/api/mcp/calls")
def mcp_calls(limit: int = 60) -> dict:
    """Recent tool calls, newest first, with the transport each one used."""
    from sc.mcp import _runtime

    return {"calls": _runtime.calls(limit), "counts": _runtime.counts()}


@app.post("/api/mcp/transport")
def mcp_transport(body: dict) -> dict:
    """Switch the MCP transport on or off without restarting.

    Read per call rather than cached, so this takes effect on the next tool
    lookup. Useful mid-demo: run the loop in-process, flip it, run it again and
    watch the same calls cross a process boundary.
    """
    import os as _os

    from sc.mcp import client as mcp_client

    _os.environ["USE_MCP"] = "1" if body.get("enabled") else "0"
    return mcp_client.status()


@app.get("/api/graph")
def graph_topology() -> dict:
    """The graph's own structure, read from the compiled LangGraph.

    Exposed so the UI can draw the graph locally. LangGraph Studio renders the
    same thing, but its UI is hosted at smith.langchain.com and needs a sign-in
    - a dependency the demo should not carry into a venue with a restricted
    network. Reading it from the compiled graph rather than hard-coding a
    picture means the diagram cannot drift from what actually runs.
    """
    drawable = graph_build.get_graph().get_graph().to_json()
    return {
        "nodes": [n["id"] for n in drawable["nodes"]],
        "edges": [{"source": e["source"], "target": e["target"],
                   "conditional": bool(e.get("conditional"))}
                  for e in drawable["edges"]],
    }


@app.get("/api/runs/{thread_id}")
def run_state(thread_id: str) -> dict:
    """The checkpointed state of one run, plus what it spent on models.

    The total is summed here rather than stored: ``usage`` is written per node
    so the state reducer can merge concurrent writers, and a stored total would
    be a second figure to keep in step with the first.
    """
    snapshot = graph_build.snapshot(thread_id)
    return {**snapshot, "usage_total": _usage_total(snapshot.get("values") or {})}


def _usage_total(values: dict) -> dict:
    """Add up the per-node model spend the run checkpointed."""
    by_node = [row for row in (values.get("usage") or {}).values()
               if isinstance(row, dict)]
    total = {key: sum(row.get(key) or 0 for row in by_node)
             for key in ("calls", "prompt_tokens", "completion_tokens",
                         "total_tokens", "cache_hits")}
    return {**total,
            "cost_usd": round(sum(row.get("cost_usd") or 0.0 for row in by_node), 6),
            "nodes": len(by_node)}


@app.get("/api/runs/{thread_id}/history")
def run_history(thread_id: str, limit: int = 40) -> dict:
    """Checkpoint history - every step the run passed through."""
    return {"thread_id": thread_id,
            "checkpoints": graph_build.history(thread_id, limit)}


@app.get("/api/approvals/pending")
def pending_approvals() -> dict:
    """Correction cases suspended at the approval gate."""
    rows = db.query(
        "SELECT id, thread_id, severity, title, opened_at FROM incidents"
        " WHERE status = 'AWAITING_APPROVAL' ORDER BY opened_at DESC")
    pending = []
    for row in rows:
        snap = graph_build.snapshot(row["thread_id"])
        if snap["awaiting_approval"]:
            pending.append({**dict(row), "interrupt": snap["interrupt"]})
    return {"pending": pending}


@app.post("/api/approvals/{thread_id}")
def decide(thread_id: str, body: dict) -> dict:
    """Deliver a reviewer's decision into a suspended run.

    APPROVE resumes into publication; REJECT and MODIFY close the run. The
    decision is recorded with DECIDED provenance before the graph acts on it.
    """
    decision = str(body.get("decision", "")).upper()
    if decision not in {"APPROVE", "REJECT", "MODIFY"}:
        raise HTTPException(status_code=400,
                            detail="decision must be APPROVE, REJECT or MODIFY")

    result = graph_build.resume(thread_id, {
        "decision": decision,
        "actor": body.get("actor", "reviewer"),
        "comment": body.get("comment", ""),
        "scenario_id": body.get("scenario_id"),
    })
    bus.publish("approval", {"thread_id": thread_id, "decision": decision,
                             "status": result["status"]})
    return result


# ---------------------------------------------------------------------------
# Publish locks, commit, audit
# ---------------------------------------------------------------------------


@app.get("/api/reservations")
def reservations(incident_id: str | None = None) -> dict:
    return {"reservations": planning.open_reservations(incident_id)}


@app.post("/api/plan/commit")
def commit(body: dict) -> dict:
    result = planning.commit_plan(
        incident_id=body["incident_id"], scenario_id=body["scenario_id"],
        actions=body["delta"], actor=body.get("actor", "reviewer"),
        idempotency_key=body.get("idempotency_key"))
    bus.publish("commit", {"result": result})
    return result


@app.post("/api/plan/rollback")
def do_rollback(body: dict) -> dict:
    return planning.rollback(incident_id=body["incident_id"],
                             scenario_id=body["scenario_id"],
                             reason=body.get("reason", ""),
                             idempotency_key=body.get("idempotency_key"))


@app.get("/api/audit")
def audit_log(limit: int = 200) -> dict:
    rows = db.query("SELECT * FROM audit ORDER BY ts DESC LIMIT ?", (limit,))
    return {"entries": [
        {**dict(r), "detail": db.loads(r["detail"]),
         "provenance": db.loads(r["provenance"])} for r in rows]}


@app.get("/api/facts")
def facts(entity_type: str, as_of: str | None = None,
          as_of_recorded: str | None = None, attr: str | None = None) -> dict:
    """Bitemporal read. ``as_of_recorded`` is what powers 'what did the content
    team know when they wrote this?' in the audit view."""
    from sc.state import store

    valid = datetime.fromisoformat(as_of) if as_of else tape.sim_now()
    # Both time axes default to the simulated clock - see overlay.build.
    recorded = datetime.fromisoformat(as_of_recorded) if as_of_recorded else valid
    found = store.get_many(entity_type, valid, recorded, attr=attr)
    return {"facts": [f.model_dump(mode="json") for f in found],
            "provenance_mix": store.counts_by_provenance()}


@app.get("/api/facts/{fact_id}/lineage")
def fact_lineage(fact_id: str) -> dict:
    from sc.state import store

    return {"lineage": [f.model_dump(mode="json")
                        for f in store.lineage(fact_id)]}


# ---------------------------------------------------------------------------
# Static UI - mounted last so it never shadows an API route
# ---------------------------------------------------------------------------


if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(DIST / "index.html")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        candidate = DIST / path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
else:
    @app.get("/")
    def no_ui() -> dict:
        return {"ok": True,
                "note": "UI not built. Run 'npm run build' in frontend/, "
                        "or use the API directly at /api/health."}
