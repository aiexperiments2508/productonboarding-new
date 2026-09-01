"""Who decides a proposed value, and what happens when they do.

``suggest`` produces a value and a score. This module answers the only two
questions left: does a person have to look at it, and what is written when
somebody says yes.

**The threshold.** Ninety-five per cent by default, held in ``runtime_config``
so it can be moved without a restart, and recorded in the ledger when it moves -
a number that decides what gets written without a person looking at it is a
policy decision, and a policy decision nobody can date is one nobody can audit.

**Three things always go to a person, and only one of them is the score.**

*   A **safety-class** attribute. ``suggest`` already scores these zero and says
    why; this refuses them a second time and does not consult the number,
    because a rule that holds only because another rule fed it a zero is a rule
    that stops holding the day somebody changes the other one.
*   An **uncorroborated** proposal - one source and nothing agreeing with it.
    Checked structurally, on ``supporters``, rather than by trusting the weights
    to fall short of the threshold. The threshold is a knob an operator can turn
    down, and a safety property that survives only while nobody turns it is not
    one.
*   Anything the score does not clear. That is the whole point of the number,
    and it is the *last* of the three rather than the first.

**What gets written, and why the provenance differs.** This is the part that
would be easy to get subtly wrong.

*   An **autonomous** fill goes through ``ingest.record_attribute``, the same
    door ``enrich`` writes through, and lands ``INFERRED`` with its confidence
    and its citation. Nothing else may write it: that provenance is what keeps
    the fail-closed safety gate in ``sim.engine`` able to see it, and what stops
    a model's reading acquiring the standing of a supplier's assertion.
*   A **person's** decision lands ``DECIDED``. Not INFERRED-with-a-note:
    ``ProvenanceKind`` keeps "an LLM concluded it" and "a human chose it" apart
    on purpose, the audit trail is meant to be able to tell them apart, and the
    publish-time safety check treats them differently *because they are
    different*. A category manager approving a value is taking responsibility
    for it, which is precisely the thing an inference cannot do.

**Nothing here publishes.** A product becomes ready by having no findings left,
which is arithmetic; publication needs ``commit_plan``, a recorded approval and
a channel reservation, and none of those are touched. That prohibition is
inherited from ``fix`` and is not weakened by a decision being human - a
reviewer answering "yes, 65 W is right" has not said "put it on sale".
"""

from __future__ import annotations

import json
import uuid

from sc import db

THRESHOLD_KEY = "onboarding.autonomy_threshold"

#: What the category manager asked for. Above this a proposal is written
#: without anybody looking at it.
DEFAULT_THRESHOLD = 0.95

AUTONOMOUS = "AUTONOMOUS"
HUMAN = "HUMAN"

#: How many sources have to agree before a value may be written without a
#: person looking at it. Two, and it is not a tunable: one passage, one sibling
#: or one past decision is a lead, and a lead is what the queue is for.
MIN_SOURCES = 2

APPROVE = "APPROVE"
REJECT = "REJECT"
RECTIFY = "RECTIFY"

DECISIONS = (APPROVE, REJECT, RECTIFY)


def threshold() -> float:
    """The autonomy threshold in force, clamped to something meaningful.

    Zero would make every proposal autonomous, which is the one setting that
    could not be undone by looking at a queue - so the floor is deliberate, and
    a value above one would silently mean "never", which the UI can say in
    words instead.
    """
    raw = db.get_config(THRESHOLD_KEY)
    try:
        value = float(raw) if raw is not None else DEFAULT_THRESHOLD
    except (TypeError, ValueError):
        value = DEFAULT_THRESHOLD
    return max(0.5, min(1.0, value))


def set_threshold(value: float, *, actor: str) -> dict:
    """Move the threshold, and say who did.

    Audited rather than merely stored. "Why was this written without anybody
    approving it" is answered by the threshold that was in force, and a
    threshold with no history cannot answer it.
    """
    from sc.tools import planning

    before = threshold()
    wanted = max(0.5, min(1.0, float(value)))
    db.set_config(THRESHOLD_KEY, str(wanted))
    planning.audit(actor, "SET_AUTONOMY_THRESHOLD", "config", THRESHOLD_KEY,
                   {"from": before, "to": wanted})
    return {"threshold": threshold(), "previous": before, "actor": actor}


