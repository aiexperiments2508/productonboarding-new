## Context

The propagation walk is a typed edge traversal over the catalog: document to
attribute to asset to listing to channel. It already finds the non-obvious case
- a correction scoped to one variant landing on a sibling's page because a
comparison table quotes both - which is the single most convincing thing this
system does in a demo.

It reports that finding in `VAR-01B` and `LST-07`. Those are the right
identifiers for the code and the wrong ones for the conversation the finding
starts.

Publishing is one call with three refusals enforced at the planning boundary
rather than in the graph, so no future graph edit can route around them. That
placement is correct and this change does not move it.

## Goals / Non-Goals

**Goals:**

- The blast radius answerable in SKUs and in publication systems.
- A dispatch plan a reviewer can read before deciding, that writes nothing.
- Per-system outcomes on both dispatch and revert.
- The three refusals untouched and still enforced in one place.

**Non-Goals:**

- Moving or duplicating the approval gate. It is at the planning boundary
  because that is the one place the graph cannot route around, and re-checking
  it here would be a second implementation of the thing most worth having only
  one of.
- Per-channel approval. A reviewer approves a *resolution*; letting them approve
  it for four channels and not the fifth turns one decision into six and makes
  "what was approved" unanswerable.
- Retrying a deferred channel automatically. A freeze window ends on a date
  somebody knows, and a system that quietly published when it lifted would
  publish without anybody watching.

## Decisions

**Publication systems are derived from the channels, never configured beside
them.** A separate list would be a second account of where content goes, and the
first thing it would disagree about is the channel somebody has just added -
which is exactly when a disagreement is least likely to be noticed and most
likely to matter.

*The consequence, and it is a real one.* A publication system cannot have
properties its channel does not. That is right today, because everything one
needs - schema, freeze window, recallability - is a property of the channel. It
stops being right the day two systems publish to one channel, and that day is
when this decision should be revisited rather than worked around.

**Recallability is the freeze window, not a second flag.** A channel declares a
freeze window *because* what it publishes cannot be pulled back. Storing both
would let them disagree, and the disagreement would be silent: a channel marked
recallable with a seven-day window reads as a mistake in either direction.

**Dispatch is per system; refusal is not.** These pull in opposite directions
and both are right.

A *dispatch* is per system because the systems fail independently - a
marketplace connector that is down must not hold up four channels that are
answering, and a caller told "failed" cannot tell whether nothing went out or
almost everything did.

A *refusal* is not per system, because the gates are properties of the
resolution rather than of any channel. A resolution nobody approved is not
approved for the website either, and reporting per-channel refusals would invite
somebody to publish the four that "passed".

**A frozen channel is deferred rather than attempted.** Attempting it would
produce a printed catalogue nobody can correct. A row in a report saying it was
not attempted is strictly better than a page that cannot be unprinted, and the
report is what a reviewer reads before the press date.

**A channel never sent to is never reported as reverted.** The asymmetry is
deliberate and would be easy to smooth away for a tidier report. A deferred
channel has nothing to roll back, and saying it was reverted would be a false
statement about a printed page - which is precisely the class of statement this
system exists to prevent.

*Alternative considered.* Omitting deferred systems from the revert report.
Rejected: a system absent from a report reads as a system nothing happened to,
and something did happen - it was skipped, on purpose, and somebody may still
need to deal with the copies already printed.

**Planning writes nothing.** A surface that published as a side effect of being
looked at would be the worst possible way to learn this, so it has its own test
rather than resting on the implementation being obviously read-only.

## Risks / Trade-offs

**A dispatch report can look like a delivery receipt.** It says what was sent
where; it does not say the receiving system accepted it. In this system the
channels are simulated, so "sent" and "accepted" coincide - and in a real
deployment they would not. The report names the verb and the endpoint so the gap
is visible, and closing it means an acknowledgement path that does not exist
yet.

**Deriving from channels ties two lifecycles together.** Adding a channel adds a
publication system, silently and correctly. Removing one removes a publication
system that may still have live listings, which the catalog would have to notice
first - and today nothing removes a channel, so this is a hazard rather than a
bug.

**The SKU view duplicates information the identifier view already carries.** Two
renderings of one truth can drift. They are both computed from the same trace on
each read rather than stored, which is the same discipline the map already
follows for the same reason.

## Migration Plan

No schema change and no data migration. The publication systems are derived on
read, and both new views are computed from a trace the walk already produces.
The publish and rollback functions are called rather than modified.

## Open Questions

- Whether a deferred channel should raise something a reviewer sees later, so
  the print run is dealt with when the window lifts rather than remembered.
  Today it is a row in a report, which is a record and not a reminder.
- Whether "sent" should wait on an acknowledgement from the receiving system. It
  would make the report a delivery receipt rather than a dispatch note; it also
  means a channel that is slow to acknowledge holds up a run, which is the
  coupling this design spent its effort avoiding.
- Whether the SKU should be the primary vocabulary of the blast-radius view
  rather than the second one offered beside identifiers. The identifiers are
  what the audit trail is written in, so they cannot leave - but the default
  rendering is a choice, and it is currently the developers' choice.
