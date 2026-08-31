"""What happened to what a supplier sent.

The estate's ``arrivals`` table is the retailer's record of what landed. This is
the supplier's record of what it sent, and they are not the same question - one
submission carries several events, plus bytes on disk, plus the idempotency key
the portal generated, and none of that fits in a row about an arrival.

The table holds only the submission's own facts. Everything the platform
*decided* is joined at read time, from the table that owns it: the arrival from
``arrivals``, the recorded document version from ``facts``, the correction
raised from the signals in force, whether the graph has read it from the audit
ledger, the case from ``incidents``, the verdict from the readiness assessment.
There is deliberately no ``status`` column and no ``verdict`` column, because a
stored verdict that can disagree with the record is the failure this system
spends most of its design avoiding - and a supplier is exactly the reader who
would find the disagreement first.

Two things this reports honestly rather than flattering:

* A document version raises no correction signal by itself. Ingestion records
  that the version is in force and declines to guess at what the document says;
  the reading happens when a correction run reaches it. So the stage is
  ``awaiting_extraction``, which is a different statement from "nothing wrong".
* An assessment that could not reach a model has run six of its nine checks. It
  has therefore found *fewer* things, and the caveat travels with the verdict.
"""

from __future__ import annotations

from sc import db

#: The stages a submission passes through, in order. Named here so the portal
#: renders a fixed spine rather than whatever happened to be reachable.
STAGES: tuple[str, ...] = ("received", "carried", "ingested", "recorded",
                           "judged", "read", "case", "verdict")


def _row(submission_id: str):
    return db.one("SELECT * FROM submissions WHERE id = ?", (submission_id,))


def recent(supplier: str, limit: int = 50) -> list[dict]:
    """This supplier's submissions, newest first."""
    rows = db.query(
        "SELECT * FROM submissions WHERE supplier_id = ?"
        " ORDER BY wall_at DESC LIMIT ?", (supplier, limit))
    return [{
        "submission_id": r["id"],
        "kind": r["kind"],
        "system": r["system_id"],
        "submitted_at": r["submitted_at"],
        "wall_at": r["wall_at"],
        "doc_ref": r["doc_ref"],
        "entities": db.loads(r["entity_ids"]),
        "events": db.loads(r["event_ids"]),
        "files": db.loads(r["files"]),
        "note": r["note"],
        "effective_from": r["effective_from"],
    } for r in rows]


def status(supplier: str, submission_id: str) -> dict:
    """Every stage one submission reached, each read from its own table."""
    row = _row(submission_id)
    if row is None:
        return {"error": f"no submission {submission_id}"}
    if row["supplier_id"] != supplier:
        return {"error": f"{submission_id} does not belong to {supplier}"}

    event_ids = db.loads(row["event_ids"])
    entity_ids = db.loads(row["entity_ids"])
    stages = [
        _received(row, event_ids),
        _carried(event_ids),
        _ingested(event_ids),
        _recorded(row),
        _judged(event_ids, entity_ids),
        _read(event_ids),
        _case(event_ids, entity_ids),
        _verdict(entity_ids),
    ]
    return {
        "submission_id": submission_id,
        "supplier": supplier,
        "kind": row["kind"],
        "system": row["system_id"],
        "doc_ref": row["doc_ref"],
        "entities": entity_ids,
        "stages": stages,
        "reached": [s["stage"] for s in stages if s["done"]],
    }


def _stage(name: str, done: bool, detail: str, **extra) -> dict:
    return {"stage": name, "done": done, "detail": detail, **extra}


def _received(row, event_ids: list[str]) -> dict:
    return _stage(
        "received", True,
        f"{row['kind'].replace('_', ' ').lower()} received through "
        f"{row['system_id']}",
        at=row["submitted_at"], wall_at=row["wall_at"], events=event_ids,
        files=db.loads(row["files"]))


def _carried(event_ids: list[str]) -> dict:
    rows = [db.one("SELECT * FROM arrivals WHERE event_id = ?", (e,))
            for e in event_ids]
    found = [r for r in rows if r is not None]
    if not found:
        return _stage("carried", False, "no arrival recorded yet")
    first = found[0]
    return _stage("carried", True,
                  f"arrived through {first['system_id']} in batch "
                  f"{first['batch_id']}",
                  system=first["system_id"], batch=first["batch_id"],
                  arrived_at=first["arrived_at"],
                  defects=db.loads(first["defects"]))


