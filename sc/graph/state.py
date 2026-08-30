"""Graph state.

One dictionary carried through the whole correction run. Two fields use
reducers because the validation step fans out with ``Send`` and several node
invocations write back concurrently - without a reducer the last writer would
win and the other candidates' verdicts would vanish.

Everything here is JSON-serialisable. The checkpointer has to persist it after
every step, and a run must survive the process being killed and restarted,
which rules out holding live objects in state - no enums, no datetimes, no
pydantic models: dump to primitives at the node boundary.
"""

from __future__ import annotations

import operator
import time
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, TypedDict


def _merge_dicts(left: dict, right: dict) -> dict:
    return {**(left or {}), **(right or {})}


# A re-plan runs the same thread a second time. Every additive field would
# otherwise carry revision 1's contents into revision 2 - twelve validated
# candidates where there are six, and a citation list that doubles on every
# pass. The reducers therefore accept an explicit reset marker as the first
# element of an update, which is the only way to clear an accumulating field in
# LangGraph: returning [] from a node appends nothing, it does not empty.
RESET = "__reset__"


def resettable_add(left: list, right: list) -> list:
    """Append, unless the update opens with RESET - then replace."""
    if right and right[0] == RESET:
        return list(right[1:])
    return [*(left or []), *(right or [])]


# Two sources disagreeing is not settled by a third value landing on the same
# attribute; only an explicit resolution closes it. Letting a later correction
# quietly supersede the conflict would hide exactly what POL-002 exists to
# surface, so this kind is exempt from supersession.
_NEVER_SUPERSEDED = frozenset({"SOURCE_CONFLICT"})

# A withdrawal retracts whatever the document asserted, however the original
# notice happened to be classified - the day-10 kettle notice is a
# SPEC_CORRECTION and the day-13 withdrawal that clears it is not. Every other
# resolution has to be about the same kind of thing it clears.
_WHOLESALE_RESOLVERS = frozenset({"DOC_WITHDRAWN"})


def _detected_at(signal: dict) -> datetime:
    """Signal timestamp as a comparable naive-UTC datetime.

    String comparison is only correct while every timestamp is written in the
    same shape and the same zone. The tape carries both, so it is not: a
    date-only value sorts before every full timestamp on the same day, and an
    explicit ``+01:00`` offset sorts after a ``Z`` it actually precedes.
    """
    raw = signal.get("detected_at")
    if isinstance(raw, datetime):
        parsed = raw
    else:
        try:
            parsed = datetime.fromisoformat(str(raw or "").strip())
        except ValueError:
            return datetime.min  # unparseable: never wins a comparison
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _entities(signal: dict) -> set[str]:
    return {str(e) for e in signal.get("entities") or [] if e}


def _paths(signal: dict) -> set[str]:
    return {str(p) for p in signal.get("attribute_paths") or [] if p}


def _same_subject(left: dict, right: dict) -> bool:
    """Do two signals talk about the same entity and the same attribute?

    A signal naming no attribute path is about the entity wholesale rather than
    about nothing: "dimensions under review pending a tooling audit" has no path
    in ``attr_defs`` to name, and the withdrawal that clears it has none either.
    Those still have to match, so an empty path set matches anything on a shared
    entity.
    """
    if not _entities(left) & _entities(right):
        return False
    left_paths, right_paths = _paths(left), _paths(right)
    return not left_paths or not right_paths or bool(left_paths & right_paths)


def _resolves(resolver: dict, signal: dict) -> bool:
    kind_ok = (resolver.get("kind") == signal.get("kind")
               or str(resolver.get("kind") or "") in _WHOLESALE_RESOLVERS)
    return (kind_ok
            and _same_subject(resolver, signal)
            and _detected_at(resolver) >= _detected_at(signal))


def _supersedes(later: dict, later_pos: int,
                earlier: dict, earlier_pos: int) -> bool:
    kind = str(later.get("kind") or "")
    if kind != str(earlier.get("kind") or "") or kind in _NEVER_SUPERSEDED:
        return False
    if not _same_subject(later, earlier):
        return False
    # Position breaks timestamp ties, so exactly one signal per subject
    # survives instead of a pair cancelling each other out.
    return (_detected_at(later), later_pos) > (_detected_at(earlier), earlier_pos)


