"""Validation and publication tools.

Everything that changes state lives here, and every function that changes state
carries the same controls:

*   **Idempotency** - a replayed call returns its original result instead of
    acting twice. The event plane is at-least-once, so this is not optional.
*   **Publish locks** - a claim on one (channel, product) for one batch date.
    SOFT holds are advisory and expire; HARD holds are exclusive and the
    database enforces it with a partial unique index.
*   **Approval gating** - ``commit_plan`` refuses to act without a recorded
    APPROVE decision, so no graph path can publish a resolution the reviewer
    never saw.
*   **Fail-closed gates** - a publish is re-validated against what is in force
    at the instant it is written. A resolution built on a superseded document
    version, or one that leaves a safety or allergen declaration open, is
    refused rather than pushed.

The conflict story is deliberately declarative. Rather than taking a lock and
hoping every code path remembers to, a second conflicting HARD reservation
fails at the database with an integrity error, surfaced as a
``publish_conflict`` violation. Two runs republishing the same product to the
same channel on the same day is impossible, not merely unlikely.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import date, datetime, timedelta

from sc import db
from sc.contracts import (
    ActionKind,
    ApprovalDecision,
    ChangeSet,
    ObjectiveWeights,
    Provenance,
    ProvenanceKind,
    ReservationStatus,
    ScopeLevel,
    SourceRef,
    Violation,
    ViolationSeverity,
)
from sc.sim.engine import simulate
# The validator's own ordering of source-document versions. Shared rather than
# re-implemented: the gate below and the engine must agree on what "later" means.
from sc.sim.engine import _rank as version_rank
# The two constraints that stop a publish outright. Everything else can be
# accepted with its reason on the record; a wrong allergen cannot. Shared with
# the engine rather than restated, so the gate below and the KPI that counts
# safety flags bind on the same list.
from sc.sim.engine import SAFETY_CONSTRAINTS as SAFETY_GATE
from sc.state import baseline as baseline_mod
from sc.state import overlay as overlay_mod
from sc.state import store
from sc.state.baseline import Baseline

SOFT_HOLD_MINUTES = 30

# A publish lock is a boolean claim on a (channel, product) batch, not a
# quantity; the column stays for schema continuity.
LOCK_QTY = 1.0

# An infeasible resolution takes a flat hit rather than a proportional one. An
# unpublishable option is not a cheap option, it is not an option.
INFEASIBLE_PENALTY = 0.35

# Evidence confidence is compared in bands of a tenth. It is the strength of an
# argument about scope, not a measurement, and ordering 0.66 ahead of 0.65 would
# read a precision into it that is not there.
EVIDENCE_BAND = 0.1


def _sim_now() -> datetime:
    from sc.replay import tape

    return tape.sim_now()


def _now() -> datetime:
    return datetime.now()


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def _remembered(key: str) -> dict | None:
    row = db.one("SELECT result FROM idempotency_keys WHERE key = ?", (key,))
    return db.loads(row["result"]) if row else None


def _remember(key: str, tool: str, result: dict, conn=None) -> None:
    c = conn or db.connect()
    c.execute(
        "INSERT OR IGNORE INTO idempotency_keys (key, tool, created_at, result)"
        " VALUES (?,?,?,?)",
        (key, tool, _now().isoformat(), db.dumps(result)),
    )
    if conn is None:
        c.commit()


def idempotent(tool: str):
    """Decorator: short-circuit a repeated call with its first result."""
    def wrap(fn):
        def inner(*args, idempotency_key: str | None = None, **kwargs):
            if idempotency_key:
                prior = _remembered(idempotency_key)
                if prior is not None:
                    return {**prior, "idempotent_replay": True}
            result = fn(*args, **kwargs)
            if idempotency_key and not result.get("error"):
                _remember(idempotency_key, tool, result)
            return result
        inner.__name__ = fn.__name__
        inner.__doc__ = fn.__doc__
        return inner
    return wrap


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def audit(actor: str, action: str, entity_type: str, entity_id: str,
          detail: dict | None = None, provenance: Provenance | None = None,
          conn=None) -> str:
    entry_id = _uid("AUD")
    c = conn or db.connect()
    c.execute(
        "INSERT INTO audit (id, ts, actor, action, entity_type, entity_id,"
        " detail, provenance) VALUES (?,?,?,?,?,?,?,?)",
        (entry_id, _now().isoformat(), actor, action, entity_type, entity_id,
         db.dumps(detail or {}),
         db.dumps(provenance or Provenance(kind=ProvenanceKind.COMMITTED))),
    )
    if conn is None:
        c.commit()
    return entry_id


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _change_set(scenario_id: str, delta: dict | list) -> ChangeSet:
    """Accept a whole resolution document or the bare action list it holds.

    The graph hands over the ``ChangeSet`` it validated; the MCP surface hands
    over the actions a reviewer approved. Both name the same publish.
    """
    if isinstance(delta, dict):
        return ChangeSet.model_validate(delta)
    return ChangeSet(id=scenario_id, actions=delta)


def run_scenario(delta: dict, as_of: str | None = None,
                 as_of_recorded: str | None = None) -> dict:
    """Validate one candidate resolution. Read-only, so no idempotency needed.

    This is the only way any number enters the system. The graph may choose
    *what* to validate; it never decides what the result is.

    ``as_of_recorded`` reads the record as it stood at an earlier instant,
    which is how a resolution is checked against what was known when it was
    proposed rather than against corrections that landed since.
    """
    base = baseline_mod.get()
    change_set = ChangeSet.model_validate(delta)

    valid = datetime.fromisoformat(as_of) if as_of else _sim_now()
    recorded = datetime.fromisoformat(as_of_recorded) if as_of_recorded else None
    ov = overlay_mod.build(valid, recorded)

    result = simulate(base, change_set, ov)

    return {
        "delta_id": change_set.id,
        "feasible": result.feasible,
        "kpis": result.kpis.model_dump(mode="json"),
        "violations": [v.model_dump(mode="json") for v in result.violations],
        "trace_hash": result.trace_hash,
        "runtime_ms": result.runtime_ms,
        "scope": {"level": str(change_set.scope.level),
                  "entities": sorted(change_set.scope.entities)},
        "corrections": overlay_mod.summarise(ov),
    }


def compare_scenarios(deltas: list[dict], weights: dict | None = None,
                      as_of: str | None = None) -> dict:
    """Validate several candidates and rank them.

    Ranking is a weighted score plus a Pareto front, so an option that is
    dominated on every dimension is visibly dominated rather than merely
    ranked lower.

    Each row is one candidate with its verdict inlined - the reviewer's table
    renders a row from exactly this, so it carries the change set it priced and
    a name and summary the reviewer can argue between, not just an id.
    """
    base = baseline_mod.get()
    rows: list[dict] = []
    for delta in deltas:
        change_set = ChangeSet.model_validate(delta)
        result = run_scenario(delta, as_of=as_of)
        rows.append({
            "scenario_id": change_set.id,
            "name": _scenario_name(base, change_set),
            "summary": _scenario_summary(change_set, result["kpis"]),
            "delta": change_set.model_dump(mode="json"),
            **result,
        })

    scored = _score(rows, weights or {})
    return {"scenarios": scored,
            "pareto": [s["scenario_id"] for s in scored if s["pareto_optimal"]]}


def _scenario_name(base: Baseline, change_set: ChangeSet) -> str:
    """Name a reading after the variants it moves, not after its id.

    "AeroPure 300 Max only" is the sentence a reviewer is choosing between;
    ``D-4f19c2`` is not.
    """
    scope = change_set.scope
    entities = sorted(scope.entities)
    if scope.level is ScopeLevel.ALL:
        products = sorted({base.products[base.product_of_variant[e]].name
                           for e in entities if e in base.variants})
        return f"Every variant of {', '.join(products)}" if products \
            else "Every variant"
    names = [base.variants[e].name for e in entities if e in base.variants]
    return f"{', '.join(names)} only" if names \
        else f"{scope.level} reading of the correction"


def _scenario_summary(change_set: ChangeSet, kpis: dict) -> str:
    """One line about a candidate. Every figure in it is the validator's."""
    return (f"{kpis['fields_affected']} field(s) on "
            f"{len(change_set.scope.entities)} variant(s) via "
            f"{len(change_set.actions)} action(s); "
            f"{kpis['channels_blocked']} channel(s) blocked, "
            f"{kpis['listings_ready_pct']}% of affected listings publishable")


