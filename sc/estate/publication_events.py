"""Telling the application that published state moved.

The write path - ``sc.tools.planning`` and ``sc.estate.redaction`` - imports
nothing from ``sc.main`` and must not start. That module mounts the estate, so
the import would be a cycle; more to the point, a correction has to be
committable from a script, a test or the graph without a web process existing
to be told about it.

So the write path calls ``notify`` and does not care whether anybody is
listening. The application subscribes at startup and turns each message into a
server-sent event.

Messages name what happened and let the reader re-read, following the same
discipline the topology notifications already use: carrying a whole projection
of published state in the message would be a second account of it, and the
first thing that second account would disagree about is the redaction somebody
committed while it was in flight.
"""

from __future__ import annotations

import logging
from typing import Callable

log = logging.getLogger(__name__)

_subscriber: Callable[[str, dict], None] | None = None


def subscribe(callback: Callable[[str, dict], None] | None) -> None:
    """Register the one listener. Called by the application at startup."""
    global _subscriber
    _subscriber = callback


def notify(kind: str, payload: dict) -> None:
    """Announce a change to published state. Never raises.

    A reader that cannot be told is a worse panel, not a failed commit - and
    this is called from inside the code path that has just changed what a
    shopper sees, which is the last place an exception should be able to
    originate.
    """
    if _subscriber is None:
        return
    try:
        _subscriber(kind, payload)
    except Exception:  # noqa: BLE001 - a display concern must not fail a write
        log.debug("could not publish a %s notification", kind, exc_info=True)
