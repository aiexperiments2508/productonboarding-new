## Context

This change adds the present tense to a system that has only had a past tense.
Almost every decision below is about keeping a new, live, externally-reachable
surface from weakening a guarantee the recorded half already makes.

## Decisions

### The boundary is a test, not a convention

Three applications reach the platform over MCP and by no other route. They hold
no database and no access to the HTTP API.

That is one convenient line away from being false at any moment - an `import
sc.db` in a handler, a `fetch("/api/...")` in a page - and **nothing would
visibly break when it happened.** The application would keep working, faster,
and the architectural claim would be quietly untrue. So the boundary is walked
by a test: their imports, their server-side fetches, and the URLs their web
pages reach.

### The lanes are told apart by a column, never by a sequence range

The obvious implementation gives the live lane a high sequence band and
compares numbers. Two failures made that untenable, and both of them **report
success**:

- `advance` had no upper bound, so the cursor would walk out of the recording
  and into the high band, and the transport would report having replayed
  everything.
- Ingestion keeps a single watermark, which would be pushed past every
  remaining taped event - so ingestion would stop recording facts and report
  success.

A column cannot be walked into by arithmetic. Both failures now have named
regression tests, because a bug whose symptom is "it worked" does not announce
itself a second time either.

### A supplier cannot write a value, and there is no permission check to route around

A submission is recorded as a **document version**. What it asserts becomes a
fact only when the graph reads the document and writes it back inferred, under
the fail-closed safety gate.

The enforcement is the provenance taxonomy rather than an authorisation check.
That distinction is the point: a permission check is a thing that can be passed,
mocked, or forgotten at a new call site, whereas there is no code path from the
intake to the fact store at all. The intake's imports are asserted so there
cannot come to be one.

A correction revises the document the value came off, rather than minting a new
document - a newly minted identifier carries no precedence and would lose every
contest it entered.

### Redaction is authorised by the approval that already exists; republishing is not

Between knowing a live value is wrong and having a validated replacement, the
wrong value is still on sale. That gap is real and the system previously had no
move in it.

So the two acts are separated by what authorises them. **Hiding** is authorised
by the approval that already agreed the value was wrong, and happens at once -
asking for a second decision to stop showing something a reviewer has already
called incorrect would be ceremony with a shopper on the other end of it.
**Republishing** needs its own release decision.

That decision is recorded in **its own table, never in the approvals table.** If
it lived there it would satisfy the first gate by itself, and "we agreed the old
value was wrong" would silently become "we agreed the new value is right". It is
enforced as a fourth refusal in the publish path, beside the three that already
exist.

### What "hide" means is derived from the channel, and one correction gets five right answers

A single correction produces five genuinely different correct actions:

| channel | action |
|---|---|
| web listing | withheld |
| marketplace | withdrawn - its own rules make a placeholder a hard violation |
| search | facet dropped, rather than left indexing a wrong value |
| shelf | label queued for reprint, not claimed as done |
| print run | cannot be recalled at all |

The print case is the one worth stating: it opens an **erratum obligation** and
is never reported as redacted. Reporting a print run as redacted would be a lie
about the physical world, and an obligation that nobody has discharged is the
honest record of it.

Copy is redacted with the value it quotes, through the same lineage the blast
radius already uses. A bullet reading "may contain milk" sitting above a spec
row saying the allergen statement is being checked would make the page **worse**
than before the correction started.

### A redaction is a new fact and never an edit

It writes no attribute fact, moves no published version, is invisible to the
validator, and emits no change-set action. What a channel showed before a
redaction stays readable as of then, because the store is bitemporal and hiding
something today is not a claim about what was true yesterday.

A rollback does not undo a safety redaction. Rolling back a publish restores a
previous state; it is not a decision that the hidden value is now fine.

### Lanes are derived, never stored

Every product is placed in exactly one lane from its current state, for the
same reason the publication estate is derived from the channels: a stored lane
is a second account of the truth and the first thing it disagrees about is
whatever just changed.

A product is **as blocked as its worst variant**, because that is the question
the board answers - "can I sell this product" - and one unsellable size makes
the answer no.

Precedence is argued: a late change outranks being on sale, because a product
on sale with an unread submission against it is the row somebody has to look
at; and being sent back outranks being on sale for the same reason.

## Risks / Trade-offs

- **Three more processes to run.** Each is small and holds no state, and the
  alternative - simulating the outside world inside the platform - is what this
  change exists to stop doing.
- **A redaction leaves a product visibly incomplete on the channel.** That is
  the intended outcome: a gap that says "being checked" is better than a wrong
  allergen statement, and the erratum path says so explicitly where a channel
  cannot be recalled.
- **The live lane can be submitted to while the tape is paused.** Two
  submissions at one paused instant must not tie, so the ordering has to be
  resolved on something other than the simulated clock alone.

## Open Questions

- Supplier identity is taken at its word. There is no identity provider here and
  the portal does not pretend otherwise; what a submission records is the
  supplier the endpoint was reached as. Attribution, not authentication.