def _scope_of(row: dict) -> dict:
    """The reading a row was priced under.

    The change set's own scope first: it carries the confidence the evidence
    earned. ``run_scenario`` echoes a scope back without one, which is enough to
    measure width but not enough to weigh evidence.
    """
    return (row.get("delta") or {}).get("scope") or row.get("scope") or {}


def _evidence_band(row: dict) -> int:
    try:
        confidence = float(_scope_of(row).get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return int(round(max(0.0, min(1.0, confidence)) / EVIDENCE_BAND))


def _scope_width(row: dict) -> int:
    return len(_scope_of(row).get("entities") or [])


def _score(results: list[dict], weights: dict) -> list[dict]:
    """Rank resolutions. Safety is a pre-sort, not a weight.

    ``ObjectiveWeights`` has no safety term on purpose: a resolution with an
    open safety flag never outranks one without, whatever the reviewer sets the
    weights to. The weights only order the options that are equally safe.

    The order is safety, then feasibility, then the evidence behind the reading,
    then the narrowest scope that evidence supports. Evidence outranks the
    weighted score deliberately: readiness and precision are properties of a
    resolution, and letting them settle *which reading of the correction is
    true* let a narrow reading nobody could defend beat a wide one the documents
    supported. Narrowness breaks ties inside an evidence band; it does not
    overturn one.
    """
    w = ObjectiveWeights().model_dump()
    w.update({k: float(v) for k, v in weights.items() if k in w})

    ready = [r["kpis"]["listings_ready_pct"] for r in results] or [0.0]
    fields = [r["kpis"]["fields_affected"] for r in results] or [0.0]
    steps = [r["kpis"]["republish_steps"] for r in results] or [0.0]
    filled = [r["kpis"]["completeness_pct"] for r in results] or [0.0]

    def norm(value, lo, hi, invert=False):
        if hi - lo < 1e-9:
            return 1.0
        scaled = (value - lo) / (hi - lo)
        return 1.0 - scaled if invert else scaled

    for r in results:
        k = r["kpis"]
        readiness = norm(k["listings_ready_pct"], min(ready), max(ready))
        # Precision is measured in fields touched, not in the confidence the
        # proposing agent claimed for its scope: a resolution that republishes
        # a number on a page it does not belong on is imprecise however sure it
        # says it is, and every number in the ranking comes from the validator.
        precision = norm(k["fields_affected"], min(fields), max(fields), True)
        effort = norm(k["republish_steps"], min(steps), max(steps), True)
        completeness = norm(k["completeness_pct"], min(filled), max(filled))
        penalty = 0.0 if r["feasible"] else INFEASIBLE_PENALTY
        r["score"] = round(
            max(0.0, w["readiness"] * readiness + w["precision"] * precision
                + w["effort"] * effort + w["completeness"] * completeness
                - penalty), 4)
        r["safety_hold"] = k["safety_flags"] > 0

    # Pareto on the two dimensions a reviewer actually argues about: how much
    # of the catalog goes live against how much work it takes to get there.
    for r in results:
        r["pareto_optimal"] = not any(
            other is not r
            and other["kpis"]["listings_ready_pct"] >= r["kpis"]["listings_ready_pct"]
            and other["kpis"]["republish_steps"] <= r["kpis"]["republish_steps"]
            and (other["kpis"]["listings_ready_pct"] > r["kpis"]["listings_ready_pct"]
                 or other["kpis"]["republish_steps"] < r["kpis"]["republish_steps"])
            for other in results
        )

    # Ties break on the change-set id, which every row carries whatever built
    # it: the graph's candidates and a bare comparison both come back through
    # ``run_scenario``, and a row keyed only by scenario id would not sort here.
    return sorted(results,
                  key=lambda r: (r["safety_hold"], not r["feasible"],
                                 -_evidence_band(r), _scope_width(r),
                                 -r["score"], r["delta_id"]))


# ---------------------------------------------------------------------------
# Publish locks
# ---------------------------------------------------------------------------


def publish_lock(base: Baseline, listing_id: str) -> str:
    """The lock one listing publishes under: ``"CH-MKT-A:PRD-01"``."""
    listing = base.listings[listing_id]
    return f"{listing.channel_id}:{base.product_of_variant[listing.variant_id]}"


def reserve_publish(resource_id: str, bucket_date: str, incident_id: str,
                    scenario_id: str, status: str = "SOFT") -> dict:
    """Claim one (channel, product) for one publish batch date.

    A HARD claim is exclusive. The second one to arrive for the same
    (resource, date) fails on the database's unique index and is reported as a
    conflict - which is what prevents two runs from publishing different
    corrections of the same product to the same channel on the same day.
    """
    held = ReservationStatus(status)
    hard = held is ReservationStatus.HARD
    expires = None if hard else (_now() + timedelta(minutes=SOFT_HOLD_MINUTES))
    reservation_id = _uid("RES")

    # The unique index only covers HARD rows, so it cannot stop a SOFT hold
    # being taken on a batch that is already committed, and it cannot tell a
    # genuine clash from this scenario re-committing after a partial failure.
    committed = db.one(
        "SELECT * FROM reservations WHERE resource_id = ? AND bucket_date = ?"
        " AND status = 'HARD'", (resource_id, bucket_date))
    if committed is not None:
        if committed["scenario_id"] != scenario_id:
            return _conflict(resource_id, bucket_date, committed)
        return {"reserved": True, "reservation_id": committed["id"],
                "status": committed["status"], "expires_at": None,
                "already_held": True}

    try:
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO reservations (id, resource_id, bucket_date, qty,"
                " status, incident_id, scenario_id, created_at, expires_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (reservation_id, resource_id, bucket_date, LOCK_QTY, str(held),
                 incident_id, scenario_id, _now().isoformat(),
                 expires.isoformat() if expires else None),
            )
            audit("publisher", "RESERVE", "listing", resource_id,
                  {"status": str(held), "batch_date": bucket_date,
                   "scenario": scenario_id}, conn=conn)
    except sqlite3.IntegrityError:
        # The database refused a second exclusive claim. This is the mechanism
        # that makes conflicting republishing impossible rather than unlikely.
        holder = db.one(
            "SELECT * FROM reservations WHERE resource_id = ? AND bucket_date = ?"
            " AND status = 'HARD'", (resource_id, bucket_date))
        return _conflict(resource_id, bucket_date, holder)

    return {"reserved": True, "reservation_id": reservation_id,
            "status": str(held),
            "expires_at": expires.isoformat() if expires else None}


