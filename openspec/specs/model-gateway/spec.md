# model-gateway Specification

## Purpose
The single egress to a model: what a deployment actually serves, how those
models are sorted into the tiers the pipeline asks for by name, what happens when
a tier is empty or a pin is stale, and how a selection is persisted without
damaging the file it is written to.

## Requirements

### Requirement: A tier is classified on whole tokens, not substrings

A model identifier SHALL be split on its separators and matched against tier
hints as whole tokens. Substring matching is wrong here and quietly so: "gemini"
contains "mini", so a substring check files every Gemini model - the Pro tier
included - as a small model and routes the reasoning work to the cheap one.
Every model SHALL land in exactly one tier.

#### Scenario: Nine identifiers land in the tier their name implies

- **WHEN** each of a Pro, a preview Pro, an Opus, a Flash, a Flash-Lite, a Mini,
  a Haiku and two embedding identifiers is classified
- **THEN** the first three are reasoning, the next four are fast, and the last
  two are embedding
- **AND** `tests/test_models.py::test_tier_classification` asserts each

#### Scenario: A Gemini Pro is not mistaken for a mini model

- **WHEN** a Gemini Pro identifier and a GPT mini identifier are classified
- **THEN** the Pro is reasoning and the two do not classify the same
- **AND** `tests/test_models.py::test_gemini_is_not_mistaken_for_a_mini_model`
  asserts both

#### Scenario: Every listed model is in exactly one tier

- **WHEN** the model listing is grouped by tier
- **THEN** the fast and embedding tiers are populated, and concatenating the
  three tiers reproduces the full listing exactly
- **AND** `tests/test_models.py::test_listing_groups_by_tier` asserts each - and
  deliberately does not assert that a reasoning tier exists, which would be a
  claim about one deployment rather than about the code

### Requirement: The fallback list is parsed from the shipped configuration

Where the gateway cannot answer, the model list SHALL be parsed from the shipped
gateway configuration rather than duplicated in code, so it cannot drift from
what the gateway would actually serve. The listing SHALL say whether it came from
the gateway or from the fallback, and SHALL carry the reason it fell back, so a
stale list is never presented as current.

**No model identifier SHALL appear in application code at all** - not as a
default, not as a last-resort fallback, and not as a tier hint's example. Two
such lists survived in the client for exactly this purpose and both had gone
stale against the shipped configuration, so an outage produced a picker whose
every entry the gateway would have refused. A wrong answer offered confidently
is worse than none.

Where neither the gateway nor the configuration names a model, the system SHALL
say that no model is available rather than returning an invented alias. A caller
handed a name will use it, and the refusal then surfaces from inside a run
instead of at the point where the cause is obvious.

#### Scenario: With no gateway reachable the list is the shipped aliases

- **WHEN** the model list is refreshed against an unreachable gateway
- **THEN** the listing reports the fallback as its source, carries an error, and
  holds exactly the aliases named in the shipped configuration, including at
  least one embedding model
- **AND** `tests/test_models.py::test_fallback_is_parsed_from_the_shipped_config`
  asserts each, against the file rather than against a hard-coded alias

#### Scenario: No model identifier is written in the application

- **WHEN** the application's own modules are searched for a model identifier
- **THEN** none appears outside the shipped gateway configuration and the
  environment
- **AND** `tests/test_models.py::test_no_model_is_named_in_application_code`
  asserts the absence

#### Scenario: With nothing served and nothing configured, the answer is none

- **WHEN** a tier is resolved with no gateway reachable and no configuration
  present
- **THEN** the caller is told no model is available, and no alias is returned
- **AND** `tests/test_models.py::test_no_model_available_is_said_rather_than_invented`
  asserts both

### Requirement: A tier the gateway does not serve degrades rather than failing

The pipeline asks for a tier by name, unconditionally. Where that tier is empty -
a gateway serving only flash-class models genuinely has no reasoning tier - the
strongest model actually available SHALL be returned. Raising from inside a run
is not an acceptable answer to a deployment question.

#### Scenario: Reasoning degrades to the strongest fast model

- **WHEN** the reasoning tier is resolved against a gateway that serves no
  reasoning tier
- **THEN** the model returned is one of the fast tier's
- **AND** `tests/test_models.py::test_reasoning_degrades_to_the_strongest_fast_model`
  asserts it

### Requirement: A tier can be pinned per deployment, and the pin is validated

Tier hints read names, and several flash-class models differ in capability but
not in name, so a deployment SHALL be able to name the model for a tier outright
and have that win. The pin SHALL be checked against what the gateway actually
serves rather than trusted: a retired alias SHALL surface as a warning and fall
back to the tier, at startup, rather than as a 404 from inside a run.

#### Scenario: A pinned tier is honoured

- **WHEN** a served model is pinned as the reasoning tier
- **THEN** resolving the reasoning tier returns exactly that model
- **AND** `tests/test_models.py::test_a_tier_can_be_pinned_per_deployment` asserts
  it

#### Scenario: A pin the gateway does not serve is refused with a warning

- **WHEN** an unserved alias is pinned as the reasoning tier
- **THEN** a runtime warning is raised, the pin is not returned, and the model
  returned is one the gateway serves
- **AND** `tests/test_models.py::test_a_pin_the_gateway_does_not_serve_is_refused`
  asserts each

### Requirement: A selection is effective immediately and survives a restart

Selecting a model, an embedding model or the response cache SHALL take effect on
the running process without a restart and SHALL be written back so it survives
one. Writing only one of the two would either revert on the next launch or
require a restart to take effect.

#### Scenario: A model selection is hot-loaded and persisted

