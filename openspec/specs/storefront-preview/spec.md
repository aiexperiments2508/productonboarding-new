# storefront-preview Specification

## Purpose

What the listing would look like, shown to an authorised reviewer before it
exists anywhere a shopper can reach - and the one genuinely generative surface
in this system, fenced accordingly.

## Requirements

### Requirement: Only a record that passed is previewable

A preview SHALL be produced only for a record whose verdict is ready to launch.
A record that was returned to its source or blocked SHALL be refused with the
verdict and the findings, rather than rendered with a warning.

A page that renders a blocked product is a page somebody screenshots.

Access SHALL require the same authorisation the approval gate requires. A
preview is a view of unpublished commercial content and the reviewer boundary
already exists; inventing a second, weaker one beside it would be the only
interesting thing about it.

#### Scenario: A blocked record is refused, not rendered

- **WHEN** a preview is requested for a record carrying a blocking finding
- **THEN** the request is refused and the response names the verdict and the
  findings
- **AND** `tests/test_preview.py::test_a_blocked_record_is_refused_not_rendered`
  asserts both

#### Scenario: A ready record renders its salient information

- **WHEN** a preview is requested for a ready record
- **THEN** the page carries the product name, the salient specification values,
  the media in their roles, and the claims the record substantiates
- **AND** `tests/test_preview.py::test_a_ready_record_renders_its_salient_information`
  asserts each

### Requirement: The preview asserts nothing the record does not hold

Every value shown SHALL come from the record in force. The preview SHALL NOT
compute, round, reword or infer a specification value, and SHALL NOT show a
claim the substantiation table does not support.

A preview is the last surface before publication and the first one a reviewer
trusts. A figure that appears here and nowhere in the record is a figure nobody
can trace.

#### Scenario: Every figure on the page is in the record

- **WHEN** a preview is rendered and its specification values are compared with
  the record
- **THEN** every value shown appears in the record, unchanged
- **AND** `tests/test_preview.py::test_every_figure_on_the_page_is_in_the_record`
  asserts the equality

#### Scenario: An unsubstantiated claim does not reach the page

- **WHEN** a record carries prepared copy making a claim the substantiation
  table does not support
- **THEN** the claim does not appear on the preview
- **AND** `tests/test_preview.py::test_an_unsubstantiated_claim_does_not_reach_the_page`
  asserts the absence

### Requirement: The differentiator is grounded twice, or it is not shown

The value differentiator SHALL rest on two things at once: an attribute the
record holds, and a passage the corpus carries. Season, region, festivity and
popular usage are authored documents; a differentiator SHALL cite the passage it
used and name the attributes it leaned on.

A differentiator that can cite only one of the two SHALL NOT be shown. Saying a
product is comfortable in summer requires both a summer and a reason, and either
alone is a sentence somebody made up.

It SHALL NOT introduce a comparative or superlative claim, a health or medical
claim, or any statement the prohibited-content documentation forbids - whatever
the model returns. These are checked against the record after the model answers
rather than requested politely in the prompt.

Where no model is reachable, a differentiator SHALL still be produced from the
same two inputs by template, so the surface degrades rather than disappearing.

#### Scenario: A differentiator names its attributes and cites its passage

- **WHEN** a differentiator is produced for a ready record
- **THEN** it names at least one attribute the record holds and cites at least
  one retrievable passage
- **AND** `tests/test_preview.py::test_a_differentiator_names_attributes_and_cites_a_passage`
  asserts both

#### Scenario: An ungrounded differentiator is withheld

- **WHEN** a differentiator cites no passage, or leans on no attribute the
  record holds
- **THEN** it is not shown
- **AND** `tests/test_preview.py::test_an_ungrounded_differentiator_is_withheld`
  asserts the absence

#### Scenario: A forbidden claim is stripped whatever the model returned

- **WHEN** a proposed differentiator contains a medical, absolute-safety or
  guaranteed-outcome claim
- **THEN** it is rejected and the deterministic form is used instead
- **AND** `tests/test_preview.py::test_a_forbidden_claim_is_rejected`
  asserts the rejection

#### Scenario: The differentiator survives having no model

- **WHEN** a differentiator is produced with no model reachable
- **THEN** one is still produced, from the same attributes and the same passage,
  and it says it was written without a model
- **AND** `tests/test_preview.py::test_the_differentiator_survives_having_no_model`
  asserts each