def route(suggestion, limit: float | None = None) -> str:
    """Whether this proposal may be written without a person looking.

    ``suggestion`` is a ``suggest.Suggestion``. Deliberately takes the object
    rather than a bare number: two of the three refusals below are properties
    of the proposal rather than of its score, and a signature that accepted a
    confidence would make them unreachable.

    The order is the order they are argued in. The score is consulted last,
    because it is the only one of the three a threshold can move.
    """
    if suggestion.safety_class:
        return HUMAN
    if suggestion.supporters < MIN_SOURCES:
        return HUMAN
    bar = threshold() if limit is None else limit
    return AUTONOMOUS if suggestion.confidence >= bar else HUMAN


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------


def record(submission_id: str, suggestion, *, routed: str,
           limit: float, conn=None) -> str:
    """Keep a proposal so a decision can attach to the exact thing shown.

    Upserted on (submission, entity, attribute): re-assessing a batch refreshes
    the open proposal rather than stacking a second one beside it, and a
    proposal that has already been decided is left alone - re-reading a batch
    is not a reason to reopen a question somebody answered.
    """
    from sc.replay import tape

    c = conn or db.connect()
    existing = c.execute(
        "SELECT id, decision FROM onboarding_suggestions"
        " WHERE submission_id = ? AND entity_id = ? AND attribute_path = ?",
        (submission_id, suggestion.entity_id,
         suggestion.attribute_path)).fetchone()

    if existing is not None and existing["decision"]:
        return existing["id"]

    row = (
        json.dumps(suggestion.value, default=str),
        float(suggestion.confidence),
        json.dumps(suggestion.reasons, default=str),
        1 if suggestion.safety_class else 0,
        json.dumps(suggestion.citation or {}, default=str),
        tape.sim_now().isoformat(),
        routed,
        float(limit),
    )

    if existing is not None:
        c.execute(
            "UPDATE onboarding_suggestions SET proposed = ?, confidence = ?,"
            " reasons = ?, safety_class = ?, citation = ?, created_at = ?,"
            " route = ?, threshold = ? WHERE id = ?",
            (*row, existing["id"]))
        identifier = existing["id"]
    else:
        identifier = f"SUG-{uuid.uuid4().hex[:12]}"
        c.execute(
            "INSERT INTO onboarding_suggestions (id, submission_id, entity_id,"
            " attribute_path, proposed, confidence, reasons, safety_class,"
            " citation, created_at, route, threshold)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (identifier, submission_id, suggestion.entity_id,
             suggestion.attribute_path, *row))
    if conn is None:
        c.commit()
    return identifier


def pending(submission_id: str | None = None) -> list[dict]:
    """Proposals waiting on a category manager, oldest first.

    Oldest first, unlike the correction queue, and for a different reason: a
    correction queue is ordered by severity because the worst thing open is the
    thing to work next, and these are all the same kind of question. What
    matters here is that a supplier is waiting, so the one that has been waiting
    longest is the one to answer.
    """
    sql = ("SELECT * FROM onboarding_suggestions WHERE decision IS NULL"
           " AND route = ?")
    params: tuple = (HUMAN,)
    if submission_id:
        sql += " AND submission_id = ?"
        params += (submission_id,)
    return [_row(r) for r in db.query(sql + " ORDER BY created_at, id", params)]


def for_submission(submission_id: str) -> list[dict]:
    """Every proposal this bundle produced, decided or not."""
    return [_row(r) for r in db.query(
        "SELECT * FROM onboarding_suggestions WHERE submission_id = ?"
        " ORDER BY created_at, id", (submission_id,))]


def get(suggestion_id: str) -> dict | None:
    row = db.one("SELECT * FROM onboarding_suggestions WHERE id = ?",
                 (suggestion_id,))
    return _row(row) if row is not None else None


def _row(row) -> dict:
    return {
        "id": row["id"],
        "submission_id": row["submission_id"],
        "entity_id": row["entity_id"],
        "attribute_path": row["attribute_path"],
        "value": _loads(row["proposed"]),
        "confidence": row["confidence"],
        "reasons": _loads(row["reasons"]) or [],
        "safety_class": bool(row["safety_class"]),
        "citation": _loads(row["citation"]) or None,
        "created_at": row["created_at"],
        "route": row["route"],
        "threshold": row["threshold"],
        "decision": row["decision"],
        "decided_by": row["decided_by"],
        "decided_at": row["decided_at"],
        "decided_value": _loads(row["decided_value"]),
        "comment": row["comment"] or "",
    }


