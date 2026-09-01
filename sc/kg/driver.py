"""The Neo4j connection, mirroring ``sc/db.py``.

Same job as that module and deliberately the same shape: lazy creation, one
handle held for the process, an explicit ``close_all`` so a test can let go of
it, and every setting read from the environment at call time rather than
captured at import. A reader who knows how ``sc/db.py`` works knows how this
works.

**The driver is imported inside functions, never at module scope.** ``neo4j``
lives in ``requirements-graph.txt``, not ``requirements.txt``, so a checkout
that has not installed it must still be able to import ``sc.kg`` - and it must
be able to *run*, on the in-process backend, with the tab working. An import at
the top of this file would turn an optional dependency into a required one via
the import graph, silently.

**Unreachable is a state, not an exception.** ``available()`` answers a
question; it does not raise. That is the same posture ``sc/mcp/connections.py``
takes for a system that does not answer, and for the same reason: a demo that
will not open because a database somebody never started is not answering has
failed at the one job it had.
"""

from __future__ import annotations

import logging
import os
import threading

log = logging.getLogger(__name__)

#: How long to wait deciding whether Neo4j is there. Short: this runs on the
#: first request of a session, and a reader staring at a spinner while a
#: hopeful TCP connection times out would rather have been told there is no
#: Neo4j and shown the graph anyway.
CONNECT_TIMEOUT = 3.0

_lock = threading.Lock()
_driver = None
_probe: tuple[bool, str] | None = None


def uri() -> str:
    return os.environ.get("NEO4J_URI", "").strip()


def database() -> str:
    return os.environ.get("NEO4J_DATABASE", "neo4j").strip() or "neo4j"


def safe_uri() -> str | None:
    """Host and port only. Credentials have no business in a response body."""
    raw = uri()
    if not raw:
        return None
    without_scheme = raw.split("://", 1)[-1]
    return without_scheme.rsplit("@", 1)[-1]


def _auth() -> tuple[str, str]:
    return (os.environ.get("NEO4J_USER", "neo4j").strip(),
            os.environ.get("NEO4J_PASSWORD", "").strip())


def driver():
    """The shared driver, created on first use. None when it cannot be made.

    Returns rather than raises so every caller can treat "no Neo4j" as an
    answer. The one place that must not is the loader, which says so loudly and
    exits - see ``scripts/load_graph.py``.
    """
    global _driver
    if not uri():
        return None
    with _lock:
        if _driver is not None:
            return _driver
        try:
            from neo4j import GraphDatabase
        except ImportError:
            log.debug("the neo4j driver is not installed; "
                      "pip install -r requirements-graph.txt")
            return None
        try:
            _driver = GraphDatabase.driver(
                uri(), auth=_auth(),
                connection_timeout=CONNECT_TIMEOUT,
                connection_acquisition_timeout=CONNECT_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            log.debug("could not build a neo4j driver: %s", exc)
            _driver = None
        return _driver


def available(refresh: bool = False) -> tuple[bool, str]:
    """Whether Neo4j is reachable, and why not when it is not.

    Probed once and remembered. A per-request handshake would put a network
    round trip in front of every page load to answer a question whose answer
    almost never changes within a session; ``refresh`` is for the one caller
    that has just changed something.
    """
    global _probe
    if _probe is not None and not refresh:
        return _probe

    if not uri():
        _probe = (False, "NEO4J_URI is not set")
        return _probe

    handle = driver()
    if handle is None:
        _probe = (False, "the neo4j driver is not installed or would not build")
        return _probe

    try:
        handle.verify_connectivity()
        _probe = (True, "")
    except Exception as exc:  # noqa: BLE001 - the reason is the useful part
        _probe = (False, f"{type(exc).__name__}: {str(exc)[:180]}")
    return _probe


def run(query, *, write: bool = False) -> list[dict]:
    """Run one ``GraphQuery`` and return its records as plain dicts.

    Takes the builder's own object rather than a string and a dict, so there is
    no call site that can pass a statement the builders never made.
    """
    handle = driver()
    if handle is None:
        raise RuntimeError("no neo4j driver")
    with handle.session(database=database(),
                        default_access_mode="WRITE" if write else "READ") as session:
        return [record.data() for record in session.run(query.cypher,
                                                        **query.params)]


def close_all() -> None:
    """Let go of the driver. Called by tests and at shutdown.

    ``sc/db.py`` needs this because Windows will not unlink an open file; here
    it is so a test that flips ``NEO4J_URI`` does not keep talking to the
    server the previous test pointed at.
    """
    global _driver, _probe
    with _lock:
        if _driver is not None:
            try:
                _driver.close()
            except Exception:  # noqa: BLE001 - shutting down either way
                log.debug("neo4j driver did not close cleanly", exc_info=True)
        _driver = None
        _probe = None
