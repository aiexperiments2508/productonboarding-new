## Why

Product 360 has five sections, and a person with a question has to know which
one answers it. "Where is this stocked", "why is it blocked", "what is it
certified to", "can we sell it in Ireland" - each lands in a different section,
and a reader who does not already know the layout reads all five.

The obvious answer is a panel that takes the question in words. It is also the
**only** surface in this application that would take an open-ended question,
which makes it the easiest place in the whole system to say something untrue.

The failure has a specific shape and it is not hypothetical. A model given a
retrieval tool and a question can choose to look up nothing and answer from its
own memory, fluently, citing nothing - and every other surface here is built so
that cannot happen. A panel that reintroduced it would undo the argument the
rest of the application makes.

There is also a fault worth naming before it is built on: a graph walk that
reaches from a variant *through* the product to what hangs off it also walks
back down into the product's sibling variants. Their stock and their
certificates then arrive labelled as this variant's. On one product that turns
three stock records into a hundred and eighty-one, and one certificate into
nineteen - a reply that is fluent, cites its sources, and is wrong by sixtyfold.

## What Changes

- **An Ask panel above Product 360's five sections**, linking down into
  whichever one its answer concerned rather than competing for a place in the
  row. A question can be about any of them, so it sits above all of them.
- **Routing is deterministic.** A closed keyword table picks which surfaces a
  question reaches. A model choosing what to look up is a model that can choose
  to look up nothing and answer anyway.
- **Evidence is gathered before anything is phrased.** The reply step is handed
  facts and asked for a sentence. It has **no retrieval tool**, so the failure
  where a model answers from its own memory is not mitigated - it is
  unavailable.
- **An answer with no evidence is a refusal** that names what could be asked
  instead, rendered in a different treatment from prose. A confident sentence
  and an admission of ignorance must not look the same.
- **The graph walk is two hops from the variant with no detour through the
  product**, which is a correctness constraint rather than a performance one.
  What genuinely hangs off the product is reached by one hop from the product
  node, which cannot stray. The test asserts this against the graph's own
  adjacency rather than against a number written down by hand.
- **Routing gaps are closed by generating inflections**, with any hand-written
  spelling always winning - that guard is what stops a low-weighted word in one
  intent quietly acquiring a related word belonging to another.
- **Speech out is the browser's own synthesis**: nothing is uploaded and the
  panel works with the speakers muted. Voices arrive asynchronously and one
  browser stops speaking after about fifteen seconds unless resumed on a timer;
  both are worked around rather than assumed away.
- Also fixes a promotion leaking into the back office campaign table, where it
  threw on render: a promotion carries a campaign identifier too, so the filter
  keys on the objective, which only a campaign has.

## Capabilities

### New Capabilities

- `product-questions`: taking a question about a product in words, deciding
  deterministically what to look up, and answering only from what was found.

## Impact

- `sc/chat/intents.py` - the closed keyword table and the generated
  inflections.
- `sc/chat/evidence.py` - the gather, including the one-hop-from-product walk.
- `sc/chat/reply.py` - handed facts, asked for a sentence, given no tools.
- `sc/main.py` - the chat route, holding no business logic.
- `frontend/src/components/chat/` - the panel, the refusal treatment, the
  speech-out timer.
- `apps/backoffice/` - the campaign filter keyed on objective.
- `tests/test_chat.py`.