def _loads(raw):
    if raw is None or raw == "":
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


def decide(suggestion_id: str, *, actor: str, decision: str,
           value: object = None, comment: str = "") -> dict:
    """A category manager answers one proposal.

    Three answers and no fourth. **Approve** takes the value as proposed;
    **rectify** replaces it with the one the manager typed, which is the answer
    that makes this queue worth having rather than a pair of buttons; **reject**
    writes nothing and sends the field back to the supplier.

    Refuses a proposal that has already been decided rather than overwriting
    it. Two managers reaching the queue at once is the ordinary case, and the
    second one has to be told the question was answered rather than silently
    replacing the first answer.
    """
    from sc.onboarding import fix as fix_mod
    from sc.tools import planning

    if decision not in DECISIONS:
        return {"error": f"{decision!r} is not one of {', '.join(DECISIONS)}",
                "decided": False}
    actor = str(actor or "").strip()
    if not actor:
        return {"error": ("a decision has to be attributable to somebody. "
                          "There is no identity provider anywhere in this "
                          "system, so the name is taken at its word and "
                          "recorded"),
                "decided": False}

    found = get(suggestion_id)
    if found is None:
        return {"error": f"no proposal {suggestion_id}", "decided": False}
    if found["decision"]:
        return {"error": (f"{suggestion_id} was already "
                          f"{found['decision'].lower()}d by "
                          f"{found['decided_by']}"),
                "decided": False, "held": found}

    written = None
    if decision == RECTIFY and value is None:
        return {"error": "a rectified proposal needs the value to write",
                "decided": False}

    settled = value if decision == RECTIFY else found["value"]

    if decision in (APPROVE, RECTIFY):
        # DECIDED, not INFERRED. See the module docstring: a person choosing a
        # value is a different class of knowledge from a model reading one, the
        # ledger is meant to be able to tell them apart, and the publish-time
        # safety check treats them differently because they are different.
        written = fix_mod.write_decided(
            entity_id=found["entity_id"],
            attribute_path=found["attribute_path"],
            value=settled, actor=actor, suggestion_id=suggestion_id,
            citation=found["citation"] or {},
            note=("approved as proposed" if decision == APPROVE
                  else "corrected by the reviewer"))

    from sc.replay import tape

    with db.transaction() as conn:
        conn.execute(
            "UPDATE onboarding_suggestions SET decision = ?, decided_by = ?,"
            " decided_at = ?, decided_value = ?, comment = ? WHERE id = ?",
            (decision, actor, tape.sim_now().isoformat(),
             json.dumps(settled, default=str) if decision == RECTIFY else None,
             comment or "", suggestion_id))

    planning.audit(actor, "ONBOARDING_DECISION", "variant", found["entity_id"], {
        "suggestion_id": suggestion_id,
        "submission_id": found["submission_id"],
        "attribute_path": found["attribute_path"],
        "decision": decision,
        "proposed": found["value"],
        "written": settled if decision != REJECT else None,
        "confidence": found["confidence"],
        "threshold": found["threshold"],
        "fact_id": written,
        "comment": comment or "",
    })

    return {
        "decided": True,
        "suggestion_id": suggestion_id,
        "decision": decision,
        "actor": actor,
        "value": settled if decision != REJECT else None,
        "fact_id": written,
        "note": _note(decision, found),
    }


def _note(decision: str, found: dict) -> str:
    """What just happened, in the words the reviewer needs to read."""
    field = found["attribute_path"]
    if decision == REJECT:
        return (f"nothing was written. {field} is still missing on "
                f"{found['entity_id']}, and it now has to come from the "
                f"supplier")
    verb = "as proposed" if decision == APPROVE else "as you corrected it"
    return (f"{field} on {found['entity_id']} is recorded {verb}, against your "
            f"name rather than as something a model inferred. Nothing has been "
            f"published: the product is ready when it has no findings left, and "
            f"launching it is a separate decision behind a separate gate")
