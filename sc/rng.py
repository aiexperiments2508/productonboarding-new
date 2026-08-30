"""The deterministic PRNG, in one place.

Implemented rather than taken from ``random`` because CPython does not
guarantee that ``shuffle`` and ``sample`` keep their algorithms across
versions, and "identical on every machine" is the whole point: a demo
rehearsed on Friday has to behave identically on Sunday, on somebody else's
laptop, on a different Python.

mulberry32. Small, fast, well-distributed enough for scheduling and sampling,
and - the property that matters here - specified by its arithmetic rather than
by an implementation.

This lived in ``scripts/generate_data.py`` while the generator was the only
thing that needed it. The estate emitter now needs the same stream: a batch
schedule that a test can reproduce is the only thing standing between
"deliveries arrive at irregular times" and "the run is not reproducible". Two
copies of a PRNG are two PRNGs the first time somebody fixes a bug in one.
"""

from __future__ import annotations


class Rng:
    __slots__ = ("state",)

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFF

    def next(self) -> float:
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF
        t = self.state
        t = (t ^ (t >> 15)) * (t | 1) & 0xFFFFFFFF
        t ^= (t + ((t ^ (t >> 7)) * (t | 61) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    def uniform(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self.next()

    def randint(self, lo: int, hi: int) -> int:
        return lo + int(self.next() * (hi - lo + 1))

    def pick(self, items: list):
        return items[int(self.next() * len(items))]

    def chance(self, p: float) -> bool:
        return self.next() < p


def stream(seed: int, *parts: object) -> Rng:
    """A named stream off one seed.

    Every caller that wants its own reproducible sequence takes one of these
    rather than sharing a single generator. Sharing is what makes a schedule
    depend on how many times something *else* drew from the same stream, so
    adding a system would silently reshuffle every system before it.

    The name is folded in with a stable hash of its own rather than Python's
    ``hash``, which is salted per process and would make this the one function
    in the file that is not reproducible.
    """
    mixed = seed & 0xFFFFFFFF
    for part in parts:
        for byte in str(part).encode("utf-8"):
            mixed = (mixed * 31 + byte) & 0xFFFFFFFF
    return Rng(mixed)
