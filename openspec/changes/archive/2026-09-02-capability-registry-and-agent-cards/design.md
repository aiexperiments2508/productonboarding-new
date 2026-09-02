## Context

Three things were already in place and each decided part of this change.

The tier registry reads the gateway's own `/v1/models`, classifies on whole
tokens, honours a per-tier pin and validates it against what is served. It was
already the right design; what it did not do was own *every* path, so two
fallbacks sat outside it and rotted.

The A2A peers already publish real Agent Cards, built field by field from the
SDK's protobuf types so a typo is an `AttributeError` here rather than a
client-side surprise later. The cards were fine. Nothing indexed them.

The estate change made connections a runtime record with a `discovered_tools`
column and an `admitted_tools` column that nothing yet read. This change is
where the second column starts meaning something.

## Goals / Non-Goals

**Goals:**

- No model identifier in application code, and a guard that keeps it that way.
- A directory a stranger can find, that cannot drift from the cards it lists.
- The peer/system distinction preserved rather than smoothed.
- Admission mechanised: connecting widens nothing; admitting widens exactly one
  tool, and only while its system answers.

**Non-Goals:**

- Registering peers dynamically. A peer is code in this repository; discovering
  one at runtime would mean executing something this repository did not ship,
  which is a different and much larger conversation.
- Automatic admission. Argued below - it is the decision most likely to be
  reversed by somebody optimising for convenience.
- A model *catalogue* with capability metadata. The registry already answers
  which tier a model belongs to, which is the only question the graph asks.

## Decisions

**No model identifier, and no default that is "probably fine".** The two lists
existed to make an outage degrade gracefully, and they made it degrade
misleadingly: every alias they held had gone stale, so the picker rendered
options the gateway would have refused.

The lesson is not "keep the lists updated". It is that a list which is only
consulted when something is broken will be stale when it is consulted, because
nothing exercises it. The configuration is parsed instead, and where there is no
configuration either, the honest answer is that no model is available.

*The sharp end.* `resolve_tier` now raises rather than returning an alias. A
caller handed a string will use it, and the 404 surfaces from inside a run,
several nodes deep, where the cause is expensive to find. Raising here costs a
clear error at the point of configuration.

**A grep test, which is a blunt instrument and the right one.** Reintroducing a
default alias reads as helpful in review - it is a one-line change that makes an
error message friendlier. The only reliable guard is one that fails.

The pattern requires a family name, a separator and then a version or a named
tier, because a guard that fires on the dict key `"command"` gets deleted by the
next person who sees it red. It ignores comments, because the tier classifier's
own explanation of why `"gemini"` contains `"mini"` is worth keeping.

**The directory is built from the cards, not beside them.** An inventory that
lists names would drift within a release and drift silently: the directory would
still look complete, which is the failure mode that matters for a document whose
whole purpose is to be believed by somebody who cannot check it.

It is also built from what `mount` actually returned, so a peer that failed to
publish is absent rather than advertised. A directory naming something nobody
can reach is worse than a short one.

**Peers and systems stay apart.** This is the decision a reviewer is most likely
to want simplified, and it should not be. A peer is a capability this system
implements and another organisation may call. A connected system is a capability
this system knows how to *ask for*. One list would say the estate can do things
it can only delegate - and the reader least able to check that is exactly the
reader a discovery document is for.

**Limits are stated, not implied.** Every peer entry carries what it may not do.
The approval gate and publishing are deliberately not peers; a directory that
merely omits them leaves a reader to conclude they were forgotten rather than
excluded. Saying so costs one field and removes the ambiguity.

**Admission is a separate human act, and stays one.** The obvious convenience is
to admit a connected system's read-only tools automatically - the system says
they are read-only, and the desk only wants read-only tools.

That reasoning is circular. "Read-only" is the connecting system's own claim
about itself, and the desk's allowlist exists precisely because a tool's own
description of itself is not a control. A system that could widen the desk by
connecting makes the allowlist a formality, and the allowlist is the entire
reason handing this desk to a model is uninteresting rather than alarming.

*What is automatic.* Visibility. A connected system's tools appear in the
registry, the console and the directory the moment it connects. What requires a
person is the step from *visible* to *callable*.

**An admitted tool leaves the catalogue while its system is degraded.** A
catalogue offering something unreachable spends a model's bounded rounds finding
that out, and those rounds are capped for a reason.

## Risks / Trade-offs

**Raising where the code used to return.** A deployment with no gateway and no
`litellm/config.yaml` now fails at model resolution instead of proceeding with
an alias that would have 404'd. That is louder, and it is louder at the point
where the cause is obvious. The whole test suite runs with the gateway
unreachable and does not hit this, because the configuration is present.

**The grep guard will produce a false positive eventually.** Some legitimate
string will look like an alias. The pattern is deliberately narrow and the
failure message names the file and line, so the fix is a second's work - which
is the cost of a guard that cannot be argued with.

**The directory is unauthenticated.** It is under `.well-known`, which is the
point: discovery is meant to work for somebody who has not been introduced. It
carries capability names, endpoints and states - nothing about products,
suppliers or corrections. Worth revisiting if a system's identifier ever becomes
sensitive, and noted rather than solved.

**Admission has no audit line.** Admitting a tool changes what a model can
reach and is currently a state change with no entry in the ledger. It should
have one, and does not.

## Migration Plan

No data migration. `connections.admitted_tools` already existed and was empty,
so every existing connection begins with nothing admitted, which is the correct
starting state.

A deployment relying on the removed embedding default now needs
`LITELLM_EMBED_MODEL` set or a gateway that serves an embedding model - the
latter being the normal case, since an index cannot be built without one either
way.

## Open Questions

- Whether admitting a tool should be recorded in the audit ledger alongside
  approvals and publishes. It is a governance decision with a person behind it
  and the ledger is where those live; it is out of scope here only because the
  ledger's schema is shaped around a correction case and an admission is not
  one.
- Whether a peer should be able to declare limits it discovers rather than
  having them written here. The current list is authored, and an agent whose
  handler quietly gained the ability to publish would still advertise that it
  cannot.
