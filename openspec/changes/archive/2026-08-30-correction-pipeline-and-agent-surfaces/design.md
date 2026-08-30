## Context

See proposal.md - Why. The deterministic substrate is in place: validation,
propagation, ingestion and publishing all decide the right questions and none of
them calls a model. What is missing is the loop that reads a supplier document,
argues what it means, turns the answer into content, and takes it to a person.

Constraints that shape the approach:

- **The gateway may be unreachable and the run must still finish.** The graph
  suite pins the gateway at a closed port. Every stage that consults a model is
  therefore written fallback-first, and the fallback is the path CI exercises.
- **Checkpointed state is msgpack.** Everything crossing into state is plain
  JSON - no enums, no datetimes, no models. A node dumps to primitives at its
  own boundary.
- **A revision re-enters the same thread.** LangGraph has no way to clear an
  accumulating field from a node: returning an empty list appends nothing, it
  does not empty. Anything additive therefore needs an explicit reset marker.
- **The approval gate is a real `interrupt()`.** The process may be killed while
  a reviewer is at lunch, so the gate has to be a suspension with a written
  checkpoint rather than a blocking call.
- **The publish gates live below this layer**, at the tool boundary. Nothing in
  the orchestration may be relied on to enforce them, and nothing here tries.

## Goals / Non-Goals

**Goals:**

- One run that carries a correction from the record to a signed decision, whose
  every step is inspectable from the run's own artefact.
- A bound on what a model may conclude that is enforced by the code that reads
  its answer, not by the prompt that asks the question.
- A revision that is visibly a continuation of one decision rather than a second
  incident.
- Two protocol surfaces that are real - discoverable, callable, and provably
  identical to the in-process path - without either becoming load-bearing.

**Non-Goals:**

- Autonomy. Nothing here decides to publish, and no peer can.
- Multi-agent negotiation. Four peers is four seams another team could own, not
  a society.
- A model in the decision path. Where a model is consulted, its answer is
  checked, overridden or discarded by ordinary software before it reaches a
  reviewer.
- Making a transport required. Both switches default off, and a failure on
  either falls back rather than propagating.

## Decisions

**Fallback-first, and no LLM mocking anywhere.** Every model call sits inside a
`try` whose `except` is a complete answer rather than a degraded one. A mocked
model tests the mock; a closed port tests the fallback. The cost is that the
suite never exercises the model path, which is the correct trade: the model path
failing is a bad demo, and the fallback path failing is a system that cannot
run at all.

*Alternative considered.* Recording live responses and replaying them. It would
have exercised more code and would also have made the tests a claim about one
deployment's model catalogue, which is precisely what this project has already
been bitten by once.

**The scope fallback is the widest reading, deliberately.** Applied too widely, a
correction republishes a number on a page it does not belong on - which a
reviewer sees and rejects. Applied too narrowly, a wrong number stays live and
nobody sees it at all. Fail safe, not fail silent; and the low confidence and the
stated rationale mean the reviewer is told which it is.

**A case is one product, not one document.** The publish lock is
channel-and-product, so the product is the unit actually committed. Grouping by
document would split the day-18 disagreement - two documents about one product -
across two cases, which is exactly the wrong seam.

**The case filter goes after extraction, not before it.** This is the second
attempt and the first one was a no-op, which is worth recording. Filtering inside
the monitoring step looked right and failed for a reason that only shows on a
fresh record: signals are derived from the facts in force, a correction still
sitting in an unread document is not yet a fact, so the filter had an empty list
to filter and everything extraction then read arrived behind it. The regression
test deliberately seeds no prior run so that condition is what it runs under.

*Consequence stated as a principle.* **Extraction is global; action is
case-scoped.** A document is read once whatever case is running and its facts are
recorded either way, because a run that skipped a document would leave the case
nobody has decided yet unreadable. Only the signals a run acts on are narrowed.

*And a second line of defence.* The escalation test is taken over the products
the case names rather than over everything the radius reached, because a union
radius legitimately arrives at unrelated products through a shared document. Two
mechanisms for one property is right here: the filter is the fix, and the scoped
escalation is what stops the same class of leak arriving through a different
door.

**Its own node, not three lines in the classification step.** Which corrections a
run may act on is the boundary the reviewer is being asked to approve, so it
belongs in the trace where they can read it.

**The mandatory evidence is resolved before the model is prompted.** Not a
prompting nicety: "does this apply to the base model or the variant" is a
question about the current catalog, and a retrieved postmortem will assert an
answer that a model reading it will believe. Left to its own judgement the
investigator consistently decides the corpus already told it and scopes a
correction on a citation rather than on the record.

*Two budgets, not one.* A required lookup that fell off the end of the model's
allowance would be a governance rule the run quietly skipped, so the required and
chosen budgets are separate and the trace labels which is which. A request the
agent chose to make is a different claim from one the standard required, and
collapsing them would overstate what the model decided.

