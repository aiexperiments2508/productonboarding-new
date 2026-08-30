"""Graph assembly.

    monitor -> extract -> scope_case
                            |
                            v
                          triage --(immaterial)--> ack_and_park -> close
                            |
                        (material)
                            v
                     resolve_scope --(sources disagree)--> supplier_clarification
                            |      --(seen before)-------> apply_precedent
                            v                                    |
                     plan_candidates <---------------------------+
                            |
                            |  Send() fan-out, one branch per candidate reading
                            v
                       validate_one  (concurrent)
                            v
                          rank --(nothing publishable)--> blocked_review
                            |                                   |
                            v                                   |
    propagate -> scan_claims -> regenerate -> enrich -> validate_final
                            |                                   |
                            v                                   v
                         recommend <-----------------------------
                            v
                     request_approval
                        |        |
                   approve     reject
                        v        v
                    publish     close
                        v
                 verify_publish --(conflict or stale)--> plan_candidates
                        v
                      close

The approval step is a genuine ``interrupt()``: the graph suspends, the
checkpoint is written, and the process may be killed and restarted before a
reviewer decides. That is what makes it an approval gate rather than a modal
dialog, and it is also how the brief's "recover safely from partial execution"
requirement is met - a resumed thread continues from the last completed step
rather than starting over.

The one cycle is ``verify_publish -> plan_candidates``, bounded by
``branches.MAX_PUBLISH_RETRIES``.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from sc import db
from sc.graph import branches, nodes
from sc.graph.state import FactoryState


def _route_after_triage(state: FactoryState) -> str:
    return "ack_and_park" if branches.is_immaterial(state) else "resolve_scope"


def _route_after_scope(state: FactoryState) -> str:
    """Which exception, if any, this correction needs before it can be planned.

    Order matters and is not arbitrary. A disagreement between two supplier
    documents - or a scope no reading on file can settle - is a fact about
    *this* correction and produces a question a human has to send. A
    resemblance to a past incident is context for the writer. When both hold,
    the question outranks the reading material.
    """
    if branches.sources_conflict(state):
        return "supplier_clarification"
    if branches.has_precedent(state):
        return "apply_precedent"
    return "plan_candidates"


def _route_after_candidates(state: FactoryState):
    """Fan out one validation per candidate reading, or go straight to rank.

    Returning an empty ``Send`` list would leave the superstep with no tasks
    and strand the run short of ``close``, so a correction that produced no
    candidate at all is routed onward instead: ``rank`` scores nothing,
    ``nothing_publishable`` is true, and the reviewer gets the empty result as
    a finding rather than as a graph that stopped.
    """
    if not state.get("scenarios"):
        return "rank"
    return nodes.fan_out_validations(state)


def _route_after_rank(state: FactoryState) -> str:
    return ("blocked_review" if branches.nothing_publishable(state)
            else "propagate")


def _route_after_recommend(state: FactoryState) -> str:
    return "request_approval" if state.get("recommendation") else "close"


def _route_after_verify(state: FactoryState) -> str:
    """A publish that lost a race, or was overtaken, still has a plan left.

    Read from the status rather than from ``publish_conflicted``: by the time
    this runs the retry has been spent, and the predicate would be answering
    for the next attempt instead of this one.
    """
    return ("plan_candidates"
            if state.get("status") in branches.REPLANNING_STATUSES else "close")


def build_graph() -> StateGraph:
    """The uncompiled graph. Shared by the app and by LangGraph Studio.

    LangGraph Studio imports this function and nothing else, so this is where
    the graph's own preconditions have to be met - without it Studio runs
    against a database with no schema and finds nothing to do.
    """
    from sc import bootstrap

    bootstrap.ensure_ready()

    graph = StateGraph(FactoryState)

    graph.add_node("monitor", nodes.monitor)
    graph.add_node("extract", nodes.extract)
    graph.add_node("scope_case", nodes.scope_case)
    graph.add_node("triage", nodes.triage)
    graph.add_node("resolve_scope", nodes.resolve_scope)
    graph.add_node("plan_candidates", nodes.plan_candidates)
    graph.add_node("validate_one", nodes.validate_one)
    graph.add_node("rank", nodes.rank)
    graph.add_node("propagate", nodes.propagate)
    graph.add_node("scan_claims", nodes.scan_claims)
    graph.add_node("regenerate", nodes.regenerate)
    graph.add_node("enrich", nodes.enrich)
    graph.add_node("validate_final", nodes.validate_final)
    graph.add_node("recommend", nodes.recommend)
    # request_approval routes with Command(goto=...) rather than a static edge,
    # because the destination depends on the reviewer's decision. Declaring the
    # possible destinations does not change execution - it tells the renderer
    # where the node can go, so Studio draws the approve/reject branches
    # instead of showing the approval step as a dead end.
    graph.add_node("request_approval", nodes.request_approval,
                   destinations=("publish", "close"))
    graph.add_node("publish", nodes.publish)
    graph.add_node("ack_and_park", nodes.ack_and_park)
    graph.add_node("close", nodes.close)

    # Branch nodes. None of these runs on every correction - that is the point.
    graph.add_node("apply_precedent", branches.apply_precedent)
    graph.add_node("supplier_clarification", branches.supplier_clarification)
    graph.add_node("blocked_review", branches.blocked_review)
    graph.add_node("verify_publish", branches.verify_publish)

    graph.add_edge(START, "monitor")
    graph.add_edge("monitor", "extract")
    # The case filter goes between reading and acting, not before reading. A
    # correction in an unread document is not yet a fact, so a filter ahead of
    # extract has nothing to filter and everything extract then reads arrives
    # behind it unscoped.
    graph.add_edge("extract", "scope_case")
    graph.add_edge("scope_case", "triage")

    graph.add_conditional_edges("triage", _route_after_triage,
                                ["resolve_scope", "ack_and_park"])
    # Both exceptions are additive. A supplier who has been asked a question
    # has not answered it yet, and the wrong figure is live on six channels
    # meanwhile; a postmortem is context for the writer. Either way the
    # correction still gets planned.
    graph.add_conditional_edges("resolve_scope", _route_after_scope,
                                ["supplier_clarification", "apply_precedent",
                                 "plan_candidates"])
    graph.add_edge("apply_precedent", "plan_candidates")
    graph.add_edge("supplier_clarification", "plan_candidates")

    # Send-based fan-out. Every branch writes to sim_results, which has an
    # additive reducer, so the concurrent verdicts accumulate instead of
    # overwriting one another.
    graph.add_conditional_edges("plan_candidates", _route_after_candidates,
                                ["validate_one", "rank"])
    graph.add_edge("validate_one", "rank")
    graph.add_conditional_edges("rank", _route_after_rank,
                                ["propagate", "blocked_review"])

    # The content leg: the lineage walk made executable, then the sentences the
    # record cannot settle, then a full validation pass over the whole thing -
    # so the figures the reviewer approves come from the change set they are
    # actually approving.
    graph.add_edge("propagate", "scan_claims")
    graph.add_edge("scan_claims", "regenerate")
    graph.add_edge("regenerate", "enrich")
    graph.add_edge("enrich", "validate_final")
    graph.add_edge("validate_final", "recommend")
    # Nothing publishes. The reviewer still needs a decision to take - which
    # channels do not go live, and what binds them - so this informs the
    # recommendation rather than replacing it.
    graph.add_edge("blocked_review", "recommend")

    graph.add_conditional_edges("recommend", _route_after_recommend,
                                ["request_approval", "close"])
    # request_approval returns a Command naming its own next node, so no static
    # edge is declared out of it.
    graph.add_edge("publish", "verify_publish")
    # The one cycle in the graph. A publish can lose its locks to another run,
    # or find a newer source version in force, while its approval was pending;
    # planning again against what is actually true is a better answer than
    # reporting failure.
    graph.add_conditional_edges("verify_publish", _route_after_verify,
                                ["plan_candidates", "close"])
    graph.add_edge("ack_and_park", "close")
    graph.add_edge("close", END)

    return graph


# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------


def checkpoint_path() -> Path:
    """Checkpoints live beside the application database, not inside it.

    Sharing one file would put LangGraph's schema migrations in the same
    database as the audit ledger, and a checkpoint reset would risk the
    evidence. Separate files keep "wipe the run history" from meaning "wipe the
    audit trail".
    """
    return db.db_path().with_suffix(".checkpoints.db")


def make_checkpointer() -> SqliteSaver:
    path = checkpoint_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: uvicorn runs handlers in a threadpool and the
    # saver is shared across them.
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return SqliteSaver(conn)


_compiled: Any = None
_checkpoint_conn: sqlite3.Connection | None = None


def get_graph():
    """Process-wide compiled graph with its checkpointer attached."""
    global _compiled, _checkpoint_conn
    if _compiled is None:
        saver = make_checkpointer()
        _checkpoint_conn = saver.conn
        _compiled = build_graph().compile(checkpointer=saver)
    return _compiled


def reset_graph() -> None:
    """Drop the compiled graph and release the checkpoint file.

    Closing the connection matters on Windows, where an open handle blocks the
    file from being deleted - a test that resets between runs would otherwise
    fail on permissions rather than on anything it meant to check.
    """
    global _compiled, _checkpoint_conn
    _compiled = None
    if _checkpoint_conn is not None:
        try:
            _checkpoint_conn.close()
        except Exception:
            pass
        _checkpoint_conn = None


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def config_for(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id},
            "recursion_limit": int(os.environ.get("GRAPH_RECURSION_LIMIT", "50"))}


def _initial_state(incident_id: str, thread_id: str, weights: dict | None,
                   case_id: str | None) -> FactoryState:
    """The run's opening state.

    ``case_id`` is only written when the caller named one. Writing an empty
    string instead would be indistinguishable from "monitor looked and found
    nothing open", and monitor uses that distinction to decide whether it may
    pick a case for itself.
    """
    initial: FactoryState = {
        "incident_id": incident_id, "thread_id": thread_id,
        "weights": weights or {}, "status": "STARTING",
    }
    if case_id:
        initial["case_id"] = case_id
    return initial


def start_run(incident_id: str, thread_id: str, weights: dict | None = None,
              case_id: str | None = None) -> dict:
    """Run until the graph either finishes or stops for approval."""
    graph = get_graph()
    graph.invoke(_initial_state(incident_id, thread_id, weights, case_id),
                 config_for(thread_id))
    return snapshot(thread_id)


def stream_run(incident_id: str, thread_id: str, weights: dict | None = None,
               case_id: str | None = None) -> Iterator[dict]:
    """Same run, yielding each node's update as it lands.

    This is what the UI's live trace consumes - the graph's own progress,
    rather than a progress bar guessing at it.
    """
    graph = get_graph()
    for chunk in graph.stream(_initial_state(incident_id, thread_id, weights,
                                             case_id),
                              config_for(thread_id),
                              stream_mode="updates"):
        for node, update in chunk.items():
            yield {"node": node, "update": _jsonable(update)}


class ReplanRefused(Exception):
    """A revision was asked for where there is nothing to revise."""


def _withdraw_pending(thread_id: str, reason: str) -> None:
    """Retire an approval the evidence has overtaken.

    Delivered as a real REJECT through the same interrupt a reviewer uses, so
    it lands in the audit ledger with DECIDED provenance and an actor. The
    alternative - clearing the interrupt through update_state - would leave a
    recommendation that simply vanished, which is the one thing an audit trail
    exists to prevent.
    """
    from langgraph.types import Command

    graph = get_graph()
    graph.invoke(
        Command(resume={
            "decision": "REJECT",
            "actor": "system",
            "comment": ("superseded before decision - new evidence arrived: "
                        + (reason or "new evidence arrived")),
        }),
        config_for(thread_id),
    )


def _replan_input(reason: str, case_id: str = "") -> dict:
    """The markers that turn the next pass into a revision.

    The case is carried forward explicitly. A revision that re-picked would walk
    the incident onto whichever product looked worst this minute, and re-planning
    on the same thread exists precisely so the decision stays the same one.
    """
    return {
        "replan_reason": reason or "new evidence arrived",
        "revision_started": False,
        "case_id": case_id,
        "status": "REPLANNING",
    }


def replan_run(thread_id: str, reason: str = "") -> dict:
    """Revise an existing plan against evidence that arrived after it.

    The brief is specific that new evidence must force "targeted re-planning
    rather than a full restart", so this deliberately re-enters the SAME
    thread. Three things follow from that, and they are the whole point:

    * the checkpoint history stays continuous, so the revision is visibly a
      continuation of the incident rather than a second unrelated incident;
    * the superseded recommendation and the options it beat are still in
      state, so `monitor` can carry them forward and `rank` can compute what
      moved;
    * the incident id, and therefore the audit trail, is unchanged.

    A run suspended at the approval gate is the *expected* case, not an error:
    the demo's clarification lands after the first plan is prepared, which is
    precisely when a reviewer is sitting in front of it. The pending approval
    is withdrawn first - recorded as a decision, by "system", with the reason -
    because a recommendation whose evidence has changed is not one anybody
    should still be able to approve. Silently leaving the gate open would let a
    reviewer publish content the system already knows is stale.
    """
    graph = get_graph()
    current = snapshot(thread_id)
    values = current.get("values") or {}

    if not values:
        raise ReplanRefused(f"thread {thread_id} has no run to revise")
    if not values.get("recommendation") and not values.get("previous_recommendation"):
        raise ReplanRefused("there is no recommendation to revise yet")

    if current.get("awaiting_approval"):
        _withdraw_pending(thread_id, reason)

    # Passed as input, not through update_state. `invoke(None, ...)` resumes a
    # suspended thread; a finished one has nothing to resume and would return
    # immediately. Invoking WITH input on a finished thread is what starts a
    # fresh pass from START while keeping the thread's accumulated state - which
    # is exactly the "same incident, next revision" semantics wanted here.
    # These three fields have no reducer, so the input overwrites them.
    graph.invoke(_replan_input(reason, str(values.get("case_id") or "")),
                 config_for(thread_id))
    return snapshot(thread_id)


def stream_replan(thread_id: str, reason: str = "") -> Iterator[dict]:
    """Same revision, streamed node by node."""
    graph = get_graph()
    current = snapshot(thread_id)
    values = current.get("values") or {}
    if not values:
        raise ReplanRefused(f"thread {thread_id} has no run to revise")
    if current.get("awaiting_approval"):
        _withdraw_pending(thread_id, reason)

    for chunk in graph.stream(_replan_input(reason,
                                            str(values.get("case_id") or "")),
                              config_for(thread_id), stream_mode="updates"):
        for node, update in chunk.items():
            yield {"node": node, "update": _jsonable(update)}


def resume(thread_id: str, decision: dict) -> dict:
    """Deliver a reviewer's decision into a suspended run."""
    from langgraph.types import Command

    graph = get_graph()
    graph.invoke(Command(resume=decision), config_for(thread_id))
    return snapshot(thread_id)


