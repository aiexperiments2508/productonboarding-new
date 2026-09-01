"""Shared test setup.

**Every test module gets its own database file.** Without this they share one,
because ``DB_PATH`` is read from the environment at call time and the modules
set it with ``setdefault`` at import - whichever module imported first wins,
and the others silently operate on its database. The symptom is nasty: each
module passes alone and fails in a full run, because one module's ``drop=True``
wipes another's fixtures out from under it.

**And its own accepted-lines extension.** ``data/catalog.live.json`` is merged
by every ``baseline.load``, and ``lifecycle.drafts.accept`` writes it. One
shared path is a product from one module's test appearing in another module's
catalog - which is the same failure as the shared database, one file further
out, and it survived this long only because the suite ran in one process at a
time. It does not any more; see below.

**The suite runs in parallel, distributed by file.** ``pytest.ini`` passes
``-n auto --dist loadfile``, and ``loadfile`` is load bearing rather than a
tuning choice: it guarantees every test in a module lands on the same worker,
which is what makes the per-module isolation above hold. Under the default
``--dist load`` two workers would take turns at one module's tests, both
pointed at ``data/test_thing.db``, and each ``drop=True`` would delete the
other's fixtures mid-run.

The one thing ``loadfile`` cannot isolate is a resource outside this repository:
``test_kg_neo4j`` writes to whatever Neo4j ``NEO4J_URI`` names. Keeping that
module on one worker is enough *within* a run, and it is why two pytest runs
must not overlap - which is worth knowing, because the failure looks like a
code bug rather than like two processes sharing a graph.

**The suite is disk-bound, so it runs SQLite unsafely.** Measured rather than
assumed: eight workers beat four, but neither came close to the eight-fold
speedup, which is what a disk rather than a CPU running out looks like. Each
test drops a database file, replays the schema and inserts the 5,225-event
tape, and journalling that durably was most of the cost. ``SQLITE_UNSAFE_FAST``
turns the journal and the fsync off for these throwaway files and takes the
per-test setup from 155ms to 64ms.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

#: Set before ``sc.db`` is imported, and before any test module's own imports
#: open a connection - a module-scoped fixture runs ahead of the autouse one
#: below, so pinning this inside the fixture would be too late for it.
#:
#: ``setdefault`` so a developer chasing a corruption bug can turn it off from
#: the shell without editing this file.
os.environ.setdefault("SQLITE_UNSAFE_FAST", "1")

from sc import db  # noqa: E402

DATA = Path("data")

#: Everything a run leaves behind, keyed on the module that made it. Kept as
#: one list because "what does a run write" is a question with an answer.
ARTEFACTS = ("test_*.db", "test_*.db-wal", "test_*.db-shm", "test_*.env",
             "test_*.npy", "test_*.checkpoints.db*", "test_*.live.json")


def _module_name(request) -> str:
    return request.node.module.__name__.rsplit(".", 1)[-1]


@pytest.fixture(autouse=True)
def isolate_database(request, monkeypatch):
    """Pin this module's own database, env file and catalog extension."""
    name = _module_name(request)
    monkeypatch.setenv("DB_PATH", str(DATA / f"{name}.db"))
    monkeypatch.setenv("ENV_FILE", str(DATA / f"{name}.env"))
    # Resolved inside the data directory by `baseline.extension_path`, so the
    # module still reads the one seed pack and writes only its own extension.
    monkeypatch.setenv("CATALOG_EXTENSION", f"{name}.live.json")

    # Connections are thread-local and cached; a handle opened against the
    # previous module's file would otherwise still be in play.
    db.close_all()
    yield
    db.close_all()


def pytest_sessionfinish(session, exitstatus):
    """Remove the per-module artefacts a run leaves behind.

    The controller only. A worker's session ends when the controller says the
    run is over, so cleaning up there would *usually* be harmless - but
    "usually" is the wrong property for a delete, and a worker that finished
    early deleting a database another worker still holds is a failure nobody
    would think to look for. One process, once, at the end.
    """
    if hasattr(session.config, "workerinput"):
        return

    for pattern in ARTEFACTS:
        for path in DATA.glob(pattern):
            try:
                path.unlink()
            except OSError:
                pass
