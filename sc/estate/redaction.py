"""Taking a wrong value down, per channel.

``remediation`` pushes a corrected value out. This is the step before it, and
it exists because those are not the same act and must not be gated the same
way.

A late correction arrives against copy that is already live. Between the moment
the retailer knows the value is wrong and the moment a validated replacement
exists, the wrong value is still on sale. For a marketing bullet that is
untidy. For an allergen declaration it is the whole problem, and "we are
working on the corrected wording" is not an answer anybody would accept.

So a redaction hides the wrong value on the authority of the approval that
already said it was wrong, immediately, and republication waits for a second
decision of its own. Both gates live at the planning boundary; this module
decides only *what shape* hiding takes on each channel, and reports what
happened per system.

**The shape is derived, never configured.** Two things the record already
holds decide it: whether the attribute is safety-class, and whether the channel
declares it required. Nothing here is a taste judgement.

* A **web** page can carry a placeholder for an ordinary field, and cannot for
  a required one - a food page reading "Contains: -" is not a lawful page, so
  the listing comes down instead.
* A **marketplace** cannot carry a placeholder for a safety field at all. Its
  own rules forbid it: the allergen statement is REQUIRED and its format is
  matched against a pattern, so a placeholder is itself a hard violation. The
  listing is withdrawn. This is forced by the channel's declared rules rather
  than chosen.
* A **search** facet is dropped. A shopper filtering for "no peanuts" and being
  shown peanuts is the actual harm, and the channel declares no rules to object.
* A **shelf** label is a physical artefact. It stays wrong in the aisle until
  somebody walks over with a printer, so the honest outcome is a queued reprint
  with a date, never "sent".
* A **print** run cannot be redacted at all. Two hundred thousand catalogues
  are in the world and there is nothing to take down. The only truthful outcome
  is an erratum obligation: open, owned and dated.

``ERRATUM`` is deliberately not ``DEFERRED``. Deferred means later. A printed
page has no later.

**What this must never do**, and both have cost somebody a lot of money
somewhere:

* It must never emit a change-set action. ``engine.simulate`` skips every check
  for a withheld listing, so redacting the print listing through a
  ``WITHHOLD_CHANNEL`` action would make the frozen-version violation vanish
  from the validator while the wrong catalogues were still in circulation -
  which is INC-2026-002 happening a second time, in the code written to stop it.
* It must never write an attribute fact or move a published version. Every
  in-flight scenario would go stale against a version nothing published, and
  the republish this sequence exists to allow would refuse itself.
"""

from __future__ import annotations

from datetime import timedelta

from sc import db
from sc.estate import publication

#: What happened on one system. Mirrors ``remediation``'s vocabulary, with one
#: outcome that has no equivalent there.
REDACTED = "REDACTED"      # the channel no longer shows it
QUEUED = "QUEUED"          # a physical artefact has to be re-made
ERRATUM = "ERRATUM"        # cannot be recalled; an obligation is open instead
REFUSED = "REFUSED"        # no authority, or nothing to redact

#: The shape a redaction takes on one channel.
PLACEHOLDER = "PLACEHOLDER"
WITHDRAWN = "WITHDRAWN"
FACET_DROPPED = "FACET_DROPPED"
REPRINT_QUEUED = "REPRINT_QUEUED"
ERRATUM_REQUIRED = "ERRATUM_REQUIRED"

KINDS = (PLACEHOLDER, WITHDRAWN, FACET_DROPPED, REPRINT_QUEUED,
         ERRATUM_REQUIRED)

#: What a shopper sees where a value has been suppressed. Deliberately says
#: that information is missing rather than implying the product lacks the
#: property - "no allergens declared" and "we are checking the declaration" are
#: very different sentences to somebody with an allergy.
NOTICE = ("This information is being updated and has been withheld until the "
          "supplier's revision is confirmed.")
PLACEHOLDER_TEXT = "Temporarily unavailable"

#: How long a physical artefact has to be re-made. Working days would need a
#: calendar this system does not have; the number is the promise, not a
#: calculation.
REPRINT_DAYS = 3
ERRATUM_DAYS = 5


def _required_here(base, channel_id: str, attribute_path: str) -> bool:
    """Whether this channel declares it cannot publish without the field."""
    definition = base.attr_defs.get(attribute_path)
    return bool(definition and channel_id in (definition.required_for or []))


