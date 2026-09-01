"""Onboarding a batch of products a supplier sent in one bundle.

The stages, in the order a batch moves through them:

*   ``batch``    - which products a bundle touched, read back from its submission
*   ``assess``   - the sequential pass over those products, one at a time
*   ``gate``     - the compliance and policy check that stops one before it starts
*   ``fixable``  - which gaps have a source passage on file, decided without a model
*   ``history``  - what the catalog and past decisions already say about a gap
*   ``suggest``  - a proposed value and the score it was composed from
*   ``decide``   - the threshold, the routing, and a category manager's answer
*   ``fix``      - the only writer, and the two doors it writes through

**The gate is first and it stops things.** A product that breaches a regulation
or the retailer's own policy goes back to its supplier without being onboarded:
nothing retrieves a source for it, nothing proposes a value for it, and nothing
downstream spends anything on it. Everything after the gate is about a record
that may lawfully be sold and is merely incomplete.

**Nothing is written on a model's own confidence.** ``suggest`` composes a score
from a discounted self-report plus counts of what is already on file; ``decide``
routes on that score against a threshold held in config; ``fix`` writes what
clears it, INFERRED, and queues the rest for a person. A safety-class attribute
never clears, whatever agrees with it.

Deliberately not a LangGraph run. The correction graph answers *a published
value changed, what does it reach*; onboarding asks *is this record fit to
launch*, which is what the readiness checks already answer, deterministically
and in milliseconds. Working forty new products through a graph that ends at an
approval interrupt would leave forty suspended threads and forty pending
approvals in a queue that exists to hold one.
"""
