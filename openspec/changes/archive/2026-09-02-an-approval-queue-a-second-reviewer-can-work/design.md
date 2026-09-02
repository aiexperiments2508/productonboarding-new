## Context

This change adds no capability. Every part of the mechanism already works: the
pending endpoint, the resume route, and an on-disk checkpointer that survives a
restart. What is wrong is that the client holds one thread identifier where the
server holds a queue, and no amount of correctness at the back compensates for
that.

## Decisions

### One read, two consumers

The badge and the list read the same array.

The alternative - a count endpoint for the badge and a list endpoint for the
screen - is what produced the original fault in the first place: two surfaces
each correct about their own source, disagreeing in public. Holding the queue
as the array it is makes "badge says three, screen says nothing to do"
**unrepresentable** rather than merely fixed, which is a stronger property than
the bug being closed.

### Selecting a row adopts the thread, in both places it is held

Loading a checkpoint into the view is half of it. The in-memory reference and
the stored identifier both have to move.

If only the view moves, two things break in ways a reviewer would not predict:
re-planning still points at whatever this browser last *ran*, and a reload drops
the reviewer back on somebody else's case. Both are silent - the screen looks
right, and the action goes somewhere else.

### The rows carry the grounds for choosing between them

Severity, whether review is mandatory, when it was raised, how many fields move,
and the product it is about.

A reviewer with three waiting decisions otherwise chooses by opening all three,
which is three checkpoint loads to answer a question the list already knows. The
list exists to be triaged from, so it carries what triage needs.

### The worked row is marked, not removed, and stays in the tab order

Removing it would make the list jump under a reviewer mid-decision.

Marking it disabled to assistive technology rather than actually disabling it is
deliberate: it is the row most likely to be tabbed back to, and a genuinely
disabled control leaves the tab order entirely, so a keyboard user loses their
place in the list they are working.

### The empty state keeps its words for when they are true

"Nothing awaiting a decision" is a correct and useful sentence when the queue is
empty. The objection was never to the wording - it was that the sentence
appeared while two decisions were waiting. When the queue is not empty the
screen says so and points at it.

## Risks / Trade-offs

- **No test covers this.** There is no frontend test in this repository, and
  this change is entirely in the client. The server-side property the fix relies
  on - that the pending list is confirmed against each run's checkpoint - is
  already asserted; what is added here is verified by use.
- **Two reviewers can open the same case.** Nothing here locks a row. The
  publish lock downstream is exclusive at the database, so the second decision
  is refused rather than duplicated, but the second reviewer discovers that at
  the end rather than the beginning.

## Open Questions

- Whether a row should be claimable, so a second reviewer sees it as being
  worked before spending the decision. That needs a notion of who is working it,
  and there is no identity provider here to hang one on.
