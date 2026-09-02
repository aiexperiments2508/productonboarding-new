## ADDED Requirements

### Requirement: An assessment may run rules alone, and one that did says so

An assessment SHALL be able to run the deterministic rule checks alone, without
invoking a model, and this SHALL be the default for opening a product. The
checks that read prose SHALL run when a reviewer asks for them.

A rule-only assessment SHALL always report itself as narrow. It SHALL NOT use
the vocabulary reserved for a complete assessment: the word that means a
product is fit to launch is reserved for an assessment that ran every check,
and a narrow one SHALL say only that no rule found anything.

This is the whole cost of defaulting to the fast path. A narrow assessment
produces the same *shape* of answer as a complete one, so unless the vocabulary
differs the difference is invisible at the point somebody reads it - and the
reader is deciding whether to put a product on sale.

A pre-publication preview SHALL refuse to build from a narrow verdict, because
the purpose of a preview is to show what would actually go live.

Every surface that renders a verdict SHALL derive the wording from one shared
helper rather than phrasing it independently. A rule enforced in whichever
surfaces somebody remembered is not enforced.

#### Scenario: Rule checks alone always report themselves as narrow

- **WHEN** a product is assessed with the rule checks only
- **THEN** the assessment reports itself as narrow
- **AND** `tests/test_readiness.py::test_the_rule_checks_alone_always_report_themselves_as_narrow`
  asserts it

#### Scenario: A narrow assessment with nothing found still says it was narrow

- **WHEN** a rule-only assessment finds nothing
- **THEN** it reports that no rule found anything rather than that the product
  is fit to launch
- **AND** `tests/test_readiness.py::test_a_narrow_assessment_can_still_be_ready_which_is_why_it_must_say_so`
  asserts it

#### Scenario: A narrow assessment's findings keep their full weight

- **WHEN** the same finding is raised by a narrow assessment and by a complete
  one
- **THEN** it carries the same severity and the same consequence in both
- **AND** `tests/test_readiness.py::test_findings_are_not_weakened_by_the_assessment_being_narrow`
  asserts it

Fewer checks ran, so there is *less* evidence - not worse evidence. Discounting
a rule finding because the reading checks were skipped would make the fast path
quietly less useful than the slow one rather than merely narrower.
