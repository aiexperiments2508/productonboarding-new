## Context

See proposal.md - Why. The pipeline, the deterministic core and the protocol
surfaces all exist and are tested; what does not exist is a way to watch any of
it, or a way to point the model gateway at a deployment other than the one the
code assumed.

Constraints that shape the approach:

- **One process serves everything.** No separate web server, no backend-for-
  frontend hop. The domain logic sits next to the pipeline, so the API can be a
  thin layer rather than a translation.
- **The pipeline is synchronous**; the server is not. Anything that runs the
  graph has to leave the event loop free or the stream does not flush.
- **The approval gate is a real suspension.** The API cannot hold a request open
  waiting for a reviewer; it has to be able to leave, come back and resume.
- **The demonstration may run on a restricted network.** Nothing observable may
  depend on an external service being reachable - which rules out relying on a
  hosted graph viewer, and is why the response cache exists at all.
- **The gateway is somebody else's deployment.** Its model catalogue is not
  knowable at build time, and the provider credentials live in it rather than in
  this repository.
- **There is no frontend test in this repository**, so the console is a
  deliverable of this change and not a specified capability. What is specified is
  the route contract beneath it.

## Goals / Non-Goals

**Goals:**

- One HTTP surface that cannot disagree with the pipeline, because it calls the
  same functions.
- A model layer that works against a gateway nobody here configured, and says
  clearly when it is guessing.
- Configuration that is read at entry rather than by one entry point.
- A launcher that fails loudly on the two conditions that otherwise waste the
  first five minutes of a demonstration.

**Non-Goals:**

- Authentication, authorisation or multi-tenancy. There is one operator.
- A specified user interface. The console is built and shipped; it is not
  written down as a capability, because a specification with no test behind it
  would be prose asserting itself.
- A second source of truth for anything. Every read is the pipeline's own.
- Streaming from the model. Responses are whole; the stream is over pipeline
  stages, not tokens.

## Decisions

**Every read is the function the pipeline calls, not a copy of it.** The moment
the console gets its own implementation of "what does this correction touch",
there are two answers to that question and one of them is wrong. The cost is that
a route sometimes returns more than a screen needs and the shaping happens in the
client; that is the right side to pay on.

**The variant table returns the tool's cell, not the value.** This is the
regression the change is most worth remembering. Flattening
`{value, doc, version, provenance, confidence}` to `value` reads as tidying and
is the removal of the argument: the whole base-versus-variant story is that a
named document certified the base model at 45 W a fortnight before an ambiguous
correction, and a bare 45 cannot carry that. It also silently made the route and
the catalog tool two different accounts of one table, which is the failure mode
the previous decision exists to prevent.

**The spend total is summed on read.** Spend is written per stage because the
state reducer merges concurrent writers by key; a stored total would be a second
number to keep in step with the first, and the first is the one the reducer
protects.

**Runs stream over server-sent events, produced on a worker thread.** The
pipeline is synchronous and mixes CPU and IO; running it inline would block the
loop and the stream would arrive in one burst at the end, which is worse than no
stream. Errors are pushed onto the stream rather than raised, because a dropped
connection is indistinguishable from a network problem at the far end.

**The topology is read from the compiled graph.** A hard-coded picture drifts
the first time a node is added, and the hosted viewer needs a sign-in and a
network the venue may not have.

**The governance surfaces are rendered from the structures that enforce them.**
The evidence allowlist, the toolset partition and the peer roster are each served
from the object the code actually consults. A separately maintained description
of a safety property is a description that will one day be wrong while looking
right.

**The console is mounted last, deliberately.** Its catch-all would shadow every
API route mounted after it. This is one line and one comment, and it is the kind
of thing that is discovered at the worst possible moment.

**Tier hints match whole tokens.** "gemini" contains "mini". A substring check
files the Pro tier as a small model and routes the reasoning work to the cheap
one - silently, correctly-looking, and only visible as slightly worse answers.
Splitting on separators first is the whole fix.

