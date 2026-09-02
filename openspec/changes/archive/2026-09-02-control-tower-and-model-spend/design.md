## Context

Everything on this surface is a number somebody will repeat without having seen
the product it came from. That is the whole reason the decisions below lean so
hard on *not concluding anything* and on saying which question each figure
answers. A dashboard that reached its own verdict would be a second answer to
"is this ready", and the one on the big screen is the one people would quote.

## Decisions

### The tower joins and never concludes

Every verdict, gate outcome, stage, lane and cost is read from the module that
owns it - readiness, the onboarding gate, lifecycle, the ledger. Nothing in the
tower weighs, scores or decides.

There is no snapshot table and no stored rollup either. Every number is
recomputed on read, for the reason `lifecycle/stages` gives for not storing a
stage: a stored figure is a second account of the truth, and the first thing it
disagrees about is whatever somebody just changed.

The cost of that is real - a window of thirty feeds is thirty readiness passes
- and it is paid by hoisting the whole-estate reads (the catalog, the overlay,
the lane signals) into one context built once per request, and by letting a
list of a hundred feeds ask for arrival facts without the states.

### Position is exclusive; history is not

`state_of` returns exactly one state, because a product is in one place. But
"the AI corrected this" is a fact about the past that does not stop being true
when the product moves on, so it is carried beside the state as a flag and a
count rather than as an eighth place to be.

Filing every row under exactly one heading would mean either losing the
autonomous fills into "all clear", where nobody would ever see them, or
reporting a product as corrected when what it actually *is* now is on sale.
This is the same trade `readiness/rollup` already makes for stopped rows.

### The precedence order is argued, not arbitrary

- **Not ingested outranks everything.** A product the record has not taken in
  yet has no verdict worth reporting, and showing the last assessment beside a
  feed that has just landed would date-stamp a screen with an answer about a
  different version of the record.
- **Stopped outranks downstream.** A product that is on sale *and* has just
  been refused by the gate is the single row somebody has to look at, and a
  board filing it under "on sale" would hide it.
- **Downstream outranks waiting.** A pending proposal on a product already
  dispatched is real, but where the product *is* is downstream; the proposal
  shows in the count of open decisions either way.

### `RETURN_TO_SOURCE` is not blocked, and the distinction is the point

Blocked means the gate stopped it or a finding blocks it - the two things a
supplier has to fix. A record with a gap the gate let through is mid-flight:
the gate passed it, so nothing is wrong with it that a value would not fix, and
the next thing that happens is the system trying to fill that gap from what it
already holds.

Filing that as blocked would count the entire AI-correction lane as a failure,
which is the opposite of what it is. Written the other way round, the
in-progress state is unreachable - which is what the test that walks every
state is for.

### The grain is the row the supplier sent, and two surfaces will disagree

Product Lifecycle places a *product*, and a product is as blocked as its worst
variant. Asked about a feed, the honest answer is that one row cleared and one
did not, because that is what the supplier has to act on.

So the lane is recomputed per variant from the same `stage_of` and the same
three signals the board passes it. Same function, same inputs, finer grain -
not a second set of rules. Both surfaces are right and they will disagree for
the same pack, so each caption names which question it answered.

### A cache and a ledger want opposite shapes, so there are two tables

`llm_calls` is keyed by the cache key. That is exactly right for a cache and
wrong for a ledger in three ways at once: the timestamp is the first time the
prompt was ever seen, there is one row per distinct prompt rather than per
call, and no column names the feed.

So the cache stays a cache and `llm_ledger` is append-only, written at the two
choke points completion already had plus embedding. Nothing on the read path
depends on it, and the append is guarded: the call has already happened, and a
ledger that could take the gateway down would be a worse trade than no ledger.

**A cache hit is recorded, not skipped.** It lands with its token counts intact
and no cost of its own, which makes spend and spend-avoided two separate sums
over one table rather than one number with a footnote. What the hit *would*
have cost is read off the cache's own record and never re-estimated - the
flattering reading and the honest one are then the same reading, which is the
only good reason to prefer it.