def _conflict(resource_id: str, bucket_date: str, holder) -> dict:
    """Shape a refusal the reviewer can act on: what is held, and by whom."""
    channel, _, product = resource_id.partition(":")
    detail = (f"{product} on {channel} is already committed for the "
              f"{bucket_date} batch")
    if holder is not None:
        detail += (f", to scenario {holder['scenario_id']} of incident "
                   f"{holder['incident_id']}")
    violation = Violation(
        constraint="publish_conflict",
        severity=ViolationSeverity.HARD,
        entity_id=resource_id,
        channel_id=channel,
        bucket_date=date.fromisoformat(bucket_date),
        required=LOCK_QTY,
        available=0.0,
        detail=detail,
    )
    return {
        "error": "conflict",
        "reserved": False,
        "violation": violation.model_dump(mode="json"),
        "held_by": {"incident_id": holder["incident_id"],
                    "scenario_id": holder["scenario_id"]} if holder else None,
    }


def release_reservation(reservation_id: str) -> dict:
    conn = db.connect()
    conn.execute("UPDATE reservations SET status = 'RELEASED' WHERE id = ?",
                 (reservation_id,))
    conn.commit()
    return {"released": True, "reservation_id": reservation_id}


def expire_soft_holds() -> dict:
    """Drop expired advisory holds so an abandoned proposal stops blocking."""
    conn = db.connect()
    cur = conn.execute(
        "UPDATE reservations SET status = 'RELEASED'"
        " WHERE status = 'SOFT' AND expires_at IS NOT NULL AND expires_at < ?",
        (_now().isoformat(),))
    conn.commit()
    return {"expired": cur.rowcount}


