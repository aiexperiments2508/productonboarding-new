## Context

The event plane is a SQLite table with a per-consumer cursor. `ingest()` takes a
batch, sorts it by sequence, drops everything at or behind the cursor, writes
the facts and advances the cursor in the same transaction. That last property is
what makes redelivery after a crash safe, and it is better than what a broker
would give: the offset and the facts move together or neither does.

The cursor is a single watermark. This matters more than it looks, and it is the
first thing this change has to reckon with.

The map the UI draws is derived from the catalog on read - that requirement
already exists and is a good one - except for node coordinates, which the
generator writes into `catalog.json`. Four tiers at fixed x positions, y spread
evenly within each. A tier whose membership is only known at runtime cannot be
laid out that way.

The six toolsets are a frozen tuple of dataclasses, and nine tests read it
directly to assert things worth asserting: no tool on two toolsets, every
mutating tool declared by the toolset that exposes it, exactly one server able
to change what a channel sees.

## Goals / Non-Goals

**Goals:**

- Ten or more external systems, each a real MCP server over a real transport,
  each able to join and leave while the application is running.
- Deliveries that are genuinely asynchronous, batched and irregularly timed, and
  visibly so.
- Payloads that are sometimes wrong, in named ways, so that validation can be
  measured rather than demonstrated.
- The same seed still producing the same facts and the same `trace_hash`.
- The existing ownership invariants over the built-in toolsets left intact.

**Non-Goals:**

- A message broker. Considered and declined; the reasoning is under *Risks*.
- Systems that invent data at runtime. What each system delivers is scripted by
  the seed, because a demo that cannot be rehearsed is not a demo. The
  asynchrony is real; the content is written down.
- Letting a connected system's tools become callable by a model on connection.
  That is deliberately a separate, later decision.

## Decisions

**Delivery is asynchronous; ingestion is sequenced. These are different
boundaries and conflating them would lose events.** The obvious reading of
"systems push asynchronously" is that each system's batch goes straight to
`ingest()`. That silently drops data: the cursor is one watermark, so a system
delivering sequence 50 before another delivers 30 advances the cursor past 30,
and the second batch is discarded as already seen. Nothing would fail; facts
would simply be missing.

So the boundary moves. A system delivers into an **arrivals** record - the
system, the batch, the moment it landed, and the defects the payload carries.
The event plane then releases what has arrived into ingestion **in sequence
order**, exactly as the replay clock already does. Arrival is concurrent and out
of order; ingestion is ordered and unchanged. `ingest()` is not touched.

*Alternative considered.* A cursor per system, which the `event_cursors` table
would already support. It permits genuinely independent ingestion per system and
costs the one property that decides everything downstream: with ten independent
watermarks there is no longer a single answer to "what did the system know at
this instant", and the bitemporal record is built on there being one.

*What this buys, and it is worth being plain.* A real integration bus sequences.
Saying so is not a demo shortcut - it is the same answer Kafka gives inside a
partition, arrived at without a partition.

**Systems deliver a script, and the script is seeded.** Each system's emitter
reads its own slice of the tape and pushes it in batches whose size and spacing
come from the seeded generator, not from wall-clock randomness. Two rehearsals
therefore look different in their timing at the millisecond level and identical
in their outcome. A generator that rolled live dice would trade the
reproducibility the audit trail depends on for the appearance of liveness.

**The tape stays one ordered sequence, and every event names its system.**
Ordering is global, by simulated timestamp, ties broken by the system's index in
the manifest. Per-system sequence lanes were considered and rejected for the
same reason as per-system cursors: they make the global order a derived thing
rather than a recorded one.

**Conformance is a property of the system, and defects are named on the
arrival.** A profile says how a system misbehaves - omits a mandatory
attribute, sends a number as a string, uses its own vocabulary, breaks a
format, sends a stale document version, contradicts a higher-precedence source,
omits required media. The defect is stamped where it was introduced. This is
what turns "some data is erroneous" into something a test can assert, and it
gives the readiness work that follows an answer key it did not have to
hand-label.

**The built-in six are unchanged; discovered systems sit beside them.**
`TOOLSETS` keeps its type, its contents and its meaning, and the nine tests that
read it keep passing unmodified. A combined listing is what the API and the
console render. A discovered tool is owned by the system that declared it, and a
discovered name that collides with a built-in tool does not shadow it - the
built-in wins and the collision is reported, because a connected system quietly
redefining `commit_plan` is the failure this partition exists to prevent.

**Transport is a property of the connection.** `_Bridge` already holds one
session per toolset on a background loop; it now chooses between a spawned
module and an HTTP endpoint from the connection record. Streamable HTTP is the
primary form because it is what the current MCP specification defines; the older
HTTP+SSE transport is kept for a client that needs it. Nothing about `call()`
changes, and the in-process fallback stays exactly where it is.

**The map's coordinates are computed, not seeded.** Tier index gives x, position
within the live membership gives y. Removing coordinates from `catalog.json` is
what allows a tier whose size changes at runtime, and it removes a way for the
picture to disagree with the catalog.

**Disconnection degrades, it does not delete.** A system that goes away is
marked degraded. Its facts stay - they were true when they were recorded, and a
bitemporal store does not retract history because a connection dropped. Its
edges grey out, and any lookup routed to it falls back in-process the way a
failed toolset already does.

## Risks / Trade-offs

**Considered and declined: Kafka.** It is the obvious question for an estate of
ten asynchronous producers, and the answer is no, for two reasons stronger than
operational weight. First, it would lose a property this system has: the
consumer cursor advances in the same transaction as the facts it wrote, and a
broker splits that into an offset commit and a database write that cannot be
atomic - the dual-write problem, solved with idempotency keys that are already
here. Second, its ordering guarantee is per partition; ten systems on ten
partitions gives nondeterministic global interleaving, against an architecture
whose invariant is that the same seed yields the same `trace_hash`. Determinism
would be recovered by sorting on sequence at the consumer, which is what already
happens. MCP is also already the integration story, and a second one competes
with it for the same explanation.

**Ten producers, one SQLite writer.** WAL permits one writer with concurrent
readers, and the busy timeout absorbs contention at this volume. The emitter
must therefore write one transaction per batch rather than one per event. This
is a constraint to honour in the implementation, not a limit to discover during
a demo.

**Ten servers mounted in one process.** Mounting is cheap; a handshake per
connection at startup is not free. Connections are established lazily and in
parallel, and a system that fails to answer is recorded as degraded rather than
delaying the application's start. A demo that cannot boot because a mock
supplier was slow is a worse outcome than a demo missing one supplier.

**Named defects can drift from the validator.** A defect the generator stamps
and the validator does not detect is a lie in the answer key. The two are tied
together by a test that walks every stamped defect and asserts something
reports it.

## Migration Plan

The seed pack is regenerated, which the project already treats as routine -
`data/` is git-ignored and rebuilt by `scripts/generate_data.py`. The catalog
gains systems and every event names one; node coordinates leave. A database
carried over from before the change is reset the way any schema change here is
reset, with `python run.py --reset`.

The rename is a label change. The section identifier stays `tower`, so routing,
the command palette and every stored preference keyed on it are untouched.

## Open Questions

- Whether a connection should be able to declare its own conformance profile, so
  that a genuinely external server added from the UI can say what it is rather
  than being assumed well-behaved. Assumed well-behaved for now, and reported as
  unknown rather than as good.
- Whether arrivals should be retained after they are ingested, or trimmed. They
  are retained here because the Ingest Fabric shows them and because "when did
  this land" is a question the audit trail cannot currently answer; a long-lived
  deployment would want a horizon on that.
