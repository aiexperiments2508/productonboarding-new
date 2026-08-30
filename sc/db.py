"""SQLite access layer.

One database file, WAL mode, no server process. Connections are per-thread
because SQLite objects are not shareable across threads and FastAPI runs
handlers in a threadpool.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

_local = threading.local()

# Every connection ever handed out, so they can all be closed. Connections are
# thread-local, and the graph fans simulations out across a threadpool - each
# worker opens its own and never gets a chance to close it. Without a registry
# those handles live until the process exits, which leaks file handles in a
# long run and blocks the database file from being replaced on Windows.
_all_connections: list[sqlite3.Connection] = []
_registry_lock = threading.Lock()

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def db_path() -> Path:
    return Path(os.environ.get("DB_PATH", "data/factory.db"))


def _configure(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    # NORMAL is the right durability/speed trade for a demo workload: still
    # crash-safe under WAL, without fsync on every commit.
    conn.execute("PRAGMA synchronous = NORMAL")


def connect() -> sqlite3.Connection:
    """Thread-local connection, created on first use."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        _configure(conn)
        _local.conn = conn
        with _registry_lock:
            _all_connections.append(conn)
    return conn


def close() -> None:
    """Close this thread's connection."""
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        with _registry_lock:
            if conn in _all_connections:
                _all_connections.remove(conn)
        _local.conn = None


def close_all() -> None:
    """Close every connection, from whichever thread opened it.

    Needed before the database file can be replaced: a worker thread from an
    earlier graph run still holds a handle, and Windows refuses to unlink a
    file that any process has open.
    """
    with _registry_lock:
        connections, _all_connections[:] = list(_all_connections), []
    for conn in connections:
        try:
            conn.close()
        except Exception:
            pass
    _local.conn = None


def init_db(drop: bool = False) -> None:
    """Apply the schema. Idempotent unless ``drop`` is set."""
    if drop:
        close_all()
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path()) + suffix)
            if p.exists():
                p.unlink()
    conn = connect()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


class transaction:
    """Context manager for an immediate write transaction.

    ``BEGIN IMMEDIATE`` takes the write lock up front rather than on first
    write, so two concurrent writers serialise here instead of one failing
    partway through with SQLITE_BUSY.
    """

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self.conn = conn or connect()

    def __enter__(self) -> sqlite3.Connection:
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        return False


# ---------------------------------------------------------------------------
# JSON / datetime helpers
#
# SQLite stores everything as TEXT here. Centralising the encoding keeps the
# round-trip lossless and stops each module inventing its own date format.
# ---------------------------------------------------------------------------


def _default(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    raise TypeError(f"not JSON serialisable: {type(obj).__name__}")


def dumps(obj: Any) -> str:
    # sort_keys matters: cache keys and trace hashes are built from JSON, and
    # dict ordering must not change the digest.
    return json.dumps(obj, default=_default, sort_keys=True, separators=(",", ":"))


def loads(text: str) -> Any:
    return json.loads(text)


def iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def query(sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
    return connect().execute(sql, params).fetchall()


def one(sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
    return connect().execute(sql, params).fetchone()


def iter_rows(sql: str, params: tuple | dict = ()) -> Iterator[sqlite3.Row]:
    cur = connect().execute(sql, params)
    while True:
        rows = cur.fetchmany(500)
        if not rows:
            return
        yield from rows


# ---------------------------------------------------------------------------
# Runtime config
# ---------------------------------------------------------------------------


def get_config(key: str, default: str | None = None) -> str | None:
    row = one("SELECT value FROM runtime_config WHERE key = ?", (key,))
    return row["value"] if row else default


def set_config(key: str, value: str) -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO runtime_config (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
        "updated_at = excluded.updated_at",
        (key, value, datetime.now().isoformat()),
    )
    conn.commit()