def open_reservations(incident_id: str | None = None) -> list[dict]:
    sql = ("SELECT * FROM reservations WHERE status IN ('SOFT','HARD')"
           + (" AND incident_id = ?" if incident_id else "")
           + " ORDER BY resource_id, bucket_date")
    rows = db.query(sql, (incident_id,) if incident_id else ())
    return [dict(r) for r in rows]


def _touched_listings(base: Baseline, action) -> list[str]:
    """The listings one action would republish."""
    if action.kind is ActionKind.SET_ATTRIBUTE:
        variants = ([action.entity_id] if action.entity_id in base.variants
                    else base.variants_of.get(action.entity_id, []))
        return sorted(lid for v in variants for lid in base.listings_of.get(v, []))
    if action.kind is ActionKind.SET_FACET:
        return sorted(base.listings_by_channel.get(action.channel_id, []))
    if action.kind in (ActionKind.REGENERATE_COPY, ActionKind.REMAP_TAXONOMY,
                       ActionKind.WITHHOLD_CHANNEL):
        return [action.listing_id]
    return []


def _publish_claims(base: Baseline, change_set: ChangeSet,
                    batch_date: date) -> list[tuple[str, str]]:
    """One lock per affected (channel, product), sorted.

    An action may name the lock it needs; where it does not, the lock is
    derived from the listings it touches, because a publish that forgot to
    declare its lock is still a publish.
    """
    claims: set[tuple[str, str]] = set()
    for action in change_set.actions:
        bucket = (action.bucket_date or batch_date).isoformat()
        if action.resource_id:
            claims.add((action.resource_id, bucket))
            continue
        for listing_id in _touched_listings(base, action):
            claims.add((publish_lock(base, listing_id), bucket))
    return sorted(claims)


