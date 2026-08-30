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
    global _clock_task
    from sc import bootstrap

    bootstrap.ensure_ready()
    _clock_task = asyncio.create_task(tape.run_clock(_on_events))


@app.on_event("shutdown")
async def shutdown() -> None:
    if _clock_task is not None:
        _clock_task.cancel()
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
    """The toolset partition, read from the registry that defines it."""
    from sc.mcp import client as mcp_client
    from sc.mcp import registry as mcp_registry
    from sc.mcp import _runtime

    return {
        "servers": mcp_registry.describe(),
        "transport": mcp_client.status(),
        "counts": _runtime.counts(),
    }


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