def _ingested(event_ids: list[str]) -> dict:
    from sc.replay import ingest, tape

    if not event_ids:
        return _stage("ingested", False, "nothing to ingest")
    seqs = [r["seq"] for r in db.query(
        "SELECT seq FROM events WHERE id IN (%s)"
        % ",".join("?" * len(event_ids)), tuple(event_ids))]
    watermark = ingest.cursor(tape.LANE_LIVE)
    done = bool(seqs) and max(seqs) <= watermark
    return _stage("ingested", done,
                  "accepted into the record" if done
                  else "not yet taken into the record",
                  watermark=watermark)


def _recorded(row) -> dict:
    """Which document version the store now holds in force."""
    doc_ref = row["doc_ref"] or ""
    doc_id = doc_ref.split(":")[0]
    if not doc_id:
        return _stage("recorded", False, "this submission asserts no document")

    from sc.replay import tape
    from sc.state import overlay as overlay_mod
    from sc.state import store

    fact = store.get("source_doc", doc_id, overlay_mod.ATTR_VERSION,
                     tape.sim_now(), tape.sim_now())
    held = getattr(fact, "value", None)
    expected = doc_ref.split(":")[-1]
    return _stage("recorded", held == expected,
                  f"{doc_id} {held} is the version in force" if held
                  else f"no version of {doc_id} is in force",
                  in_force=held, submitted=expected)


def _judged(event_ids: list[str], entity_ids: list[str]) -> dict:
    """Whether ingestion raised a correction, and if not, why not.

    A document version deliberately raises none - see the module docstring.
    Reporting that as "nothing wrong" would be the most misleading thing this
    screen could say to a supplier who has just corrected an allergen.
    """
    from sc.graph import nodes as graph_nodes
    from sc.replay import tape

    wanted = set(event_ids)
    signals = [s for s in graph_nodes._signals_in_force(tape.sim_now())
               if s.get("source_event_id") in wanted
               or set(s.get("entities") or []) & set(entity_ids)]
    if signals:
        return _stage("judged", True,
                      "; ".join(sorted({s.get("summary", "") for s in signals}))
                      or "a correction was raised",
                      signals=[{"kind": s.get("kind"), "id": s.get("id"),
                                "summary": s.get("summary")} for s in signals])
    return _stage("judged", False,
                  "awaiting extraction - the version is recorded, and what the "
                  "document says is read when a correction run reaches it",
                  awaiting_extraction=True)


def _read(event_ids: list[str]) -> dict:
    rows = db.query(
        "SELECT entity_id, ts FROM audit WHERE action = 'EXAMINE'"
        " AND entity_id IN (%s)" % ",".join("?" * max(len(event_ids), 1)),
        tuple(event_ids) or ("",))
    if not rows:
        return _stage("read", False, "no correction run has read it yet")
    return _stage("read", True, "read by a correction run", at=rows[0]["ts"])


def _case(event_ids: list[str], entity_ids: list[str]) -> dict:
    rows = db.query("SELECT id, thread_id, status, title, opened_at"
                    " FROM incidents ORDER BY opened_at DESC LIMIT 50")
    wanted = set(event_ids) | set(entity_ids)
    for row in rows:
        blob = db.dumps(dict(row))
        if any(token and token in blob for token in wanted):
            return _stage("case", True, f"{row['id']} is {row['status']}",
                          incident_id=row["id"], thread_id=row["thread_id"],
                          status=row["status"])
    return _stage("case", False, "no correction case has been opened on it")


def _verdict(entity_ids: list[str]) -> dict:
    """Whether the products this touched are fit to launch.

    Assessed without a model, so six checks of nine. The caveat is carried
    rather than dropped: a narrower result is not a clean one.
    """
    import sc.readiness as readiness
    from sc.state import baseline as baseline_mod

    base = baseline_mod.get()
    verdicts = []
    for entity_id in entity_ids:
        targets = ([entity_id] if entity_id in base.variants
                   else base.variants_of.get(entity_id, []))
        for variant_id in targets:
            summary = readiness.assess(variant_id, use_model=False)
            if summary is None:
                continue
            verdicts.append({
                "entity_id": variant_id,
                "sku": getattr(base.variants.get(variant_id), "sku", ""),
                "verdict": summary["verdict"],
                "findings": [f["detail"] for f in summary["findings"]],
                "checks_complete": summary["checks_complete"],
                "caveat": summary["caveat"],
            })

    if not verdicts:
        return _stage("verdict", False, "nothing assessable was touched")
    words = sorted({v["verdict"] for v in verdicts})
    return _stage("verdict", True, ", ".join(words), verdicts=verdicts)