# ---------------------------------------------------------------------------
# The two gates that fail closed
# ---------------------------------------------------------------------------


def _pin(source: SourceRef | None) -> str | None:
    """A document reference that carries its own version: ``"DOC-01:v2"``."""
    if source is None:
        return None
    return f"{source.doc_id}:{source.version}" if source.version else source.doc_id


def _in_force(base: Baseline, overlay, key: tuple[str, str]) -> str:
    state = overlay.attr_values.get(key)
    if state is not None:
        return state.version
    source = base.attr_sources.get(key)
    return source.version if source else ""


def _validated_against(base: Baseline, overlay, action) -> str:
    """The source version this action was written against.

    A recorded decision wins over the action's own citation - it is the version
    a human actually signed off - and the version the prepared content was
    built on is the fallback for an action that cites nothing.
    """
    ref = f"{action.entity_id}:{action.attribute_path}"
    recorded = overlay.decision_version.get(ref)
    if recorded:
        return recorded
    if action.source and action.source.version:
        return action.source.version
    source = base.attr_sources.get((action.entity_id, action.attribute_path))
    return source.version if source else ""


def _stale_versions(base: Baseline, change_set: ChangeSet,
                    overlay) -> list[Violation]:
    """Attributes whose source has moved since this resolution was validated.

    Checked against the overlay rather than against the validator's post-change
    table: the change set carries its own citation into that table, so asking
    the validator would be asking the resolution to grade itself. This is what
    stops a print batch prepared under DOC-01 v2 going out after v3 has landed.
    """
    stale: list[Violation] = []
    for action in sorted(change_set.actions, key=lambda a: a.id):
        if action.kind is not ActionKind.SET_ATTRIBUTE:
            continue
        key = (action.entity_id, action.attribute_path)
        current = _in_force(base, overlay, key)
        validated = _validated_against(base, overlay, action)
        if version_rank(current) <= version_rank(validated):
            continue
        stale.append(Violation(
            constraint="stale_version", severity=ViolationSeverity.HARD,
            entity_id=f"{action.entity_id}:{action.attribute_path}",
            required=float(version_rank(current)),
            available=float(version_rank(validated)),
            detail=(f"action {action.id} was validated against {validated}; "
                    f"{current} is now in force for {action.entity_id} "
                    f"{action.attribute_path} and must be revalidated before "
                    f"publishing"),
        ))
    return stale


# ---------------------------------------------------------------------------
# Propose / commit / rollback
# ---------------------------------------------------------------------------


