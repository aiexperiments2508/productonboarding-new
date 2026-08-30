"""Turning a system's profile into a delivery schedule.

The requirement is that ten systems deliver "in batches, at random times,
asynchronously". The invariant is that the same seed produces the same facts
and the same trace hash. Those pull against each other only if you read
"random" as "unpredictable to the program". Read it as "unpredictable to the
person watching", and both hold at once:

*   **What each system sends, in what batch, after what pause** is drawn here
    from the configured seed. Two rehearsals are identical.
*   **When those batches actually land** is a race between ten concurrent
    deliveries and is genuinely not predictable. The Ingest Fabric shows real
    interleaving because it is real.
*   **What the retailer believes afterwards** is decided by ingestion, which
    sorts by sequence. So the race is visible and cannot change the outcome.

The one thing this file must never do is call ``random`` or read a clock. A
schedule that depended on either would trade the reproducibility the audit
trail rests on for the appearance of liveness, which is a bad trade in both
directions: the demo gets less trustworthy and does not look any better.

Each system draws from its own named stream (``rng.stream``), so adding an
eleventh system does not reshuffle the ten before it. That property is worth
more than it sounds - without it, every change to the manifest invalidates
every recorded expectation about the ones that did not change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from sc import rng as rng_mod
from sc.estate.defects import Defect
from sc.estate.manifest import BY_ID, INDEX, SYSTEMS, System


def seed() -> int:
    """The seed the estate schedules against.

    The same one the seed pack was generated with, so the schedule and the tape
    it delivers cannot come from different worlds.
    """
    return int(os.environ.get("DATA_SEED", "20802"))


@dataclass(frozen=True)
class Batch:
    """One delivery from one system.

    ``after`` is a delay rather than an absolute time. An absolute schedule
    would have to be rebased every time the replay clock is paused, stepped or
    jumped, and the transport does all three; a delay survives all of them.
    """

    system_id: str
    #: Position of this batch within its own system's sequence, from 0.
    ordinal: int
    #: Sequence numbers of the events this batch carries, ascending.
    sequences: tuple[int, ...]
    #: Seconds to wait after the previous batch from the same system.
    after: float
    #: Defects stamped on this batch, per carried sequence. A sequence absent
    #: from this mapping arrived clean.
    defects: dict[int, tuple[Defect, ...]]

    @property
    def size(self) -> int:
        return len(self.sequences)


def schedule_for(system: System, sequences: list[int],
                 data_seed: int | None = None) -> list[Batch]:
    """Cut one system's events into batches, with pauses between them.

    ``sequences`` is whatever slice of the tape this system owns, in tape
    order. Batching never reorders within a system: a supplier that sends a
    correction and then withdraws it must be seen to do so in that order, and a
    shuffled batch would turn a withdrawal into a correction nobody withdrew.
    """
    draw = rng_mod.stream(data_seed if data_seed is not None else seed(),
                          "estate", system.id)
    lo, hi = system.batch_size
    pause_lo, pause_hi = system.interval

    batches: list[Batch] = []
    remaining = list(sequences)
    ordinal = 0
    while remaining:
        take = max(1, min(draw.randint(lo, hi), len(remaining)))
        carried = tuple(remaining[:take])
        remaining = remaining[take:]

        stamped: dict[int, tuple[Defect, ...]] = {}
        for sequence in carried:
            if system.defects and draw.chance(system.defect_rate):
                # One defect per payload, not a pile. A record with four things
                # wrong is not four times as informative - the first finding is
                # what a supplier acts on, and stacking them makes the answer
                # key unreadable without making validation harder.
                stamped[sequence] = (draw.pick(list(system.defects)),)

        batches.append(Batch(
            system_id=system.id,
            ordinal=ordinal,
            sequences=carried,
            # The first batch still waits: ten systems all delivering at t=0
            # is not an estate, it is a single load.
            after=round(draw.uniform(pause_lo, pause_hi), 3),
            defects=stamped,
        ))
        ordinal += 1

    return batches


def schedule(owned: dict[str, list[int]],
             data_seed: int | None = None) -> dict[str, list[Batch]]:
    """The whole estate's schedule, keyed by system.

    Systems are walked in manifest order so the result is stable; each draws
    from its own stream so the order does not affect any individual schedule.
    """
    return {
        system.id: schedule_for(system, owned.get(system.id, []), data_seed)
        for system in SYSTEMS
    }


def timeline(plan: dict[str, list[Batch]]) -> list[tuple[float, float, str, int]]:
    """Every batch laid on one clock, as (start, end, system, size).

    Used to show - and to test - that the estate genuinely overlaps. A schedule
    where no two systems are ever in flight at once is a queue being drained
    with extra steps, and would not be worth the words spent on it.
    """
    spans: list[tuple[float, float, str, int]] = []
    for system_id, batches in plan.items():
        at = 0.0
        for batch in batches:
            start = at + batch.after
            # A batch is not instantaneous: it is a request carrying several
            # events. Modelled as a short span so overlap means what a reader
            # thinks it means.
            end = start + 0.25 + 0.05 * batch.size
            spans.append((round(start, 3), round(end, 3), system_id, batch.size))
            at = start
    return sorted(spans, key=lambda s: (s[0], INDEX[s[2]]))


def overlaps(plan: dict[str, list[Batch]]) -> list[tuple[str, str]]:
    """Pairs of systems whose batches are ever in flight at the same moment."""
    spans = timeline(plan)
    found: set[tuple[str, str]] = set()
    for i, (start_a, end_a, sys_a, _) in enumerate(spans):
        for start_b, end_b, sys_b, _ in spans[i + 1:]:
            if start_b >= end_a:
                break
            if sys_a != sys_b and start_b < end_a and start_a < end_b:
                found.add(tuple(sorted((sys_a, sys_b))))  # type: ignore[arg-type]
    return sorted(found)


def owner_of(event_type: str, source: str, sequence: int,
             data_seed: int | None = None) -> str:
    """Which system carried an event.

    The tape records a coarse origin - a portal, a mailbox, the PIM - from
    before the estate existed. Several systems can be the origin of the same
    event type, so this settles which one, deterministically from the sequence
    rather than by sampling, so that re-reading the tape never reassigns an
    event to a different system.

    Falls back to the first declared emitter rather than raising: an event type
    nobody claims is a gap in the manifest, and the right time to notice it is
    in the manifest test, not in the middle of a run.
    """
    from sc.estate.manifest import emitters_of

    candidates = emitters_of(event_type)
    if not candidates:
        return SYSTEMS[0].id

    # Only one origin on the tape is genuinely one system. "CHANNEL_GATEWAY" is
    # the channel side talking back, and there is exactly one connector.
    #
    # The others are deliberately *not* pinned. The tape records a coarse
    # origin from before the estate existed, and four fifths of it says
    # "SUPPLIER_PORTAL" - pinning that would hand one system eighty per cent of
    # the traffic and leave the estate looking like one pipe with nine
    # decorations beside it. A supplier feed genuinely can arrive through the
    # portal, the supplier's own PIM, the ERP or the data pool, so it is dealt
    # among the systems that declare they emit it.
    if source == "CHANNEL_GATEWAY":
        connector = next((s.id for s in candidates
                          if "CHANNEL_STATUS" in s.emits), None)
        if connector and event_type == "CHANNEL_STATUS":
            return connector

    # Deterministic in the sequence, so re-reading the tape never reassigns an
    # event to a different system - which would silently rewrite who was to
    # blame for a defect recorded an hour ago.
    draw = rng_mod.stream(data_seed if data_seed is not None else seed(),
                          "owner", event_type, sequence)
    return draw.pick([s.id for s in candidates])