- **WHEN** a served model is selected
- **THEN** it is reported active, the process environment names it, the gateway
  resolves to it, and the written configuration file names it
- **AND** `tests/test_models.py::test_selection_is_hot_loaded_and_persisted`
  asserts each

#### Scenario: The cache toggle round-trips

- **WHEN** the response cache is switched off and then on
- **THEN** the gateway reports it off and then on, and the written file records
  each
- **AND** `tests/test_models.py::test_cache_toggle_round_trips` asserts each

#### Scenario: An embedding model selection is honoured at runtime

- **WHEN** an embedding model is selected
- **THEN** the gateway resolves embeddings to it
- **AND** `tests/test_models.py::test_embed_model_selection_is_honoured_at_runtime`
  asserts it

### Requirement: Write-back preserves the file and never invents a credential

The configuration file is hand-edited, so a write SHALL update a value on its
existing key's own line and leave comments, ordering and every other line
untouched; a key that was genuinely absent SHALL be appended under a marked
section. Existing comments SHALL never be lost. A secret SHALL NOT be created
into a file that does not already carry it - updating a credential that is
present is fine, writing one that is not is the operator's decision. A write with
nothing to change SHALL not touch the file at all.

#### Scenario: Comments and unrelated keys survive a write

- **WHEN** a model and a cache setting are written back
- **THEN** every comment present before is still present, and an unrelated
  credential key is untouched
- **AND** `tests/test_models.py::test_write_back_preserves_comments_and_other_keys`
  asserts both

#### Scenario: A credential is skipped, a managed key is created

- **WHEN** a write is asked to set both a credential and a model into a file that
  carries neither
- **THEN** the credential is reported skipped and its value does not appear in
  the file, while the model is reported created
- **AND** `tests/test_models.py::test_write_back_never_invents_a_credential`
  asserts each

#### Scenario: No change writes nothing

- **WHEN** a selection is made with no values
- **THEN** the file is byte-identical
- **AND** `tests/test_models.py::test_no_change_writes_nothing` asserts it

### Requirement: An unusable selection is refused before it reaches a run

A model the gateway does not serve SHALL be refused with the reason and the list
of what is available, and SHALL NOT be written. An embedding model asked to serve
chat SHALL be refused as the wrong tier. Failing at selection is cheap; failing
inside a run is not.

#### Scenario: An unknown model is rejected and not persisted

- **WHEN** a model the gateway does not serve is selected
- **THEN** the selection is refused as an unknown model and the written
  configuration does not name it
- **AND** `tests/test_models.py::test_unknown_model_is_rejected_before_it_reaches_a_run`
  asserts both

#### Scenario: An embedding model cannot be selected for chat

- **WHEN** an embedding model is selected as the chat model
- **THEN** the selection is refused as the wrong tier
- **AND** `tests/test_models.py::test_embedding_model_cannot_be_selected_for_chat`
  asserts it

### Requirement: An unreachable gateway fails fast and is reported, never fatally

Every model call SHALL go through one egress so that selection, token accounting
and cost are captured in one place. Where the gateway cannot be reached, repeated
connection attempts SHALL be suppressed for a cooldown after a small number of
consecutive failures, so a run degrading gracefully does not also spend twenty
seconds per node paying connection timeouts. A caller SHALL receive a gateway
error it can catch and fall back from, carrying a message an operator can act on,
and a successful probe SHALL clear the suppression so starting the gateway
mid-session recovers without a restart.

**Every invocation through that egress SHALL append to the spend ledger**,
embedding calls included, and the append SHALL NOT be able to raise into the
call it is recording. Capturing accounting in one place is only true if the
place records every call; embedding spend that is not written down is a reindex
that costs real money and reports nothing.

**A breached spend cap SHALL raise the same gateway error an unreachable
gateway raises.** Every model step already has a deterministic fallback for
that error and the whole suite exercises those fallbacks, so a cap degrades the
system exactly as far as losing the network does - narrower answers, reported as
narrower - rather than introducing a failure mode nothing has a fallback for.

The cap MAY overshoot by up to one batch of concurrent calls, because
concurrent readers clear the check together before any of them records a token.
Closing that would mean serialising calls deliberately made concurrent, to
harden a control whose design is to be soft.

#### Scenario: A run against a closed port completes and says the gateway was unreachable

- **WHEN** a full correction run is executed with the gateway pinned to a closed
  port
- **THEN** the run completes and records an error naming the gateway as
  unreachable, rather than raising
- **AND** `tests/test_graph.py::test_the_correction_is_read_without_a_model`
  asserts the recorded error, and the graph, branch and replan suites all run
  under that pinning

#### Scenario: A reply that is not a JSON object is a gateway failure

- **WHEN** a model answers a structured request with an array or a string
- **THEN** it is refused as a gateway error rather than returned, so the caller
  routes into the deterministic fallback it already has instead of failing
  halfway down a node
- **AND** this is verified by inspection of the parse guard; no test covers it
  directly

#### Scenario: A breached cap degrades the run rather than failing it

- **WHEN** a spend cap is breached and a model step runs
- **THEN** the step receives the same error it receives from an unreachable
  gateway and takes its existing fallback
- **AND** `tests/test_tower.py::test_a_breached_cap_refuses_the_way_an_unreachable_gateway_does`
  asserts it

#### Scenario: Embedding spend is recorded like any other call

- **WHEN** an embedding request leaves the egress
- **THEN** a ledger row is written for it
- **AND** `tests/test_tower.py::test_spend_is_attributable_to_a_feed_and_a_surface`
  asserts the attribution the row carries