def _safety(base, attribute_path: str) -> bool:
    return bool(getattr(base.attr_defs.get(attribute_path), "safety_class",
                        False))


def kind_for(system, base, attribute_path: str) -> str:
    """Which of the five shapes a redaction takes on this channel.

    Derived from the channel's kind, the attribute's safety class and the
    channel's own declared requirements - never from a table somebody has to
    keep in step with the rules.
    """
    channel = base.channels.get(system.channel_id)
    kind = str(getattr(channel, "kind", "WEB"))
    grave = _safety(base, attribute_path) or _required_here(
        base, system.channel_id, attribute_path)

    if not system.recallable:
        return ERRATUM_REQUIRED
    if kind == "PRINT":
        return ERRATUM_REQUIRED
    if kind == "SHELF":
        return REPRINT_QUEUED
    if kind == "SEARCH":
        return FACET_DROPPED
    if kind == "MARKETPLACE":
        # A placeholder is itself a hard violation here: the field is REQUIRED
        # and its format is matched against a pattern. Withdrawing is the only
        # thing the channel's own rules leave available.
        return WITHDRAWN if grave else PLACEHOLDER
    return WITHDRAWN if grave else PLACEHOLDER


#: Which shapes take the whole listing off air, as opposed to hiding one field.
_TAKES_DOWN = {WITHDRAWN}

#: Which shapes leave work owed rather than something hidden.
_OBLIGATION = {REPRINT_QUEUED: "REPRINT", ERRATUM_REQUIRED: "ERRATUM"}

_OUTCOME = {
    PLACEHOLDER: REDACTED,
    WITHDRAWN: REDACTED,
    FACET_DROPPED: REDACTED,
    REPRINT_QUEUED: QUEUED,
    ERRATUM_REQUIRED: ERRATUM,
}


def _reason_for(kind: str, system, base, attribute_path: str) -> str:
    definition = base.attr_defs.get(attribute_path)
    label = getattr(definition, "label", attribute_path)
    if kind == ERRATUM_REQUIRED:
        return (f"{system.channel_id} cannot be recalled"
                + (f" and is inside a {system.freeze_days}-day freeze window"
                   if system.freeze_days else "")
                + f"; an erratum is owed for {label}")
    if kind == REPRINT_QUEUED:
        return (f"{system.channel_id} prints a physical label; {label} stays "
                f"wrong in the aisle until the reprint is confirmed")
    if kind == WITHDRAWN:
        return (f"{label} is required on {system.channel_id} and its format is "
                f"checked, so the listing comes down rather than showing a "
                f"placeholder that would itself fail the channel's rules")
    if kind == FACET_DROPPED:
        return f"the {label} facet is dropped rather than left indexing a wrong value"
    return f"{label} is replaced with a notice on {system.channel_id}"


def plan_redaction(trace: dict, base, *,
                   attribute_paths: list[str] | None = None) -> list[dict]:
    """What would be hidden where, hiding nothing.

    Same row shape as ``remediation.plan_dispatch``, plus the shape the hiding
    takes and whether it leaves an obligation behind. A reviewer should be able
    to see that the print run cannot be recalled *before* deciding, not from a
    report afterwards.
    """
    paths = list(attribute_paths or [])
    lookup = publication.by_channel(base)
    rows: list[dict] = []
    for group in publication.blast_to_systems(trace, base):
        system = lookup[group["channel_id"]]
        for path in paths or [""]:
            kind = kind_for(system, base, path)
            rows.append({
                **group,
                "attribute_path": path,
                "kind": kind,
                "verb": "redact_field",
                "outcome": _OUTCOME[kind],
                "obligation": _OBLIGATION.get(kind, ""),
                "reason": _reason_for(kind, system, base, path),
                "endpoint": system.endpoint,
            })
    return rows


# ---------------------------------------------------------------------------
# Obligations
# ---------------------------------------------------------------------------


