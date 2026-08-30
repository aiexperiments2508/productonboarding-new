# evidence-desk Specification

## Purpose
The closed, read-only set of lookups the scope investigation may call - the one
place in this system where a model chooses an action rather than describing one.
It answers the questions the catalog alone can settle before the model is asked
anything, bounds what else may be asked, and records refusals as evidence.

## Requirements

### Requirement: Every tool on the desk is read-only

No entry on the desk SHALL write a fact, take a publish lock, move a listing or
otherwise change state. Membership SHALL be checkable by name against the
declared mutating surface rather than by inspecting behaviour, so a tool that
becomes mutating later fails this before it ships. Where a desk entry is also
owned by a published toolset, the two classifications SHALL agree.

#### Scenario: No allowlisted tool is on the mutating surface

- **WHEN** the desk's allowlist is compared with every mutating tool declared
  across the toolsets, plus the writing entry points outside them
- **THEN** the two sets do not intersect, and the mutating set is non-empty so
  the check is not vacuous
- **AND** `tests/test_replan.py::test_every_allowlisted_tool_is_read_only` asserts
  both

#### Scenario: A desk entry the registry also owns is on a read-only toolset

- **WHEN** each allowlisted tool that a toolset owns is looked up
- **THEN** it is not among that toolset's mutating tools
- **AND**
  `tests/test_replan.py::test_an_allowlisted_tool_the_registry_knows_is_on_a_read_only_toolset`
  asserts it for every such tool

### Requirement: The catalogue offered to the model is the allowlist

The tool list presented to the investigator SHALL be rendered from the allowlist
itself, naming each tool and what it takes, and SHALL hold exactly as many
entries as the allowlist - so the prompt cannot drift from the governance
actually in force.

#### Scenario: The rendered catalogue matches the table entry for entry

- **WHEN** the catalogue is rendered
- **THEN** every tool appears with the argument it takes, and the catalogue has
  exactly one line per allowlisted tool
- **AND** `tests/test_replan.py::test_the_catalogue_offered_to_the_model_matches_the_allowlist`
  asserts both

### Requirement: A request outside the allowlist is refused and recorded

A request naming a tool that is not on the allowlist SHALL be refused, not
executed, and the refusal SHALL be recorded with the tool asked for and the
reason the investigator gave for asking - because what the investigator wanted
and did not get is often the more interesting half of the trace. A request
naming an allowlisted tool with no argument SHALL be refused with a message
saying what that tool wanted, so the investigator can recover.

#### Scenario: Naming a publishing tool is refused rather than executed

- **WHEN** the investigator asks to commit a plan
- **THEN** one record comes back, refused, saying that is not an allowed evidence
  tool
- **AND** `tests/test_replan.py::test_a_tool_outside_the_allowlist_is_refused_not_executed`
  asserts each

#### Scenario: A refusal sits beside the answer it did not get

- **WHEN** a valid lookup and a nonsense one are requested together
- **THEN** the first is answered and the second refused, both records name the
  tool asked for, and the refusal carries the stated reason for asking
- **AND** `tests/test_replan.py::test_a_refusal_is_recorded_rather_than_dropped`
  asserts each

#### Scenario: A tool called without its argument is refused with guidance

- **WHEN** an allowlisted lookup is requested with an empty argument
- **THEN** it is refused and the message states what that tool takes
- **AND** `tests/test_replan.py::test_a_tool_called_without_its_argument_is_refused_with_guidance`
  asserts both

### Requirement: A failing lookup is evidence, not a dead run

A lookup that cannot answer SHALL return that fact as a record rather than
raising, because a failed lookup is a fact about the investigation and not a
reason to abandon a run that still has a deterministic path to a recommendation.

#### Scenario: Asking about a document that does not exist returns an error record

- **WHEN** the version history of an unknown document is requested
- **THEN** one record comes back carrying an error, and nothing raises
- **AND** `tests/test_replan.py::test_a_failing_lookup_is_evidence_rather_than_a_dead_run`
  asserts both

### Requirement: The investigation is bounded

The number of extra rounds the investigator may take, and the number of requests
it may make in a round, SHALL both be capped at declared, inspectable limits. An
uncapped investigation against a paid gateway is a bill rather than a feature.

#### Scenario: The declared bounds are real and small

- **WHEN** the desk's limits are read
- **THEN** at least one extra pass is allowed and no more than three, and at
  least one request per pass is allowed
- **AND** `tests/test_replan.py::test_the_loop_is_bounded` asserts each

### Requirement: The catalog's own answers are resolved before the model is asked anything

"Does this correction apply to the base model or to the variant" and "which
versions of this document exist" are questions about the *current catalog*. A
retrieved postmortem will assert an answer and a model reading one will believe
it, but a document records what was true when it was written while the catalog
moves underneath it. The desk SHALL therefore resolve those lookups from the
catalog before the investigator is prompted, SHALL label them as required rather
than as the investigator's own, and SHALL cap how many it takes.

#### Scenario: The standing questions are asked of the catalog, not the corpus

- **WHEN** the required lookups for a correction citing a document are assembled
- **THEN** they include the variant comparison for the product and the version
  history for the cited document, every one is labelled as required, and the set
  is within the declared cap
- **AND** `tests/test_replan.py::test_the_standing_questions_are_about_the_catalog_not_the_corpus`
  asserts each

#### Scenario: Required lookups are executed before any the investigator chose

- **WHEN** the required lookups and one request the investigator chose to make
  are run together
- **THEN** the investigator's request is last, everything before it is labelled
  required, and exactly one record is labelled as the investigator's
- **AND** `tests/test_replan.py::test_mandatory_requests_run_before_any_agent_request`
  asserts each

### Requirement: A safety-class correction pulls the rules that would block it

Where a correction touches a safety-class attribute, the desk SHALL also resolve
the publishing rules of the affected channels, because what a safety-class
attribute fails closed on is a channel rule and the rule is therefore evidence.
Those channels SHALL be taken in a stable order so a re-run produces the same
trace, and SHALL be capped. A correction touching nothing safety-class SHALL pull
no channel rules.

#### Scenario: An allergen correction pulls its channels' rules, in order

- **WHEN** the required lookups for an allergen correction are assembled
- **THEN** channel rules are among them, the channels are in sorted order, and
  there are no more than the declared cap
- **AND** `tests/test_replan.py::test_a_safety_class_correction_also_pulls_the_channel_rules`
  asserts each

#### Scenario: A non-safety correction pulls no channel rules

- **WHEN** the required lookups for a rated-power correction are assembled
- **THEN** none of them is a channel-rule lookup
- **AND**
  `tests/test_replan.py::test_a_correction_that_touches_nothing_safety_class_pulls_no_channel_rules`
  asserts it

### Requirement: The required lookups have their own budget

The budget for lookups the standard requires SHALL be separate from the budget
for lookups the investigator chose, so a governance question can never fall off
the end of the model's allowance and become a rule the run quietly skipped.

#### Scenario: A flood of chosen requests cannot crowd out a required lookup

- **WHEN** twelve requests the investigator chose are run ahead of the required
  lookups
- **THEN** the investigator's requests are held to its own allowance and every
  required lookup still ran
- **AND** `tests/test_replan.py::test_an_agent_flood_cannot_crowd_out_a_mandatory_lookup`
  asserts both
