"""Which products a bundle touched, read back from its submission.

There is no batch table, and there is deliberately not going to be one. A
bundle is already a submission: ``sc.estate.submissions`` records its id, its
supplier, the system it arrived through, every event it appended and every
entity it named. The batch id *is* the submission id, so there is no second
identifier to keep in step with the first.

The rule this respects is narrower than "derived state is not stored".
``submissions`` refuses a stored **status** and a stored **verdict** - the
decisions that could disagree with the record - and happily stores the
submission's own facts. Which entities arrived together is a fact about what
happened, not a judgement about it, and it is already a column.

So nothing here caches a count. Every number in the report is recomputed from
``readiness.assess`` on every read, exactly as ``/api/products/summary`` does,
which is what makes a report reopened after a fix show the new figures rather
than the ones somebody stored.
"""

from __future__ import annotations

from sc import db
from sc.estate.intake import DATA_PACK, PRODUCT_DRAFT


def recent(limit: int = 20) -> list[dict]:
    """The bundles, newest first."""
    rows = db.query(
        "SELECT * FROM submissions WHERE kind = ?"
        " ORDER BY wall_at DESC LIMIT ?", (DATA_PACK, limit))
    return [_row(r) for r in rows]


def get(submission_id: str) -> dict | None:
    row = db.one("SELECT * FROM submissions WHERE id = ? AND kind = ?",
                 (submission_id, DATA_PACK))
    return _row(row) if row is not None else None


def entities(submission_id: str) -> list[str]:
    """The variants this bundle asserted against, in the file's own order."""
    batch = get(submission_id)
    return list(batch["entities"]) if batch else []


def latest() -> dict | None:
    """The newest bundle, for a screen that wants to open on something."""
    found = recent(limit=1)
    return found[0] if found else None


def proposals(submission_id: str) -> list[dict]:
    """The new lines this bundle proposed, still waiting on a reviewer.

    Read from the drafts surface rather than from the bundle's own record, so
    a proposal that has since been accepted stops being listed here without
    anything having to be updated - the ledger is the authority on what was
    decided, as it is everywhere else.
    """
    from sc.lifecycle import drafts as drafts_mod

    return [d for d in drafts_mod.pending()
            if (d.get("note") or "").endswith(submission_id)]


def _row(row) -> dict:
    files = db.loads(row["files"]) or []
    return {
        "batch_id": row["id"],
        "submission_id": row["id"],
        "supplier": row["supplier_id"],
        "system": row["system_id"],
        "submitted_at": row["submitted_at"],
        "wall_at": row["wall_at"],
        "doc_ref": row["doc_ref"],
        "note": row["note"] or "",
        "entities": db.loads(row["entity_ids"]) or [],
        "event_ids": db.loads(row["event_ids"]) or [],
        # The archive itself, kept because a reviewer arguing about what a
        # supplier sent needs the artefact rather than our reading of it.
        "file": next((f for f in files
                      if str(f.get("path", "")).find("/packs/") != -1), None),
        "images": [f for f in files
                   if str(f.get("path", "")).find("/media/") != -1],
        "proposals": proposals(row["id"]),
    }
