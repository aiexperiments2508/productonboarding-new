"""Shared test setup.

Every test module gets its own database file. Without this they share one,
because ``DB_PATH`` is read from the environment at call time and the modules
set it with ``setdefault`` at import - whichever module imported first wins,
and the others silently operate on its database. The symptom is nasty: each
module passes alone and fails in a full run, because one module's ``drop=True``
wipes another's fixtures out from under it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sc import db

DATA = Path("data")


def _module_name(request) -> str:
    return request.node.module.__name__.rsplit(".", 1)[-1]


@pytest.fixture(autouse=True)
def isolate_database(request, monkeypatch):
    """Pin DB_PATH to this test's module for the duration of the test."""
    name = _module_name(request)
    monkeypatch.setenv("DB_PATH", str(DATA / f"{name}.db"))
    monkeypatch.setenv("ENV_FILE", str(DATA / f"{name}.env"))

    # Connections are thread-local and cached; a handle opened against the
    # previous module's file would otherwise still be in play.
    db.close_all()
    yield
    db.close_all()


def pytest_sessionfinish(session, exitstatus):
    """Remove the per-module artefacts a run leaves behind."""
    for pattern in ("test_*.db", "test_*.db-wal", "test_*.db-shm",
                    "test_*.env", "test_*.npy", "test_*.checkpoints.db*"):
        for path in DATA.glob(pattern):
            try:
                path.unlink()
            except OSError:
                pass
