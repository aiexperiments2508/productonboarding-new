## Context

The queue is derived from the facts in force. That is a good rule and it has a
blind spot: some kinds of trouble are precisely the kinds that leave no fact
behind. A row that lost a precedence contest is not recorded - correctly - so a
view over facts alone cannot see the disagreement at all. This change is mostly
about reaching those without abandoning the rule that makes the queue
self-retiring.

## Decisions

### All three new kinds are derived, and nothing is stored

A stored case has to be retired by something, and the retirement rule is where
these things drift. Deriving them means a conflict whose value the record later
adopted, a gap later filled and a document later reinstated stop being reported
because the record stopped saying them. That is the only resolution rule that
cannot fall out of step with the facts.

### A source conflict is recomputed from the tape, not remembered

Ingestion returns before recording when an incoming row ranks below the document
in force, and it is right to: recording the loser would let a portal spreadsheet
quietly beat approved artwork. But both halves of the contest survive anyway -
the losing value is in the event payload, which is durable, and the winning
value is the fact in force.

So the contest is recomputed rather than remembered, and against what is in
force **now** rather than at the instant it arrived. That is what gives
resolution for free: a row the record later adopted, or whose document later
outranked the one that beat it, simply stops being reported.

The scan over the tape is bounded. What that bound limits is how long a losing
row keeps asking to be looked at, not whether it was refused - the contest was
settled at the instant it arrived and stays settled.

### A gap is classified by ingestion's own predicate

A mandatory field a document asserted *empty* is missing information, not a
correction to whatever the field used to say. Classifying by attribute path gets
this wrong, and the wrongness is invisible: the case opens, it just opens as the
wrong kind and reads as a value having changed.

The predicate ingestion already applies is made public and called from here.
Two copies would be two definitions of a gap, and the queue would disagree with
the record that filled it.

### Withdrawal is keyed by the pinned version, and the obvious keying is inverted

This is the sharpest edge in the change, and the first reading of it is
backwards.

Retracting a revision is usually the *opposite* of bad news. The recorded
flight's own withdrawal pulls a provisional dimensional drawing after the
tooling audit closed; the earlier version stands; the signal merge already
treats that as a resolver. Keying a new case by *document* would turn the one
piece of good news on the tape into a critical incident on a kettle.

So a case opens only where a fact in force **pins** the retracted document
version - a value that revision asserted and nothing has since replaced. A fact
that merely *inherits* the version, or one recorded from an earlier revision, is
still supported and is not reported.

One signal per entity, not per path: a revision withdrawn under six of a
variant's attributes is one piece of news about that variant, and six rows would
be six cases' worth of noise about one event.

And this signal is deliberately **not** a resolver. A retraction that clears an
earlier notice is read out of the event itself and marked there; a retraction
that leaves values unsupported is the opposite, and must not retire the signals
it stands beside.

### The withdrawal pass reuses a lineage walk that is already happening

The document behind each value is being resolved on the line that decides
whether a value moved. Building the pinned-version map there rather than in a
second scan means one lineage walk over the facts rather than two.

The "a feed restating a value it already agrees with is not news" short-circuit
therefore has to move *after* that resolution. An unchanged value is still
standing on whatever asserted it, and the withdrawal of that document is news
about the value even so.

### The walk is paced on the client, and that is not a preference

The streaming endpoint accepts a pace and sleeps between products. That works
right up until something between the two buffers the response - a reverse proxy
without buffering disabled, a dev server's proxy, an embedded webview. Then
every frame lands in one chunk, the renderer batches the state updates into one
render, and the walk the whole feature exists to show is skipped silently.

Buffering cannot reorder or drop frames. So a client that paces its own
*reading* is correct on every transport, and the server is asked for the work as
fast as it can do it. The pace is presentation only: the report is identical
whatever it is set to, and no figure on screen depends on it.

The map pins to the walking supplier for the duration, because the map draws a
page of the catalog and a product being assessed outside that page would light
nothing at all. Pinned once per bundle rather than per product.

### The map holds detail where the reader is looking

A listing is drawn at full weight when it is traced, in the blast radius, being
worked, or stopped. Otherwise it is a hairline and its count rides on the
variant as a chip that traces it. Nothing is hidden; the picture stops shouting,
and the motion that means "this is publishing" starts meaning something again.

The systems tier is off behind a toggle. It is the estate rather than the
catalog, and there is a section about the estate.

### One run finishing is worth a screen change; the eleventh of a sweep is not

Starting a run gains a flag for whether to announce itself. A single run
finishing is news worth a section change and a toast. Moving the reader off the
map after the first case of a sweep they started deliberately would take away
the thing they are watching it on, so the sweep announces its own tally at the
end instead.

Each case is worked as its own run stopping at its own approval gate. That is a
success for the sweep rather than a reason to stop - the queue of decisions is
the point. Between runs the list is re-read, so a case a run *opened* by reading
an unexamined document is picked up rather than waiting for somebody to notice
the scoping step reporting it. The loop has a written-down ceiling so that
"walks until the queue is empty" cannot spin.

## Risks / Trade-offs

- **The conflict scan reads the tape.** Bounded, and the bound is about
  attention rather than correctness, but it is a linear read on a path that had
  none.
- **A pinned-version key is stricter than a document key**, and will miss a
  withdrawal whose values were asserted by an earlier revision and never
  restated. That is the intended trade: the looser key manufactures incidents
  out of good news, and this one under-reports rather than over-reports.
- **Client pacing means the walk is only as smooth as the browser tab.** A
  backgrounded tab throttles timers. Accepted, because the failure is a slow
  walk rather than an invisible one.
