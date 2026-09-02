## Context

Two nodes hold almost all of a run's wall clock. `regenerate` calls the
reasoning tier once per content field, up to twelve times, in a `for` loop.
`extract` calls the fast tier once per unread supplier document in another. The
gateway is synchronous `httpx`, one request per call, with a 120-second timeout
and a response cache keyed on the exact messages.

Three properties of the surrounding code decide what may be done about it.

**The storage layer already expects a thread pool.** `sc/db.py` hands out
thread-local connections and keeps a registry of every one it has issued,
with a comment saying why: the graph fans validation out across a threadpool
and each worker opens its own. The database runs in WAL with a five-second busy
timeout. Concurrency here is a road already built.

**Graph state must stay plain JSON.** The checkpointer serialises with msgpack,
so no enum, datetime or model object may enter state. Any approach that changes
the shape of what a node returns pays for it in the reducer.

**Extraction is order-dependent and regeneration is not.** `extract` threads a
watermark through its loop - each document is read against the recorded instant
the previous document's writes advanced to - and the code says why: a covering
email restating its own specification has to see what the specification wrote,
or the correction is asserted twice. `regenerate` threads nothing. Every input
to a rewrite is computed before the loop begins.

## Goals / Non-Goals

**Goals:**

- A run's wall clock scales with the slowest single model call in a stage, not
  with the number of calls in it.
- The change set, the trace and the `trace_hash` are unchanged, byte for byte,
  from what the sequential implementation produced.
- The reviewer sees real content within a second or two of starting a run.
- The suite still passes with no gateway reachable, and still contains no LLM
  mock.

**Non-Goals:**

- Making the model faster, cheaper, or asked for less. No prompt is edited and
  no cap is lowered; a run that does less work is a different change with a
  different argument.
- Making the pipeline asynchronous. The graph is synchronous and there is no
  reason for it not to be; the concurrency wanted here is inside two nodes.
- Removing the evidence loop's rounds. Those are bounded, sequential by nature -
  each round is asked in light of what the last one returned - and they are the
  interesting part of the run rather than the wasteful part.

## Decisions

**A thread pool inside the node, not a LangGraph `Send` fan-out.** `Send` is how
this graph already parallelises candidate validation, so it is the obvious
alternative and it is the wrong one here. It would split one stage into many,
which means a new reducer, a state shape that carries partial rewrites between
supersteps, one trace line per field instead of one per stage, and a checkpoint
history that no longer matches the diagram the UI draws from the compiled graph.
A pool inside the node changes latency and nothing else.

*Alternative considered.* Batching all twelve fields into a single model call.
It would be fewer round-trips still, but it changes the prompt, so every
measurement the evaluation harness has taken against the shipping prompt would
be measuring something else. It also couples twelve independent failures into
one: a reply the gateway will not accept currently costs one templated field and
would then cost twelve.

**The pool is bounded and small.** Six workers, not twelve. The gateway is a
single upstream with its own rate limits, and the failure mode of asking it for
twelve simultaneous reasoning completions is a 429 storm that the retry path
turns back into serial latency. Six is enough to collapse the loop and few
enough to stay inside a provider's concurrency allowance.

**Each worker accumulates its own spend and errors; the merge is ordered.**
The existing code appends usage to a shared list and deduplicates errors with a
membership test against another - both correct under one thread and neither
under six. Workers return their own, and the results are folded back in target
order, so two runs that raced differently still produce the same lists in the
same order.

**Extraction parallelises its reads and keeps its writes in tape order.** The
model call for a document depends only on the catalog and the event, both fixed
for the duration of the node, so all readings can be fetched at once. The
persistence loop then runs exactly as it does today, in sequence, over readings
that are already in hand. The watermark still advances document by document.

*The cost, and it is worth naming.* A document whose reading is never used -
one the loop skips as immaterial - has still been paid for. That is a few
fast-tier calls against a saving of the entire serial chain, and the alternative
is a prefetch that has to predict which documents the loop will reach, which is
the loop.

**Order is restored by construction, not by luck.** Results come back as a list
indexed by the target's position, and the assembly loop walks targets rather
than completions. There is no sort on a completion timestamp anywhere, because a
sort is a thing that can tie.

## Risks / Trade-offs

**A concurrency bug here is a correctness bug, not a performance bug.** The
whole system rests on the same correction producing the same answer. This is why
the acceptance test is equality against the sequential path over a real change
set rather than a timing assertion, and why the sequential implementation is
kept reachable behind a worker count of one - a difference in output is then
bisectable in one run.

**The suite cannot see the improvement.** Tests run with the gateway closed, so
the fallback path returns instantly and a concurrent fallback is not measurably
faster than a serial one. What the suite can check is that the answer did not
move, which is the property that matters; the latency claim is verified by
running the thing.

**SQLite has one writer.** Six workers calling the gateway also write to
`llm_calls` when the response cache records a call. WAL permits one writer with
concurrent readers, and the busy timeout absorbs the contention at this volume,
but a much larger pool would turn a latency win into lock contention. This is
part of why the pool is six.

## Migration Plan

No data migration and no configuration change. The worker count is a module
constant beside `MAX_REGENERATIONS`, and setting it to one restores exactly
today's behaviour, which is what makes the equality test meaningful rather than
circular.

## Open Questions

- Whether the cache pre-warm belongs in `prepare_demo.py` or in a flag on
  `run.py`. It is in `prepare_demo.py` here because that script already exists
  to put the system into its demo position, but a rehearsal that warms the cache
  and a demo that reads it are two different intentions sharing one entry point.
- Whether `resolve_scope`'s mandatory evidence lookups - which are known before
  the model is asked anything - should be fetched concurrently too. They are
  catalog reads rather than model calls, so the saving is small; it is left
  alone here rather than bundled into a change about model latency.
