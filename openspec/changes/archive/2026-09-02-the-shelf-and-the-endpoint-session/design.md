## Context

Three faults with one thing in common: each was invisible because the system
reported success. An empty shelf was a truthful "not carrying these lines", a
blank price was a rendered field, and a wedged endpoint was a spinner. None of
them raised.

## Decisions

### The shop asks; it does not hold a list

The immediate fix for four renamed SKUs is four corrected SKUs. That is the
wrong fix: **a downstream application should not hold a copy of the catalogue**,
and any list written down there is wrong the next time a product is renamed -
which is a thing that just happened and will happen again.

So the publication server gains a read and the shop asks for it.

### The shelf read is scoped, and that is a different act from the lookup

The existing listing lookup deliberately will not confirm a SKU the asking
channel does not carry. That is what stops a marketplace discovering, by
exhaustive guessing, what the print channel has.

Telling a channel what is on **its own** shelf is not that act, so the shelf
read is scoped to the asking system the way the impact read already is. The
distinction is worth stating because the two reads look similar and the first
one's refusal is load-bearing: a shelf read that answered for any channel would
undo the isolation the lookup exists to hold.

### The shelf is in the catalogue's own order

Sorting by SKU orders a shop by brand prefix. That is alphabetical rather than
meaningful, and it put a jersey top above the product the demonstration is
about. The catalogue already has an order that reflects what the assortment
leads with, and that is the order a shelf should read in.

### A price with no value shows nothing

The prices were keyed by SKU and the generator keys them by variant. A SKU is a
brand's name for a thing and changes when the brand does; a variant identifier
does not.

A line with no price shows none rather than a zero or a placeholder, which is
the honest rendering of a price this system does not model.

### The session belongs to a task, not to a request

This is the substantive one.

The endpoint opened its MCP session inside whichever HTTP request arrived
first. The streamable-HTTP transport runs its reader **in the task that opened
it**, so the session belonged to that request's task - and the moment that
request finished, the reader was inside a scope nobody was in any more. The
next caller got a session whose replies nobody was reading, waited for ever,
and held the endpoint while waiting, so everything after it queued behind a call
that was never going to finish.

So the session is owned by a task of its own, for its whole life. Callers hand
it work and wait for an answer. A caller that goes away - a browser that
navigated, a request that timed out - takes nothing down with it, because the
call is **shielded from its cancellation**: cancelling the caller must not
cancel the work the session is in the middle of.

A call that does not answer inside thirty seconds gives up and the session is
reopened, so an endpoint wedged some other way recovers rather than needing the
process restarted.

**What the tests can and cannot pin is stated rather than implied.** The two
client tests assert what is assertable here - overlapping calls are all
answered, and a cancelled caller leaves the endpoint usable - and say plainly
that they do not reproduce the original deadlock, which needed the real
transport's task affinity and therefore a live platform. A test named for a bug
it cannot reproduce is worse than no test, because it reads as coverage.

### A claimed decision must be reachable

Three surfaces said a reviewer accepts a proposed line. The function existed,
the route existed, the lane rendered, and no control called any of it.

That is a worse gap than a missing feature: it is the shape of claim this
codebase is otherwise careful not to make. The panel is first in the drawer
rather than under the evidence, because on a proposal it is the only thing there
is to do.

It asks for a **name** - accepting a line means the retailer takes on
responsibility for what it says about something it has never sold, and the
ledger records who did that. There is no identity provider here and the panel
does not pretend there is; the name is taken at its word and written down, which
is worth more than a blank.

The SKU is **offered and does not insist**: left empty the platform mints one,
which is right for a demonstration and wrong for a retailer that already knows
what it will call the thing. The name and category are not asked for at all -
they came from the supplier, and a reviewer should accept the line they were
shown rather than retype it.

**What it says afterwards is the part worth keeping.** An accepted line arrives
with no attributes and no imagery, so it goes straight to being with its
supplier and reads as incomplete. The confirmation says so, rather than
reporting a product created and letting somebody discover later that it holds
nothing. And accepting is not publishing: the line joins the catalogue and is
assessed like any other product, and putting it on a channel is a decision
behind its own gate.

## Risks / Trade-offs

- **The deadlock's own regression test does not exist**, and cannot without a
  live platform. Named in the tests rather than papered over.
- **A thirty-second timeout is a guess.** It is long enough that no healthy call
  reaches it and short enough that a wedged endpoint recovers within one page
  load's patience.
- **The shelf read is another surface on the publication server**, which is the
  one server that can also write. It is a read, declared as one, and covered by
  the existing assertion that read-only tools do not reach publication.

## Open Questions

- The storefront now asks per page load. A channel carrying two hundred and
  eighty-one lines is a small answer, but nothing caches it, and a busier
  channel would want that considered.