def merge_signals(left: list[dict], right: list[dict]) -> list[dict]:
    """Combine signal lists, retiring the ones a later notice settles.

    ``monitor`` derives signals from the facts in force; ``extract`` appends
    what it reads out of supplier documents and correspondence. A plain
    concatenation shows a provisional notice *and* its withdrawal as two live
    corrections, and shows the 65 W notice next to the "Max only" clarification
    that replaces it - a settled question presented as two open ones.

    Three rules, applied in order:

    * identical ids collapse - ``monitor`` derives from the facts in force so
      that it is re-runnable, which means the same signal legitimately arrives
      twice within a run; the later copy wins, in the earlier one's position;
    * a signal marked ``resolves_issue`` retires what it clears and is not
      itself an open issue - a withdrawal is evidence, not a correction;
    * otherwise the latest signal on a subject supersedes its predecessors.

    A subject is kind plus a shared entity plus a shared attribute path: two
    corrections to ``VAR-01B.specs.power_w`` are one open issue, but a
    correction to ``specs.noise_db`` on the same variant is another.
    """
    if right and right[0] == RESET:
        left, right = [], list(right[1:])

    combined = [s for s in [*(left or []), *(right or [])] if isinstance(s, dict)]

    unique: list[dict] = []
    seen: dict[str, int] = {}
    for signal in combined:
        sid = str(signal.get("id") or "")
        if sid and sid in seen:
            unique[seen[sid]] = signal
            continue
        if sid:
            seen[sid] = len(unique)
        unique.append(signal)

    resolvers = [s for s in unique if s.get("resolves_issue")]
    others = [(pos, s) for pos, s in enumerate(unique)
              if not s.get("resolves_issue")]

    out: list[dict] = []
    for pos, signal in others:
        if any(_resolves(r, signal) for r in resolvers):
            continue
        if any(_supersedes(other, other_pos, signal, pos)
               for other_pos, other in others if other_pos != pos):
            continue
        out.append(signal)
    return out


