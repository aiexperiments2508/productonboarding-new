"""Bitemporal fact store.

The brief asks the system to cope with "late or corrected information" and to
keep recorded facts distinct from AI inferences, human decisions, simulated
outcomes and committed actions. Both fall out of one table shape plus one
query rule.

Two independent time axes:

*  **valid time**    (``valid_from`` / ``valid_to``) - when the assertion is
   true in the world.
*  **recorded time** (``recorded_at``) - when this system learned it.

The query rule: among rows whose valid interval covers the asked-for valid
instant and whose ``recorded_at`` is at or before the asked-for recording
instant, the one with the greatest ``recorded_at`` wins.

That single rule gives corrections for free. A correction is just another row
with a later ``recorded_at``; it wins from the moment it arrives and not one
instant earlier. Ask with ``as_of_recorded`` set to before it landed and you
see exactly what the content team saw when they wrote the copy.
``supersedes_id`` records the lineage for display, but the query does not need
it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Iterable

from sc import db
from sc.contracts import Fact, Provenance, ProvenanceKind

# Far-future sentinel so open-ended intervals compare correctly as ISO strings
# without a NULL branch in every WHERE clause.
_OPEN = "9999-12-31T23:59:59"


def _new_id() -> str:
    return f"F-{uuid.uuid4().hex[:12]}"


def record(
    entity_type: str,
    entity_id: str,
    attr: str,
    value: Any,
    valid_from: datetime,
    provenance: Provenance,
    valid_to: datetime | None = None,
    recorded_at: datetime | None = None,
    supersedes_id: str | None = None,
    conn=None,
) -> str:
    """Insert one fact. Returns its id.

    Never updates an existing row - that is the whole point. Pass ``conn`` to
    enlist in a caller's transaction (event consumers do this so the fact and
    their cursor advance atomically).
    """
    fact_id = _new_id()
    c = conn or db.connect()
    c.execute(
        "INSERT INTO facts (id, entity_type, entity_id, attr, value, valid_from,"
        " valid_to, recorded_at, supersedes_id, provenance)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            fact_id,
            entity_type,
            entity_id,
            attr,
            db.dumps(value),
            valid_from.isoformat(),
            valid_to.isoformat() if valid_to else None,
            (recorded_at or datetime.now()).isoformat(),
            supersedes_id,
            db.dumps(provenance),
        ),
    )
    if conn is None:
        c.commit()
    return fact_id


def correct(
    fact_id: str,
    value: Any,
    provenance: Provenance,
    recorded_at: datetime | None = None,
    valid_from: datetime | None = None,
    valid_to: datetime | None = None,
    conn=None,
) -> str:
    """Supersede an existing fact with a corrected value.

    Inherits the original's validity window unless overridden - the common case
    is "same period, different number" (a supplier restates a quantity), but a
    correction may also narrow the window (the delay starts later than first
    reported).
    """
    row = db.one("SELECT * FROM facts WHERE id = ?", (fact_id,))
    if row is None:
        raise KeyError(f"no such fact: {fact_id}")

    return record(
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        attr=row["attr"],
        value=value,
        valid_from=valid_from or datetime.fromisoformat(row["valid_from"]),
        valid_to=valid_to
        or (datetime.fromisoformat(row["valid_to"]) if row["valid_to"] else None),
        recorded_at=recorded_at,
        provenance=provenance,
        supersedes_id=fact_id,
        conn=conn,
    )


def _row_to_fact(row) -> Fact:
    return Fact(
        id=row["id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        attr=row["attr"],
        value=db.loads(row["value"]),
        valid_from=datetime.fromisoformat(row["valid_from"]),
        valid_to=datetime.fromisoformat(row["valid_to"]) if row["valid_to"] else None,
        recorded_at=datetime.fromisoformat(row["recorded_at"]),
        supersedes_id=row["supersedes_id"],
        provenance=Provenance.model_validate(db.loads(row["provenance"])),
    )


_ASOF_PREDICATE = (
    " valid_from <= :vt"
    " AND COALESCE(valid_to, :open) > :vt"
    " AND recorded_at <= :rt"
)


def get(
    entity_type: str,
    entity_id: str,
    attr: str,
    as_of_valid: datetime,
    as_of_recorded: datetime | None = None,
) -> Fact | None:
    """The single-fact as-of query.

    ``as_of_recorded`` defaults to now, i.e. "everything we currently know".
    Set it to a past instant to reconstruct what was believed then.
    """
    row = db.one(
        "SELECT * FROM facts WHERE entity_type = :et AND entity_id = :ei"
        " AND attr = :attr AND" + _ASOF_PREDICATE +
        " ORDER BY recorded_at DESC, id DESC LIMIT 1",
        {
            "et": entity_type,
            "ei": entity_id,
            "attr": attr,
            "vt": as_of_valid.isoformat(),
            "rt": (as_of_recorded or datetime.now()).isoformat(),
            "open": _OPEN,
        },
    )
    return _row_to_fact(row) if row else None


def get_value(
    entity_type: str,
    entity_id: str,
    attr: str,
    as_of_valid: datetime,
    as_of_recorded: datetime | None = None,
    default: Any = None,
) -> Any:
    fact = get(entity_type, entity_id, attr, as_of_valid, as_of_recorded)
    return fact.value if fact else default


def get_many(
    entity_type: str,
    as_of_valid: datetime,
    as_of_recorded: datetime | None = None,
    attr: str | None = None,
    entity_ids: Iterable[str] | None = None,
) -> list[Fact]:
    """Bulk as-of read: the winning fact per (entity_id, attr).

    The window function does the "greatest recorded_at wins" selection in one
    pass, which keeps a whole-network snapshot to a single query rather than
    one per entity.
    """
    params: dict[str, Any] = {
        "et": entity_type,
        "vt": as_of_valid.isoformat(),
        "rt": (as_of_recorded or datetime.now()).isoformat(),
        "open": _OPEN,
    }
    clauses = ["entity_type = :et", _ASOF_PREDICATE.strip()]
    if attr is not None:
        clauses.append("attr = :attr")
        params["attr"] = attr
    if entity_ids is not None:
        ids = list(entity_ids)
        if not ids:
            return []
        keys = [f"e{i}" for i in range(len(ids))]
        clauses.append(f"entity_id IN ({','.join(':' + k for k in keys)})")
        params.update(dict(zip(keys, ids)))

    sql = (
        "SELECT * FROM ("
        "  SELECT *, ROW_NUMBER() OVER ("
        "    PARTITION BY entity_id, attr ORDER BY recorded_at DESC, id DESC"
        "  ) AS rn"
        f"  FROM facts WHERE {' AND '.join(clauses)}"
        ") WHERE rn = 1 ORDER BY entity_id, attr"
    )
    return [_row_to_fact(r) for r in db.query(sql, params)]


def lineage(fact_id: str) -> list[Fact]:
    """Walk the correction chain back to the original assertion.

    Drives the "this was corrected" disclosure in the evidence cards - a
    reviewer seeing a revised value can see what it replaced and when.
    """
    chain: list[Fact] = []
    seen: set[str] = set()
    current: str | None = fact_id
    while current and current not in seen:
        seen.add(current)
        row = db.one("SELECT * FROM facts WHERE id = ?", (current,))
        if row is None:
            break
        chain.append(_row_to_fact(row))
        current = row["supersedes_id"]
    return chain


def corrections_since(recorded_after: datetime) -> list[Fact]:
    """Facts that arrived late and overrode something.

    The monitor uses this to decide whether a live recovery run is now working
    from stale evidence and needs to re-investigate.
    """
    rows = db.query(
        "SELECT * FROM facts WHERE supersedes_id IS NOT NULL AND recorded_at > ?"
        " ORDER BY recorded_at",
        (recorded_after.isoformat(),),
    )
    return [_row_to_fact(r) for r in rows]


def counts_by_provenance() -> dict[str, int]:
    """Powers the provenance mix shown in the audit view."""
    rows = db.query(
        "SELECT json_extract(provenance, '$.kind') AS kind, COUNT(*) AS n"
        " FROM facts GROUP BY kind"
    )
    return {r["kind"]: r["n"] for r in rows}


__all__ = [
    "record",
    "correct",
    "get",
    "get_value",
    "get_many",
    "lineage",
    "corrections_since",
    "counts_by_provenance",
    "ProvenanceKind",
]