**Refusals are records, not absences.** The desk is the one place a model chooses
an action, so what it wanted and did not get is the interesting half of the
audit trail. Nothing on the desk raises: a lookup that cannot answer is a fact
about the investigation.

**The reset marker rather than a second state channel.** LangGraph's reducers
append; there is no clear. A marker at the head of an update is the only
mechanism available, so it is used consistently and applied at exactly one point
- the head of a revision - rather than scattered across every node that writes an
accumulating field. Scattering it would mean every future node has to remember it
is on a revision.

**A carried reading is matched by what it does, not what it is called.** A
revision re-proposes the same reading under a fresh identifier, so name matching
would report every revision as a move and would validate the same plan twice. The
carried reading also gets a fresh change-set identifier, because validation keys
its idempotency on that - reusing it would return the previous revision's verdict
against the new world, which is the exact failure re-planning exists to avoid.

**A withdrawn approval is a rejection, not a cleared interrupt.** Clearing the
gate through a state update would leave a recommendation that simply vanished.
Delivering a real REJECT through the same interrupt a reviewer uses puts it in
the ledger with decided provenance, an actor and a reason.

**Six toolsets, partitioned by owner, with the writes concentrated.** A single
server exposing seventeen flat tools is one system with a protocol bolted on. The
partition is only worth having if it lets an operator hand out five surfaces and
withhold the sixth, which is why the test asserts that exactly one toolset
mutates once the tape control is set aside. Before this change two toolsets wrote,
one of them named for an inventory read.

*The tape control is the one exception, stated rather than hidden.* Releasing the
next event moves the clock and never the catalog, and in a real deployment
nothing would expose a tool that manufactures events at all.

**Only reads cross the wire.** Committing over a pipe that might have died
halfway is worse than committing in-process, and a route whose two transports
disagree about the shape of an answer would make the switch a behavioural change
- the one thing it must not be. Both transports record which path each call
actually took, so the console shows what happened rather than what was
configured.

**The approval gate is not a peer, and neither is publishing.** A human decision
is not a capability to delegate, and a peer that could publish is a peer that
could publish.

**One failure retires a peer or a toolset for the process.** Retrying a server
that will not start, once per lookup, turns a misconfigured switch into a run
that appears to hang. Reviving is explicit, so fixing the configuration does not
need a restart.

**The copy peer's own implementation is the deterministic renderer.** That is
what makes the seam swappable: another team's brand-voice model replaces the
handler, and until they do the factory still produces publishable copy from the
catalog alone. It refuses an ambiguous literal rather than guessing - the
comparison table quotes both variants at the same figure, and substituting would
rewrite the base model's row, which is the whole base-versus-variant error
reached by regex instead of by a bad decision.

## Risks / Trade-offs

**The fallback paths are the tested paths, so the model paths are not.** A
prompt change that breaks a live run would not fail CI. → The reply is validated
before use everywhere it matters - a recommendation may only name a validated
candidate, an extracted value must parse as its declared type against a known
attribute and entity, an enrichment must quote a supplied chunk - so a bad reply
degrades to the fallback rather than corrupting the run.

**Two mechanisms enforce case scoping and could drift apart.** → They fail in
opposite directions: the filter narrows what a run acts on, the scoped escalation
narrows what a severity may be argued from. A regression in either is visible in
the severity sentence, which is asserted directly.

**The blast radius and the case filter can disagree about what "affected"
means.** The radius is deliberately a superset. → Stated in the modified
`blast-radius` requirement rather than left implicit, so the next reader knows
the totals are reach and not grounds.

**The retry cycle is bounded at one.** A genuinely contended publish gives up and
queues rather than converging. → Correct for now: two retries against a moving
record is a busy-wait, and the unresolved status is a finding a reviewer can act
on.

**A peer roster mounted on one process is a deployment choice that could be
mistaken for an architectural one.** → The cards are built and served the same
way whether the peer is local or not, and the tests assert the answers are
identical across the boundary, so moving a peer to its own host is a change to a
base URL.

**The evidence desk's bound is small enough to cut off a genuine
investigation.** Two extra passes, three requests each. → An investigation that
cannot resolve a scope question in three passes will not resolve it in thirty,
and the widest-reading fallback is a safe place to land.

## Migration Plan

1. Retarget state, the evidence desk and the prompts first - the pipeline is
   written against them.
2. Replace the graph wholesale, including the content leg that had no
   predecessor; land the branch nodes and the one bounded cycle with it.
3. Repartition the peers and the toolsets; delete the toolsets that described
   the previous estate.
4. Land the four test files with the gateway pinned to a closed port, and
   confirm the fallbacks are what runs.
5. Add case scoping last, as its own node, with a regression test that seeds no
   prior run.
6. Rollback is `git revert` of the five commits. No persisted state is worth
   preserving; the checkpoint database is separate from the audit ledger by
   design, so resetting run history never touches the evidence.
