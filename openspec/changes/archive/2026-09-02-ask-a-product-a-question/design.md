## Context

This is the only surface in the application that takes an open-ended question,
which makes it the easiest place here to say something untrue. Three decisions
arrange it so that saying something untrue is *hard* rather than so that
answering is *easy*, and they are the whole design.

## Decisions

### Routing is deterministic, and a model does not choose what to look up

A closed keyword table picks which surfaces a question reaches.

The alternative - handing a model a set of retrieval tools and letting it decide
- has one failure mode that matters: **a model that can choose what to look up
can choose to look up nothing** and answer from its own memory, fluently. Every
other surface in this application is built so that cannot happen, and a panel
that reintroduced it would undo the argument the rest of the system makes.

The cost is that routing has gaps, and it does. Three were real - and each was
found by asking the surface rather than by reading the table, which is worth
recording as the way to find the rest.

### Evidence is gathered before anything is phrased, and the phrasing step has no tools

The reply step is handed facts and asked for a sentence. It has no retrieval
tool at all.

That is stronger than instructing it not to answer from memory. **The failure is
not mitigated; it is unavailable.** There is nothing to reach for, so there is
no path by which an unsupported claim can enter with a citation attached.

### An answer with no evidence is a refusal, and it looks different

Where nothing was found, the panel refuses and names what could be asked
instead.

The refusal is rendered in a different treatment from prose, and that is not
decoration. **A confident sentence and an admission of ignorance must not look
the same** - if they do, a reader skimming takes the second for the first, which
is the exact outcome the whole design is arranged to prevent.

### The graph walk is two hops from the variant and never detours through the product

This is a correctness constraint, not a performance one, and it is the sharp
edge of the change.

Widening the walk to reach a campaign also walks back *down* into the product's
sibling variants. Their stock and their certificates then arrive labelled as
this variant's. Measured on one product: three stock records became a hundred
and eighty-one, and one certificate became nineteen. The reply was fluent, cited
its sources, and was wrong by sixtyfold - which is the worst available failure,
because every signal a reader uses to judge an answer said it was good.

So what genuinely hangs off the *product* is reached by one hop from the product
node, which cannot stray into siblings. The test asserts this **against the
graph's own adjacency** rather than against a count written down by hand, so it
keeps holding when the projection changes.

### Inflections are generated, and a hand-written spelling always wins

Routing gaps are closed by generating word forms rather than by listing them.

The guard matters more than the generation: a hand-written spelling always beats
a generated one. Without it, a word weighted low in one intent quietly acquires
a related form belonging to another - the concrete case being an intent weighting
"market" at 1 silently picking up "marketing", which belongs elsewhere.

### Speech out is the browser's own, and nothing is uploaded

The panel works with the speakers muted; speech is an addition, never the path.

Two browser behaviours are worked around rather than assumed away: voices arrive
asynchronously, so the voice list is not read once at load; and one browser stops
speaking after about fifteen seconds unless resumed on a timer.

## Risks / Trade-offs

- **Deterministic routing has gaps by construction.** A question phrased outside
  the table routes to nothing and gets a refusal. That is the intended failure -
  a refusal naming what can be asked is recoverable; a confident wrong answer is
  not.
- **The keyword table is a maintenance surface.** Every new domain of question
  needs an entry, and the generated inflections reduce but do not remove that.
- **The refusal is only as useful as what it suggests.** It names what could be
  asked instead, which is the difference between a dead end and a redirect.

## Open Questions

- The panel answers about one product. A question spanning two - "which of these
  is blocked" - routes to nothing, and the right shape for that is not obvious
  without letting the walk widen, which is the thing this design most carefully
  refuses.