@idempotent("propose_change")
def propose_change(incident_id: str, scenario_id: str, delta: dict) -> dict:
    """Take advisory holds on every batch a candidate would republish.

    Conflicts are found here, at proposal time, rather than at commit when the
    reviewer has already approved something unpublishable.
    """
    base = baseline_mod.get()
    change_set = _change_set(scenario_id, delta)
    expire_soft_holds()

    holds, conflicts = [], []
    for resource_id, bucket in _publish_claims(base, change_set, _sim_now().date()):
        result = reserve_publish(resource_id, bucket, incident_id, scenario_id)
        (conflicts if result.get("error") else holds).append(result)

    audit("graph", "PROPOSE", "scenario", scenario_id,
          {"incident": incident_id, "holds": len(holds),
           "conflicts": len(conflicts)},
          Provenance(kind=ProvenanceKind.INFERRED, agent="propose_change"))

    return {"proposed": not conflicts, "scenario_id": scenario_id,
            "holds": holds, "conflicts": conflicts}


def _refuse(incident_id: str, scenario_id: str, error: str, detail: str,
            violations: list[Violation], actor: str) -> dict:
    """A publish that was stopped, on the record.

    A refusal is auditable for the same reason a commit is: the reviewer's
    question at the end of the run is "why did the print batch not go out?",
    and the answer has to be a row rather than an absence.
    """
    audit(actor, "REFUSE", "incident", incident_id,
          {"scenario": scenario_id, "reason": error, "detail": detail,
           "violations": [v.model_dump(mode="json") for v in violations]},
          Provenance(kind=ProvenanceKind.SIMULATED, agent="commit_plan"))
    return {"error": error, "committed": False, "detail": detail,
            "violations": [v.model_dump(mode="json") for v in violations]}


@idempotent("commit_plan")
def commit_plan(incident_id: str, scenario_id: str, actions: dict | list,
                actor: str = "publisher", as_of: str | None = None) -> dict:
    """Publish an approved resolution.

    Three refusals, all of them fail-closed and all of them at this boundary
    rather than in the graph, so no future graph edit can route around them:

    1.  no recorded APPROVE decision for this incident and scenario;
    2.  a source document has moved since the resolution was validated;
    3.  a safety or allergen declaration is still open on an affected listing.

    Only then are the exclusive locks taken and the published values written.
    """
    approval = db.one(
        "SELECT * FROM approvals WHERE incident_id = ? AND scenario_id = ?"
        " ORDER BY decided_at DESC LIMIT 1", (incident_id, scenario_id))

    if approval is None:
        return _refuse(incident_id, scenario_id, "not_approved",
                       "no reviewer decision recorded for this resolution",
                       [], actor)
    if approval["decision"] != ApprovalDecision.APPROVE:
        return _refuse(incident_id, scenario_id, "not_approved",
                       f"resolution was {approval['decision']}, not APPROVE",
                       [], actor)

    base = baseline_mod.get()
    change_set = _change_set(scenario_id, actions)
    valid = datetime.fromisoformat(as_of) if as_of else _sim_now()
    ov = overlay_mod.build(valid)

    # Re-validate against what is in force *now*, not against what was in force
    # when the resolution was scored. Between those two instants the supplier
    # may have sent another version.
    stale = _stale_versions(base, change_set, ov)
    if stale:
        return _refuse(incident_id, scenario_id, "stale_version",
                       "a later source version is in force; revalidate first",
                       stale, actor)

    result = simulate(base, change_set, ov)
    blocked = [v for v in result.violations
               if v.severity == ViolationSeverity.HARD
               and v.constraint in SAFETY_GATE]
    if blocked:
        return _refuse(incident_id, scenario_id, "safety_hold",
                       f"{len(blocked)} open safety or allergen violations on "
                       f"affected listings", blocked, actor)

    claims = _publish_claims(base, change_set, valid.date())
    conflicts = [r for r in (reserve_publish(rid, bucket, incident_id,
                                             scenario_id, ReservationStatus.HARD)
                             for rid, bucket in claims)
                 if r.get("error")]
    if conflicts:
        # Partial failure: nothing is written, the approval stands, and the
        # reviewer is told which batch moved under them.
        return {"error": "conflict", "committed": False, "conflicts": conflicts,
                "detail": "another committed publish already holds these batches"}

    committed, facts = [], []
    with db.transaction() as conn:
        for action in sorted(change_set.actions, key=lambda a: a.id):
            key = f"{incident_id}:{scenario_id}:{action.id}"
            conn.execute(
                "INSERT OR IGNORE INTO committed_actions (id, incident_id,"
                " scenario_id, action_id, idempotency_key, committed_at, result)"
                " VALUES (?,?,?,?,?,?,?)",
                (_uid("CMT"), incident_id, scenario_id, action.id, key,
                 _now().isoformat(),
                 db.dumps({"kind": str(action.kind),
                           "source": _pin(action.source)})),
            )
            committed.append(action.id)

        facts = _record_published(base, change_set, valid, scenario_id, conn)
        conn.execute("UPDATE incidents SET status = 'COMMITTED' WHERE id = ?",
                     (incident_id,))
        audit(actor, "COMMIT", "incident", incident_id,
              {"scenario": scenario_id, "actions": committed,
               "locks": [r for r, _ in claims], "facts": len(facts),
               "trace_hash": result.trace_hash},
              Provenance(kind=ProvenanceKind.COMMITTED, source_id=scenario_id),
              conn=conn)

    return {"committed": True, "incident_id": incident_id,
            "scenario_id": scenario_id, "actions": committed,
            "locks": [r for r, _ in claims], "facts": facts,
            "trace_hash": result.trace_hash}