def _open_obligation(kind: str, system, listing_id: str, entity_id: str,
                     attribute_path: str, incident_id: str, detail: dict,
                     actor: str) -> str:
    from sc.replay import tape
    from sc.tools import planning

    days = ERRATUM_DAYS if kind == "ERRATUM" else REPRINT_DAYS
    obligation_id = f"OBL-{kind[:3]}-{listing_id}-{attribute_path}"[:80]
    now = tape.sim_now()
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO obligations (id, kind, system_id,"
            " channel_id, listing_id, entity_id, attribute_path, incident_id,"
            " opened_at, due_by, status, detail)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,'OPEN',?)",
            (obligation_id, kind, system.id, system.channel_id, listing_id,
             entity_id, attribute_path, incident_id, now.isoformat(),
             (now + timedelta(days=days)).isoformat(), db.dumps(detail)))
        planning.audit(
            actor, "ERRATUM_OPEN" if kind == "ERRATUM" else "REPRINT_QUEUE",
            "listing", listing_id,
            {"obligation_id": obligation_id, "system": system.id,
             "attribute_path": attribute_path, "incident_id": incident_id,
             "due_by": (now + timedelta(days=days)).isoformat(), **detail},
            conn=conn)
    return obligation_id


def open_obligations(system_id: str | None = None,
                     status: str = "OPEN") -> list[dict]:
    """What is still owed, newest first."""
    sql = "SELECT * FROM obligations WHERE status = ?"
    params: tuple = (status,)
    if system_id:
        sql += " AND system_id = ?"
        params += (system_id,)
    return [{**dict(r), "detail": db.loads(r["detail"])}
            for r in db.query(sql + " ORDER BY opened_at DESC", params)]


def discharge(obligation_id: str, *, actor: str, evidence: str = "",
              system_id: str | None = None) -> dict:
    """Mark an erratum published or a reprint confirmed.

    Scoped to the asking system when one is given, for the reason every read
    in this estate is: a marketplace has no business closing the print
    channel's obligations.
    """
    from sc.replay import tape
    from sc.tools import planning

    row = db.one("SELECT * FROM obligations WHERE id = ?", (obligation_id,))
    if row is None:
        return {"error": f"no obligation {obligation_id}", "discharged": False}
    if system_id and row["system_id"] != system_id:
        return {"error": f"{obligation_id} belongs to {row['system_id']}",
                "discharged": False}
    if row["status"] != "OPEN":
        return {"error": f"{obligation_id} is already {row['status']}",
                "discharged": False}

    now = tape.sim_now().isoformat()
    with db.transaction() as conn:
        conn.execute("UPDATE obligations SET status = 'DISCHARGED',"
                     " discharged_by = ?, discharged_at = ? WHERE id = ?",
                     (actor, now, obligation_id))
        planning.audit(
            actor,
            "ERRATUM_DISCHARGE" if row["kind"] == "ERRATUM"
            else "REPRINT_CONFIRM",
            "listing", row["listing_id"],
            {"obligation_id": obligation_id, "evidence": evidence,
             "system": row["system_id"]}, conn=conn)

    from sc.estate import publication_events

    publication_events.notify("obligation", {
        "change": "discharged", "obligation_id": obligation_id,
        "kind": row["kind"], "system_id": row["system_id"],
        "open_count": len(open_obligations())})
    return {"discharged": True, "obligation_id": obligation_id,
            "kind": row["kind"], "at": now}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def redact(incident_id: str, entity_id: str, fields: list[str], *,
           actor: str = "publisher", reason: str = "", trace: dict | None = None,
           base=None, only_system: str | None = None) -> dict:
    """Hide a wrong value on every system carrying it, and report per system.

    Per system for the reason dispatch is: a marketplace that has stopped
    answering must not hold up the four channels that are answering. "Redacted
    on four of six, one queued for reprint, one erratum" is the sentence, and
    it is a true one - unlike "failed", which would be false about four of them.
    """
    from sc.state import baseline as baseline_mod
    from sc.tools import network as network_tools
    from sc.tools import planning

    base = base if base is not None else baseline_mod.get()
    trace = trace if trace is not None else network_tools.trace_dependencies(entity_id)

    authorised, who = planning._authorised_to_redact(incident_id)
    planned = plan_redaction(trace, base, attribute_paths=fields)
    if only_system:
        planned = [row for row in planned if row["system"] == only_system]

    if not authorised:
        for row in planned:
            row["outcome"] = REFUSED
            row["reason"] = who
        return _summary(incident_id, entity_id, planned, authorised=False,
                        reason=who)

    lookup = publication.by_channel(base)
    for row in planned:
        system = lookup[row["channel_id"]]
        kind = row["kind"]
        obligation_kind = _OBLIGATION.get(kind)

        if obligation_kind:
            # Nothing to hide. An artefact already in the world cannot be
            # taken down, so what is recorded is the work that is owed.
            row["obligation_id"] = _open_obligation(
                obligation_kind, system, row["listings"][0], entity_id,
                row["attribute_path"], incident_id,
                {"reason": row["reason"], "skus": row["skus"]}, actor)
            row["redacted"] = False
            continue

        results = []
        for listing_id in row["listings"]:
            results.append(planning.commit_redaction(
                incident_id, listing_id, row["attribute_path"], kind,
                actor, reason or row["reason"],
                placeholder=PLACEHOLDER_TEXT if kind == PLACEHOLDER else "",
                notice=NOTICE,
                take_down=kind in _TAKES_DOWN,
                idempotency_key=f"redact:{incident_id}:{listing_id}:"
                                f"{row['attribute_path']}"))
        failed = [r for r in results if r.get("error")]
        row["redacted"] = not failed
        if failed:
            row["outcome"] = REFUSED
            row["reason"] = failed[0].get("detail", "refused")

    summary = _summary(incident_id, entity_id, planned, authorised=True,
                       reason="")

    from sc.estate import publication_events

    publication_events.notify("redaction", {
        "incident_id": incident_id, "entity_id": entity_id,
        "fields": list(fields), **summary})
    return summary


