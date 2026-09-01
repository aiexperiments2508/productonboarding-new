"""Recording what the estate delivered.

The tape decides *what* exists and when it becomes visible. This decides *who
carried it* and *in which batch*, and writes that down.

Kept apart from `tape.py` on purpose. The tape is the world's script - it would
be the same script if the retailer had one supplier and no integrations at all.
The estate is the set of pipes the script arrives through, and conflating the
two is how the MVP ended up with four suppliers standing in for ten systems.

The delivery is recorded, not simulated with sleeps. A batch that took two
seconds of real time to "arrive" would make the replay transport lie: an
operator who jumps to the inject expects to be at the inject, not two minutes
of pretend network away from it. What is faithful here is the *grouping* -
which system sent what, in what batch, with what stamped on it - and that is
what the estate panel renders and what the answer key is built from.
"""

from __future__ import annotations

from sc import db
from sc.contracts import Event
from sc.estate import arrivals, emitter, manifest
from sc.estate.manifest import SYSTEMS

#: Batch ordinals for the reference pack. `deliver` numbers from 0 and
#: `deliver_live` from 9000, so a band of its own makes a batch id readable as
#: reference traffic at a glance, without a lookup and without this module
#: having to name a system to say so.
REF_ORDINAL_BASE = 7000


def deliver(events: list[Event]) -> list[dict]:
    """Record a released window as arrivals from the systems that carried it.

    Events are dealt to their owning system, each system's share is cut into
    batches by its own seeded schedule, and each batch is written in one
    transaction. Ten producers against one SQLite writer is a contention
    problem the moment each event becomes its own commit.

    Idempotent: `arrivals.record` ignores an event it already holds, so
    re-releasing a window - which the replay transport does whenever somebody
    steps back and forward again - adds nothing and loses nothing.
    """
    if not events:
        return []

    owned: dict[str, list[int]] = {s.id: [] for s in SYSTEMS}
    ids: dict[int, str] = {}
    for event in events:
        system_id = emitter.owner_of(event.type, event.source, event.seq)
        owned.setdefault(system_id, []).append(event.seq)
        ids[event.seq] = event.id

    recorded: list[dict] = []
    for system_id, sequences in owned.items():
        if not sequences:
            continue
        system = next(s for s in SYSTEMS if s.id == system_id)
        for batch in emitter.schedule_for(system, sorted(sequences)):
            recorded.extend(arrivals.record(batch, ids))
    return recorded


def deliver_live(system_id: str, events: list[Event]) -> list[dict]:
    """Record a submission as an arrival from the system it came through.

    Not ``deliver``, and the difference matters twice.

    ``emitter.owner_of`` *deals* an event among the systems that declare its
    type, deterministically but arbitrarily. That is right for the recording,
    where the tape only knows a coarse origin. It is wrong here: we know
    exactly which endpoint this arrived at, because the endpoint is what
    accepted it. Dealing it would tell a supplier who submitted through their
    own PIM that their data came from the industry data pool.

    ``emitter.schedule_for`` also stamps defects from the system's declared
    defect rate. Applied to a submission, the estate would tell a supplier that
    the form they had just filled in correctly arrived with a mandatory field
    missing - the estate lying about itself in the one place a supplier can
    check it.
    """
    if not events:
        return []

    from sc.replay import tape

    ordinal = 9000 + (min(e.seq for e in events) - tape.LIVE_BASE)
    batch = emitter.Batch(system_id=system_id, ordinal=max(ordinal, 9000),
                          sequences=tuple(sorted(e.seq for e in events)),
                          after=0.0, defects={})
    return arrivals.record(batch, {e.seq: e.id for e in events})


def deliver_reference(events: list[Event]) -> list[dict]:
    """Record the reference pack as arrivals from the systems that sent it.

    Follows ``deliver_live`` rather than ``deliver``, for the same two reasons
    and a third.

    The owner is *derived, not dealt*. ``emitter.owner_of`` shares an event
    among every system declaring its type, which is right for the recording
    where the tape knows only a coarse origin. Here exactly one system declares
    each of these types, so the manifest already answers the question and
    drawing for it would be a lottery with one ticket. Deriving it also keeps
    this file free of system-id literals - ``emitters_of`` is asked, so the
    manifest stays the only place they are written down.

    Nothing is defect-stamped. ``emitter.schedule_for`` stamps from a system's
    declared ``defect_rate``, and all four of these declare none - because no
    detector in ``sc/estate/detection.py`` can say anything true about a pallet
    count or a month's takings. A defect here would be an assertion no rule
    could check.

    And the batching is fixed rather than seeded. A reference pack is delivered
    once at bootstrap, not raced against the clock, so there is no interleaving
    to make visible and nothing for a random schedule to buy.
    """
    if not events:
        return []

    by_system: dict[str, dict[str, list[Event]]] = {}
    for event in events:
        origins = manifest.emitters_of(str(event.type))
        if not origins:
            # A type nothing declares has no carrier, so there is nobody to
            # attribute the arrival to. Silently dropping it would leave an
            # event that exists and cannot be read; this says so instead.
            raise ValueError(
                f"no system in the manifest emits {event.type!r} - "
                f"event {event.id} has no carrier")
        by_system.setdefault(origins[0].id, {})                  .setdefault(str(event.type), []).append(event)

    recorded: list[dict] = []
    ordinal = REF_ORDINAL_BASE
    for system_id in sorted(by_system):
        system = manifest.BY_ID[system_id]
        size = max(system.batch_size[1], 1)
        for event_type in sorted(by_system[system_id]):
            share = sorted(by_system[system_id][event_type],
                           key=lambda e: e.seq)
            for start in range(0, len(share), size):
                chunk = share[start:start + size]
                batch = emitter.Batch(
                    system_id=system_id, ordinal=ordinal,
                    sequences=tuple(e.seq for e in chunk),
                    after=0.0, defects={})
                recorded.extend(
                    arrivals.record(batch, {e.seq: e.id for e in chunk}))
                ordinal += 1
    return recorded


def backfill() -> list[dict]:
    """Record arrivals for everything already released.

    A database seeded before the estate existed, or one where the clock was
    jumped past the inject by a script, has released events and no arrivals.
    Rather than leaving the estate panel empty on a system that has plainly
    been running, this deals out what is already visible.

    The recorded flight only. A submission's arrival is written by
    ``deliver_live`` against the endpoint that accepted it, and re-dealing it
    here would hand it to whichever system the draw happened to pick.
    """
    rows = db.query(
        "SELECT * FROM events WHERE released_at IS NOT NULL AND lane = 'TAPE'"
        "  AND id NOT IN (SELECT event_id FROM arrivals) ORDER BY seq")
    if not rows:
        return []
    from sc.replay.tape import _row_to_event

    return deliver([_row_to_event(r) for r in rows])