def _record_published(base: Baseline, change_set: ChangeSet, valid: datetime,
                      scenario_id: str, conn) -> list[str]:
    """Write what actually went live.

    COMMITTED facts rather than an in-place update: the published value is a
    new row citing the document version it came from, so "what did this channel
    receive, and on whose authority?" stays answerable after the next
    correction lands - and the version it pins is what the stale-version gate
    reads on the next publish.
    """
    written: list[str] = []
    # Recorded on the replay clock, not on wall-clock time: a fact recorded
    # "now" would sit outside the horizon and be invisible to every as-of read.
    def write(entity_type: str, entity_id: str, attr: str, value: object,
              provenance: Provenance) -> None:
        written.append(store.record(entity_type, entity_id, attr, value, valid,
                                    provenance, recorded_at=valid, conn=conn))

    # The version each listing goes to press on, collected rather than written
    # per action: two actions can republish one listing, and the freeze-window
    # rule reads a single answer per listing - the latest version this publish
    # carried, so an action citing an older document cannot pull it back.
    pressed: dict[str, SourceRef] = {}

    def press(listing_id: str, source: SourceRef | None) -> None:
        if source is None or not source.version:
            return
        held = pressed.get(listing_id)
        if held is None or version_rank(source.version) > version_rank(held.version):
            pressed[listing_id] = source

    for action in sorted(change_set.actions, key=lambda a: a.id):
        provenance = Provenance(kind=ProvenanceKind.COMMITTED,
                                source_id=_pin(action.source),
                                agent="commit_plan", run_id=scenario_id)

        if action.kind is ActionKind.SET_ATTRIBUTE:
            entity_type = ("variant" if action.entity_id in base.variants
                           else "product")
            write(entity_type, action.entity_id, action.attribute_path,
                  action.new_value, provenance)
            for listing_id in _touched_listings(base, action):
                write("listing", listing_id,
                      f"published.{action.attribute_path}",
                      action.new_value, provenance)
                press(listing_id, action.source)

        elif action.kind is ActionKind.REGENERATE_COPY:
            write("listing", action.listing_id, f"published.{action.field}",
                  action.proposed_text, provenance)
            press(action.listing_id, action.source)

        elif action.kind is ActionKind.WITHHOLD_CHANNEL:
            # No press: a withheld listing publishes nothing, so its version
            # stands where it was and the freeze-window rule keeps reporting
            # the artefact that is actually in the world.
            write("listing", action.listing_id, "status", "WITHHELD", provenance)

    for listing_id in sorted(pressed):
        source = pressed[listing_id]
        write("listing", listing_id, overlay_mod.ATTR_PUBLISHED_VERSION,
              source.version,
              Provenance(kind=ProvenanceKind.COMMITTED, source_id=_pin(source),
                         agent="commit_plan", run_id=scenario_id))

    return written