class FactoryState(TypedDict, total=False):
    """State of one correction run.

    A run is scoped to an incident, and an incident is scoped to a LangGraph
    thread - so resuming a thread resumes exactly one correction case.
    """

    # --- identity ----------------------------------------------------------
    run_id: str
    incident_id: str
    thread_id: str

    # --- time --------------------------------------------------------------
    # Both axes of the bitemporal read, pinned once at the start of the run.
    # Pinning matters: a recommendation must be reproducible against the
    # evidence it actually had, not against facts that arrived while it was
    # still thinking.
    as_of: str
    as_of_recorded: str

    # --- case scoping ------------------------------------------------------
    # A correction case is one PRODUCT - the unit the publish lock is taken on
    # and therefore the unit a reviewer commits. Set by the caller to pick a
    # case, or asked for by `monitor` (worst first) when the caller named none.
    # `scope_case` settles it and narrows `signals` to it, after `extract`: a
    # correction still sitting in an unread document is not yet a fact, so
    # `monitor` cannot see the case it belongs to.
    case_id: str
    # The chosen case and everything else still open, both without their signal
    # bodies: the other cases are shown so a correction never goes invisible,
    # not re-decided here, and state is checkpointed after every step.
    case: dict
    other_open_cases: list[dict]

    # --- monitor / extract -------------------------------------------------
    event_ids: list[str]
    signals: Annotated[list[dict], merge_signals]
    corrections: list[dict]

    # --- triage ------------------------------------------------------------
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    material: bool
    triage_reason: str

    # --- impact analysis ---------------------------------------------------
    # The blast radius, carrying its own totals - the measured figures behind
    # the materiality call. Written by monitor/triage and read by everything
    # downstream, so it is the one place the scope of a correction is stated.
    affected: dict            # AffectedScope + totals
    causal_chain: list[dict]
    root_causes: list[str]
    symptoms: list[str]
    prior_incidents: list[dict]
    citations: Annotated[list[dict], resettable_add]
    # What the scope resolver asked the evidence desk for, and what came back -
    # refusals included. This is the audit trail for the one step where a model
    # chooses an action, so it is state rather than a log line.
    evidence_log: list[dict]

    # --- scope resolution --------------------------------------------------
    # Competing readings of who the correction applies to, and the one the
    # deterministic ranking settled on. The model argues for a reading; it never
    # picks the winner.
    scope_candidates: list[dict]  # ChangeScope dumps
    chosen_scope: dict

    # --- candidates and validation ----------------------------------------
    scenarios: list[dict]
    rejected_actions: list[dict]
    sim_results: Annotated[list[dict], resettable_add]
    ranked: list[dict]
    weights: dict

    # --- propagation and content ------------------------------------------
    # Written by the propagate/regenerate leg. `claim_flags` is advisory unless
    # the deterministic CLAIM_RULES table agrees; `final_validation` is the full
    # engine pass over the chosen change set including the proposed copy, and is
    # what the recommendation quotes.
    claim_flags: list[dict]
    regenerated: list[dict]
    enrichments: list[dict]
    final_validation: dict

    # --- recommendation and decision --------------------------------------
    recommendation: dict
    approval: dict
    commit_result: dict

    # --- branch outputs ----------------------------------------------------
    # Each of these is written by one branch node and is absent on runs that
    # did not take that branch. Their presence in a snapshot is how the UI
    # knows which route this correction took.
    precedent: dict            # apply_precedent - guidance from a prior incident
    clarification: dict        # supplier_clarification - the question to ask
    blocked: dict              # blocked_review - what binds, for a human
    publish_retries: int       # guards the one cycle in the graph

    # --- re-planning -------------------------------------------------------
    # A revised plan is not a new plan. The brief is explicit that new evidence
    # must force "targeted re-planning rather than a full restart", so a
    # revision keeps the thread, carries the superseded recommendation and the
    # options it beat, and reports what moved and why.
    revision: int
    # Latch. `monitor` clears the accumulating fields exactly once per
    # revision; without it a resumed thread would wipe its own results.
    revision_started: bool
    replan_reason: str
    previous_recommendation: dict
    previous_ranked: list[dict]
    plan_diff: dict

    # --- bookkeeping -------------------------------------------------------
    status: str
    trace: Annotated[list[dict], operator.add]
    usage: Annotated[dict, _merge_dicts]
    errors: Annotated[list[str], operator.add]


# The graph, the UI and the tests all spell this name; keeping the alias means
# the rename is a one-line change for anything that has not caught up yet.
RecoveryState = FactoryState


class ScenarioTask(TypedDict):
    """Payload for one fan-out branch of the validation step.

    ``scenario`` carries a ChangeSet dump - plain JSON, because a ``Send``
    payload is checkpointed like any other piece of state.
    """

    run_id: str
    as_of: str
    as_of_recorded: str
    scenario: dict


# When the previous trace line was written. A node emits a line as each piece
# of its work lands, so the gap between two lines is what the work between them
# cost - the only timing available without wrapping every node, and enough to
# answer "which node is slow" once the lines are grouped by node.
_last_step = time.perf_counter()


def step(node: str, summary: str, **detail: Any) -> dict:
    """One line of the run trace, with the time it took to reach it.

    The trace is what the Audit tab renders and what makes the graph's
    reasoning inspectable without LangGraph Studio - the demo must not depend
    on an external service being reachable.

    ``elapsed_ms`` is the gap since the previous line rather than a duration a
    node measured for itself, so the first line of a node also carries the tail
    of the one before it, and two fan-out branches writing at once each report
    the gap to whichever wrote last. It is a plain float, like everything else
    here: state is checkpointed with msgpack after every step.
    """
    global _last_step
    now = time.perf_counter()
    elapsed_ms = (now - _last_step) * 1000
    _last_step = now
    return {"node": node, "summary": summary,
            "elapsed_ms": round(elapsed_ms, 1), "detail": detail}