### Two clocks, and neither is allowed to answer the other's question

This is the one place a plausible number can be quietly wrong, so it is stated
rather than assumed.

Windows filter simulated timestamps, because the whole recorded flight happened
in simulated July and August and a real-clock filter over it returns everything
or nothing depending on when the demo was last reset. Durations measure real
timestamps at both ends. Subtracting one from the other would produce a
confident number with no meaning, so a duration whose ends do not subtract - or
subtracts negative - is reported as missing rather than as a figure. `clock:
"real"` is carried beside the durations so a reader knows which question was
answered. In production these are one clock and the distinction disappears; on
a replay it is the difference between an SLA and a fiction.

### A cost of zero is not a fact about the price

Cost is the gateway's own reported figure, and a model whose price map has no
entry yields none. Those rows are marked unpriced and counted separately, so a
window nobody could price says so instead of reporting a confident $0.0000.

### The cap is two caps, and it is deliberately soft

A money cap on a gateway that prices nothing is a control that can never fire.
So a token cap sits beside it and either trips alone, and the refusal names
which one tripped - a refusal that did not would send an operator to raise the
wrong number.

The meter starts when the cap is set, as a ledger position rather than a
timestamp: two rows written in the same second can carry the same string, and a
call made microseconds before the cap was set would otherwise count against it.
An unscoped meter would also make a freshly-set cap read as instantly breached.

Past the cap the gateway raises **the same error an unreachable gateway
raises**, so every deterministic fallback already written runs, the work
continues with narrower answers, and the assessment says its reading checks did
not complete.

It overshoots by up to one batch of concurrent calls, because the four reading
checks clear the check together before any of them records a token. Closing
that would mean serialising calls that were deliberately made concurrent, in
order to harden a cap whose whole design is to be soft.

### The personas are a lens, and every surface says so

There is no identity provider in this system, no session and no password. A
decision records the name whoever took it typed - that is attribution, which is
a real property, rather than authentication, which this system does not have.

A persona changes which figures lead and nothing else, and the API says so in
its own contract. A picker that implied it were access control would be worse
than none, because somebody would build a process on it. What *is* enforced is
unchanged and lives where it always did: a decision, a fill, a threshold move
and a cap each demand a named actor and write it to the ledger.

The personas are declared as data so the API and the console read one list. A
second copy in the frontend is where "Compliance" and "Compliance Officer"
start appearing on two screens for the same person.

### The control tower is a toolset, and the cap is not on it

Everything the tower serves is derived on read, so there is nothing a tool
could sensibly write to. The one control that goes with these numbers - the
spend cap - is deliberately not a tool, for the same reason the approval gate
is not a peer and `commit_plan` lives on the publishing server. Moving a cap
changes what the system will do unattended, and that is a decision with a
person behind it; it stays on the HTTP API where the name is demanded and
audited.

This is a toolset and not an estate system. The estate is the external systems
this platform *talks to*; the control tower is a capability this platform
*implements*, which is the distinction the agent-card surface exists to keep.

## Risks / Trade-offs

- **Recomputing a window is not free.** A hundred feeds with states is a
  hundred readiness passes. Mitigated by the shared context and by the states
  being optional, and accepted because the alternative is a stored rollup that
  can disagree with the record.
- **The cap overshoots by a batch.** Named above; accepted deliberately.
- **A rate over nothing is `None`, not zero**, and every consumer has to render
  a dash. Reporting a 0% compliance pass rate for a window in which nothing was
  assessed is the kind of figure that gets screenshotted.
- **The two grains will be quoted against each other.** No amount of captioning
  fully prevents somebody comparing a product count with a row count. The
  mitigation is that both surfaces name their grain in the payload, not only in
  the caption.

## Open Questions

- Spend is attributable to a feed and a surface. It is not attributable to a
  *product*, because a reading check runs over a record rather than over a row.
  Whether that attribution is worth the plumbing is unresolved.