*Alternative considered.* A hard-coded map of alias to tier. It is exactly the
thing that cannot survive being pointed at somebody else's gateway.

**An empty tier degrades rather than raises.** Pipeline code asks for "the
reasoning model" unconditionally, so on a flash-only gateway the honest answer is
the best model available. Raising would turn a deployment question into a failure
in the middle of a correction run.

*And the test asserts the degradation rather than the tier.* The previous test
asserted that a reasoning tier existed, which is a claim about one deployment.
It would have passed forever on the developer's gateway and failed on the first
real one.

**A pin is validated against the gateway's own list.** Tier hints read names, and
several flash-class models differ in capability but not in name, so a deployment
gets the last word - but a retired alias should surface at startup as a warning,
not as a 404 from inside a run.

**The fallback list is parsed from the shipped gateway configuration.**
Duplicating the aliases in code creates two lists that diverge the first time
either is edited. The test asserts against the file rather than against a
hard-coded alias, so retuning the deployment's model list does not break a test
about parsing.

**Write-back edits lines, it does not rewrite the file.** The team hand-edits
this file, and a rewrite that drops the comments explaining what each setting
does would be worse than not persisting at all. Genuinely new keys go under a
marked section so the file stays readable.

**A credential is never created.** Updating a key that is present is fine;
introducing a secret into a file that does not have one is the operator's
decision, and a tool that writes credentials to disk on your behalf is a tool
nobody should run.

**Configuration loading belongs to entry, not to one entry point.** There are
several front doors - the app, the hosted graph viewer, the tool servers, the
build and demo scripts - and only one of them used to read `.env`. Loading uses
set-if-absent, so a real environment variable and a command-line override both
still win, which is what lets a test pin its database before importing anything.

**Attaching to an existing gateway is the default when one is named.** Starting a
second proxy while talking to the first is a pure waste, and the second is doomed
regardless: the provider credentials live in the gateway you attached to.

## Risks / Trade-offs

**No route-level test exists.** The route bodies are thin and the functions
beneath them are covered, but a wiring mistake - a renamed keyword, a field read
off the wrong object - is exactly the class of defect this layer already shipped
twice. → Recorded as an open task rather than papered over; the two that shipped
are named in the proposal so the next reader knows the class is real.

**The console is shipped and unspecified.** → Deliberate. There is not one
frontend test in the repository, and a specification with nothing behind it would
be unevidenced prose. The route contract beneath it is where the checkable claims
are.

**The spend total is only as good as the per-stage records.** A stage that
recorded nothing is indistinguishable from a stage that did not run. → Correct
as written: a stage that fell back to its deterministic path genuinely spent
nothing, and reporting zeroes for it would suggest it reached a model.

**Tier classification is a heuristic over names.** A gateway whose aliases say
nothing useful defeats it. → Which is exactly why the per-tier pin exists, and
why the pin is validated rather than trusted.

**The response cache makes a rehearsed run deterministic and could therefore
hide a broken live path.** → The cache is switchable at runtime and the switch is
persisted, so proving the calls are real is one toggle rather than a rebuild.

**Reading `.env` at entry with set-if-absent means a stale file quietly loses to
a stale environment variable.** → The gateway address in use is reported by the
health route and on the model listing, so which one won is observable rather than
guessed at.

## Migration Plan

1. Replace the supply-chain routes and fix the two that had never run; take the
   change-set routes to change sets.
2. Build the console against that contract, then rebuild the committed bundle.
3. Move configuration loading to the bootstrap, make attaching the default, and
   land the tier pins with the degradation test that replaces the deployment
   claim.
4. Fix the launcher's seed-data key and add the port check.
5. Document the whole thing, including the choices that look like shortcuts.
6. Correct the console's own narration afterwards, as a separate pass done by
   using the application rather than by reading it.
7. Rollback is `git revert` of the commits; the only persisted state is the
   written configuration file, whose write-back is line-level and reversible by
   hand.
