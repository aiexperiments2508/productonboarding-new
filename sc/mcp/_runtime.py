"""Shared plumbing for the toolset servers: the call log, and the decorator.

Splitting one server into six only means something if you can see the split.
Every tool call is recorded here with the toolset it belongs to, so the console
can show traffic crossing a boundary rather than asking anyone to take the
partition on trust.

The log is deliberately in-memory and bounded. It is an observability aid for
a demo, not an audit trail - the audit trail is the append-only ledger in
SQLite, and confusing the two would be a mistake in the direction that
matters.
"""

from __future__ import annotations

import functools
import time
from collections import deque
from threading import Lock
from typing import Any, Callable

from sc.mcp.registry import owner_of

# Enough to cover a demo run several times over. Older entries fall off the
# back rather than growing without limit in a long-lived process.
MAX_CALLS = 300

_calls: deque[dict] = deque(maxlen=MAX_CALLS)
_lock = Lock()
_seq = 0


def record(tool: str, transport: str, ms: float, ok: bool,
           detail: str = "") -> dict:
    """Note one tool invocation. Returns the entry, mostly for tests."""
    global _seq
    with _lock:
        _seq += 1
        entry = {
            "seq": _seq,
            "at": time.time(),
            "tool": tool,
            "toolset": owner_of(tool),
            # "in-process" or "stdio". The difference is the whole point of
            # the switch, so it is recorded rather than inferred.
            "transport": transport,
            "ms": round(ms, 2),
            "ok": ok,
            "detail": detail[:200],
        }
        _calls.append(entry)
    return entry


def calls(limit: int = 60) -> list[dict]:
    """Most recent first."""
    with _lock:
        return list(reversed(list(_calls)))[:limit]


def clear() -> None:
    with _lock:
        _calls.clear()


def counts() -> dict[str, int]:
    """Calls per toolset, for the console's summary row."""
    out: dict[str, int] = {}
    with _lock:
        for entry in _calls:
            out[entry["toolset"]] = out.get(entry["toolset"], 0) + 1
    return out


def instrumented(fn: Callable[..., Any], *,
                 transport: str = "in-process") -> Callable[..., Any]:
    """Wrap a tool so every call through it lands in the log.

    Applied at the MCP boundary rather than inside ``sc/tools``, because the
    point is to record *crossings*. The graph calling the same function
    directly is not a crossing and should not appear as one.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - recorded, then re-raised
            record(fn.__name__, transport,
                   (time.perf_counter() - started) * 1000, False, str(exc))
            raise
        record(fn.__name__, transport,
               (time.perf_counter() - started) * 1000, True)
        return result

    return wrapper


def serve(mcp, toolset_id: str) -> None:
    """Run one toolset over stdio.

    Every server module ends in a call to this, which is what makes each of
    them independently runnable - the property the whole partition rests on.
    """
    import argparse
    import json
    import sys

    from sc.mcp.registry import BY_ID

    parser = argparse.ArgumentParser(description=BY_ID[toolset_id].title)
    parser.add_argument("--list", action="store_true",
                        help="print this toolset and exit")
    args = parser.parse_args()

    if args.list:
        toolset = BY_ID[toolset_id]
        json.dump({"id": toolset.id, "title": toolset.title,
                   "owner": toolset.owner, "tools": list(toolset.tools),
                   "mutating": list(toolset.mutating)},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    mcp.run()
