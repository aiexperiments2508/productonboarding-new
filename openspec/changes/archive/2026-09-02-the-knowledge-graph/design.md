## Context

Two decisions carry this change. The first is that a real graph database is
optional rather than required, which constrains everything about how queries are
built. The second is that four of the seven domains have no source data, which
constrains where that invented data is allowed to reach.

## Decisions

### Two backends, one projection, and the response says which ran

Neo4j is used when it answers and the identical projection is walked in process
when it does not. This is the posture the MCP client already takes for its own
transport, and the reason is the same: a dependency that is required is a
dependency that has to be installed at a venue.

The claim "identical" is checked rather than argued. A test asserts identical
node sets and identical rows from both engines for every saved query. Two
implementations of one projection is exactly the shape that drifts, and the only
defence is that both are exercised on every run.

**Every response says which engine answered.** A graph that silently fell back
would make a difference in results look like a difference in the data.

The driver is imported inside a function rather than at module load, so a
checkout without the dependency still imports, starts and serves every route.

### No Docker

The startup script's own header says so, and Neo4j Community is a zip with a
batch file in it. It is fetched on request and run from a local directory, and
the startup path steps aside quietly when it is not there.

### The four invented domains arrive as events, on a lane that cannot reach a verdict

Warehouse, trading, marketing and compliance-as-entities have no source data.
Inventing them is necessary and is where the risk in this change lives: **a
readiness verdict moved by simulated warehouse data would be indefensible.**

So they arrive the way every other fact in this system arrives - as events from
systems declared in the estate manifest - on a **third lane** that:

- the transport does not count, so replay progress is unaffected;
- the live feed does not announce, because nothing has happened that a person
  needs to see;
- the ingestion handlers skip **by construction**, rather than by a filter that
  could be forgotten at a new call site.

A stock snapshot cannot move a readiness verdict, and there is a test that says
so rather than a comment claiming it.

### Derive where the catalog already knows, invent only where it does not

Certificate schemes are parsed out of the references variants already carry.
Hazmat class comes from the battery specification. Two of the six insight views
are built entirely on real media gaps and real supplier concentration.

Everything generated is stamped synthetic and drawn dashed, so a reader can see
at a glance which half of the picture is evidence and which is illustration. The
test that only the invented domains carry that stamp is what stops the
distinction eroding.

### There is no free-text Cypher

Every statement is parameterised. Three consequences follow and each is
enforced:

- **Depth is the one value Cypher will not bind**, so it comes from a closed set
  of literal patterns rather than being interpolated. A depth outside the set is
  refused before it reaches the database.
- **Domains are an enum**, so a domain filter carrying Cypher is refused rather
  than concatenated.
- **Saved queries are an allowlist checked by name**, so an unknown insight
  never reaches a builder.

An out-of-range parameter is **refused rather than clamped**. Clamping answers a
question the caller did not ask and reports it as the answer to the one they
did.

The row cap is the same in both implementations, because a cap that differed
would make the two backends disagree about a large result and the disagreement
would look like a data difference.

### The schema is asserted, not documented

Every label belongs to a domain and every domain has at least one label. Every
label has a business key with a constraint behind it. Every relationship
declares both of its ends. An edge takes the domain of what it reaches. The
schema applies and re-applies without error, and the merge is idempotent.

These are the properties that make the projection re-runnable, which is what
makes "both backends hold the same graph" checkable at all.

### The estate's arrival read is scoped per system

Reading the newest few hundred arrivals estate-wide and filtering afterwards
means a quiet system behind a busy one reports having delivered nothing - which
is indistinguishable from a system that has actually gone silent, and the second
is what the estate map exists to show.

## Risks / Trade-offs

- **Two implementations of one projection** is a maintenance cost, paid
  deliberately so the graph is not a hard dependency. The both-backends tests are
  what make it survivable.
- **Four domains of invented data** now exist in the system. Contained by the
  lane, the synthetic stamp, and the test that a verdict does not move.
- **The in-process walk is not a graph database.** It answers the saved queries
  and the bounded neighbourhood, which is the whole surface, and would not scale
  to arbitrary traversal - which is why there is no free-text Cypher to offer
  one.

## Open Questions

- The depth bound is small and stated. A traversal that genuinely needed more
  hops would need a fourth literal pattern rather than a parameter, and at some
  point that stops being reasonable.
