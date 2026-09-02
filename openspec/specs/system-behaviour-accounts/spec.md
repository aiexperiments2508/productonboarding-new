# system-behaviour-accounts Specification

## Purpose

Joining a finding to what the estate declares about the system that caused it,
so a reviewer reading "this supplier sent it" also reads what that supplier is
for, who owns it, and how it is known to misbehave.

The rule this capability exists under: **an account is written after the
verdict and cannot reach it.** A system's declared reputation is suggestive and
must never become evidence about a product.

## Requirements

### Requirement: An account runs after the verdict and cannot change it

An account of a finding SHALL be produced only after the verdict has been
decided, SHALL be given the finding rather than the record, and SHALL have no
route by which it can alter the outcome.

A system "known to send stale allergen data" is a fact about the system. Letting
it weigh on whether *this* product is fit to launch would make a supplier's
reputation into evidence about a shipment, which is exactly the substitution
the deterministic verdict exists to prevent.

#### Scenario: Explaining a product cannot change its verdict

- **WHEN** a product is assessed and then explained
- **THEN** the verdict before and after are the same
- **AND** `tests/test_rca.py::test_explaining_a_product_cannot_change_its_verdict`
  asserts it

#### Scenario: A clean product is offered no explanation

- **WHEN** a product with no findings is submitted for explanation
- **THEN** none is offered, because there is nothing to account for
- **AND** `tests/test_rca.py::test_a_clean_product_is_offered_no_explanation`
  asserts it

### Requirement: An account names the system, its owner and a defect it declares

An account SHALL name the system that caused the finding and the team that owns
it, and any misbehaviour it attributes SHALL be one that system's own manifest
entry declares.

Inventing a plausible defect is the failure mode here, and it is a defamatory
one: the account is about a named external party.

#### Scenario: The account names the system and its owner

- **WHEN** a finding naming a system is explained
- **THEN** the account carries that system and the team that owns it
- **AND** `tests/test_rca.py::test_a_cause_names_the_system_and_the_team_that_owns_it`
  asserts both

#### Scenario: Only a declared defect is named

- **WHEN** an account attributes a defect to a system
- **THEN** that defect is one the manifest declares for it
- **AND** `tests/test_rca.py::test_the_defect_named_is_one_that_system_actually_declares`
  asserts it

### Requirement: An account is produced without a model and says which it was

An account SHALL be produced deterministically when no model is reachable, and
SHALL state that it ran without one rather than presenting the fallback as a
model's reasoning.

Where a model is used it SHALL be fenced as every other model call here is: it
may use the finding, the declared behaviour and a retrieved passage, and an
account citing nothing retrievable SHALL be dropped in favour of the
deterministic one.

#### Scenario: An account with no gateway says so

- **WHEN** a finding is explained with no model reachable
- **THEN** an account is still produced and it states that no model was
  available
- **AND** `tests/test_rca.py::test_a_cause_is_produced_with_no_model_and_says_so`
  asserts both

### Requirement: Findings left unexplained are counted, never dropped

Where more findings exist than are accounted for, the worst SHALL be explained
first and the remainder SHALL be reported as a count.

A surface that silently explained three of eleven would read as though there
were three.

#### Scenario: The worst is first and the rest are counted

- **WHEN** a product carrying several findings is explained
- **THEN** the most severe is accounted for first and the unexplained remainder
  is reported as a number
- **AND** `tests/test_rca.py::test_the_worst_finding_is_explained_first` and
  `::test_the_findings_it_leaves_out_are_counted_rather_than_dropped` assert both