def _before_publish(base: Baseline, row, before: datetime) -> object:
    """What this entity's attribute held before the commit wrote over it.

    Read as of just before the publish was recorded, so the run's own fact is
    excluded rather than found again. A publish that was the first assertion of
    its kind falls back to the seed pack, which is what the prepared content
    stands on; an attribute the pack never carried has nothing to restore, and
    ``None`` is the honest answer to that.
    """
    prior = store.get(row["entity_type"], row["entity_id"], row["attr"],
                      as_of_valid=datetime.fromisoformat(row["valid_from"]),
                      as_of_recorded=before)
    if prior is not None:
        return prior.value
    if row["entity_type"] in ("variant", "product"):
        return base.attr_values.get((row["entity_id"], row["attr"]))
    listing = base.listings.get(row["entity_id"])
    return getattr(listing, row["attr"], None) if listing else None


def _retract_published(scenario_id: str, at: datetime, conn) -> list[str]:
    """Put back what this scenario published over.

    A retraction is a new row rather than an edit, like every other correction
    in this store: the published value *was* what the channel held between the
    commit and the rollback, and an as-of read inside that window has to keep
    saying so. The retraction is valid from the rollback onwards, so a read
    taken now returns the value the publish displaced and a read taken as of
    the publish still returns what went out. Releasing the lock alone leaves
    the published value standing, which is what "unpublish" cannot mean.

    A row already superseded is left alone, so a repeated rollback retracts
    nothing twice.
    """
    rows = db.query(
        "SELECT * FROM facts"
        " WHERE json_extract(provenance, '$.kind') = 'COMMITTED'"
        "   AND json_extract(provenance, '$.run_id') = ?"
        "   AND json_extract(provenance, '$.agent') = 'commit_plan'"
        "   AND id NOT IN (SELECT supersedes_id FROM facts"
        "                  WHERE supersedes_id IS NOT NULL)"
        " ORDER BY id", (scenario_id,))
    if not rows:
        return []

    # A rollback cannot precede the publish it reverses, and two rows sharing a
    # replay tick tie on the store's ordering - a retraction that loses that
    # tie is invisible. Say what is true anyway: the publish is retracted after
    # it happened, even where the clock has not moved since.
    published_at = max(datetime.fromisoformat(r["recorded_at"]) for r in rows)
    at = max(at, published_at + timedelta(microseconds=1))

    base = baseline_mod.get()
    provenance = Provenance(kind=ProvenanceKind.COMMITTED, source_id=scenario_id,
                            agent="rollback", run_id=scenario_id,
                            note=f"retracted by rollback of {scenario_id}")
    return [store.correct(row["id"],
                          value=_before_publish(base, row, published_at
                                                - timedelta(microseconds=1)),
                          provenance=provenance, valid_from=at, recorded_at=at,
                          conn=conn)
            for row in rows]


@idempotent("rollback")
def rollback(incident_id: str, scenario_id: str, reason: str = "",
             actor: str = "publisher") -> dict:
    """Unpublish: retract the published facts, release the exclusive locks,
    mark the actions reversed and reopen the case.

    The retraction restores what each published value displaced, from the
    instant of the rollback onwards, rather than deleting anything - so "what
    did this channel hold, and when?" stays answerable while an as-of read
    taken now no longer returns a value that has been pulled.
    """
    at = _sim_now()
    with db.transaction() as conn:
        retracted = _retract_published(scenario_id, at, conn)
        conn.execute(
            "UPDATE reservations SET status = 'RELEASED'"
            " WHERE incident_id = ? AND scenario_id = ? AND status = 'HARD'",
            (incident_id, scenario_id))
        cur = conn.execute(
            "UPDATE committed_actions SET rolled_back = 1"
            " WHERE incident_id = ? AND scenario_id = ?",
            (incident_id, scenario_id))
        conn.execute("UPDATE incidents SET status = 'OPEN' WHERE id = ?",
                     (incident_id,))
        audit(actor, "ROLLBACK", "incident", incident_id,
              {"scenario": scenario_id, "reason": reason,
               "actions_reversed": cur.rowcount,
               "facts_retracted": len(retracted)}, conn=conn)

    return {"rolled_back": True, "actions_reversed": cur.rowcount,
            "retracted": retracted}