def stream_resume(thread_id: str, decision: dict) -> Iterator[dict]:
    from langgraph.types import Command

    graph = get_graph()
    for chunk in graph.stream(Command(resume=decision), config_for(thread_id),
                              stream_mode="updates"):
        for node, update in chunk.items():
            yield {"node": node, "update": _jsonable(update)}


def snapshot(thread_id: str) -> dict:
    """Current state of a thread, including whether it is waiting on a human."""
    graph = get_graph()
    state = graph.get_state(config_for(thread_id))
    values = dict(state.values or {})

    pending = None
    for task in state.tasks or ():
        for item in getattr(task, "interrupts", ()) or ():
            pending = _jsonable(getattr(item, "value", None))

    return {
        "thread_id": thread_id,
        "status": values.get("status"),
        "awaiting_approval": pending is not None,
        "interrupt": pending,
        "next": list(state.next or ()),
        "values": _jsonable(values),
    }


def history(thread_id: str, limit: int = 40) -> list[dict]:
    """Checkpoint history - the time-travel view of a run."""
    graph = get_graph()
    out = []
    for state in graph.get_state_history(config_for(thread_id)):
        out.append({
            "checkpoint_id": state.config.get("configurable", {}).get("checkpoint_id"),
            "next": list(state.next or ()),
            "status": (state.values or {}).get("status"),
            "created_at": state.created_at,
        })
        if len(out) >= limit:
            break
    return out


def _jsonable(value):
    """Coerce state to something the API can serialise.

    Graph state is meant to be JSON already, but a node that returns a Pydantic
    model or a date should not take the whole response down.
    """
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