def _summary(incident_id: str, entity_id: str, rows: list[dict], *,
             authorised: bool, reason: str) -> dict:
    return {
        "incident_id": incident_id,
        "entity_id": entity_id,
        "authorised": authorised,
        "reason": reason,
        "systems": rows,
        "redacted": sum(1 for r in rows if r["outcome"] == REDACTED),
        "queued": sum(1 for r in rows if r["outcome"] == QUEUED),
        "errata": sum(1 for r in rows if r["outcome"] == ERRATUM),
        "refused": sum(1 for r in rows if r["outcome"] == REFUSED),
    }


def restore(incident_id: str, entity_id: str, fields: list[str], *,
            actor: str = "publisher", reason: str = "",
            trace: dict | None = None, base=None,
            only_system: str | None = None) -> dict:
    """Put hidden values back, and report per system.

    Refuses where the redaction was an erratum, and the asymmetry is the honest
    one: you cannot un-print a catalogue, so there was never anything hidden
    there to put back. ``revert`` already models the same shape for a channel
    that was never sent to.
    """
    from sc.state import baseline as baseline_mod
    from sc.tools import network as network_tools
    from sc.tools import planning

    base = base if base is not None else baseline_mod.get()
    trace = trace if trace is not None else network_tools.trace_dependencies(entity_id)
    planned = plan_redaction(trace, base, attribute_paths=fields)
    if only_system:
        planned = [row for row in planned if row["system"] == only_system]

    for row in planned:
        if _OBLIGATION.get(row["kind"]):
            row["outcome"] = REFUSED
            row["restored"] = False
            row["reason"] = (f"never hidden on {row['channel_id']}: "
                             f"{row['reason']}")
            continue
        results = [planning.commit_restore(
            incident_id, listing_id, row["attribute_path"], actor,
            reason=reason, put_back=row["kind"] in _TAKES_DOWN,
            idempotency_key=f"restore:{incident_id}:{listing_id}:"
                            f"{row['attribute_path']}")
            for listing_id in row["listings"]]
        failed = [r for r in results if r.get("error")]
        row["restored"] = not failed
        row["outcome"] = REFUSED if failed else REDACTED
        if failed:
            row["reason"] = failed[0].get("detail", "refused")

    restored = sum(1 for r in planned if r.get("restored"))
    summary = {"incident_id": incident_id, "entity_id": entity_id,
               "systems": planned, "restored": restored,
               "refused": len(planned) - restored}

    from sc.estate import publication_events

    publication_events.notify("redaction", {
        "incident_id": incident_id, "entity_id": entity_id,
        "change": "restored", **summary})
    return summary
