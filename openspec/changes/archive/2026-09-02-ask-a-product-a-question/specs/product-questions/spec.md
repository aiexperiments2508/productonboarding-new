## Purpose

Taking a question about a product in words, and answering it only from what is
recorded.

This is the only surface here that accepts an open-ended question, which makes
it the easiest place in the application to say something untrue. Every
requirement below exists to make that hard rather than to make answering easy.

## ADDED Requirements

### Requirement: What to look up is decided deterministically, never by a model

Which surfaces a question reaches SHALL be decided by a closed table of terms,
evaluated deterministically. A model SHALL NOT choose what to retrieve.

A model that can choose what to look up can choose to look up **nothing** and
answer from its own memory, fluently and with no citation. Every other surface
in this application is arranged so that cannot happen.

The table SHALL let a document speaking outweigh the noun it speaks about, and
SHALL keep distinct questions distinct - where a product may be sold is not what
it sold.

Word forms MAY be generated to close gaps, provided a hand-written spelling
always wins. Without that guard, a term weighted low in one intent quietly
acquires a related form belonging to another.

#### Scenario: Each kind of question reaches the surface that answers it

- **WHEN** questions of each kind are routed
- **THEN** each reaches the surface that holds its answer
- **AND** `tests/test_chat.py::test_each_kind_of_question_reaches_the_surface_that_answers_it`
  asserts it

#### Scenario: A document speaking outweighs the noun it speaks about

- **WHEN** a question names both a document and its subject
- **THEN** the document's intent wins
- **AND** `tests/test_chat.py::test_a_document_speaking_outweighs_the_noun_it_speaks_about`
  asserts it

#### Scenario: Generated forms route, and never steal from another intent

- **WHEN** a word the table never spelled out is routed, and when the table is
  expanded
- **THEN** the first still routes and the second takes no word from another
  intent
- **AND** `tests/test_chat.py::test_a_word_the_table_never_spelled_out_still_routes`
  and `::test_expanding_the_table_never_takes_a_word_from_another_intent` assert
  both

#### Scenario: Two similar questions stay apart

- **WHEN** "where it may be sold" and "what it sold" are each routed
- **THEN** they reach different surfaces
- **AND** `tests/test_chat.py::test_where_it_may_be_sold_is_not_what_it_sold`
  asserts it

### Requirement: Evidence is gathered before anything is phrased, and the phrasing step has no tools

Evidence SHALL be gathered before a reply is composed. The step that composes
the reply SHALL be handed facts and SHALL have no retrieval capability of its
own.

This is stronger than instructing a model not to answer from memory: with
nothing to reach for, there is no path by which an unsupported claim can enter
carrying a citation. The failure is not mitigated; it is unavailable.

#### Scenario: An unknown product yields no evidence at all

- **WHEN** a question names a product the system does not hold
- **THEN** no evidence is gathered
- **AND** `tests/test_chat.py::test_an_unknown_product_produces_no_evidence_at_all`
  asserts it

### Requirement: The evidence walk does not stray into sibling variants

Evidence about a variant SHALL be reached without a detour through its product
into the product's other variants. What genuinely belongs to the product SHALL
be reached by a single hop from the product itself.

This is a correctness constraint rather than a performance one. A walk that
widens through the product also walks back down into sibling variants, and their
stock and certificates then arrive labelled as this variant's - measured on one
product, three stock records became a hundred and eighty-one and one certificate
became nineteen. The reply was fluent, cited its sources, and was wrong by
sixtyfold, which is the worst available failure because every signal a reader
uses to judge an answer said it was sound.

The constraint SHALL be asserted against the graph's own adjacency rather than
against a count written down by hand, so it keeps holding when the projection
changes.

#### Scenario: Stock counts only this variant's stock

- **WHEN** a question about stock is answered for a variant with siblings
- **THEN** only that variant's stock is counted
- **AND** `tests/test_chat.py::test_an_answer_about_stock_counts_only_this_variants_stock`
  asserts it

#### Scenario: Certificates match what the graph actually holds

- **WHEN** certificates are named in an answer
- **THEN** they match the record, checked against the graph's own adjacency
- **AND** `tests/test_chat.py::test_certificates_named_in_the_graph_match_the_record`
  asserts it

### Requirement: An answer with no evidence is a refusal that does not look like prose

Where no evidence was found, the answer SHALL be a refusal naming what could be
asked instead, and SHALL be rendered in a treatment distinct from an answer.

A confident sentence and an admission of ignorance must not look the same. If
they do, a reader skimming takes the second for the first, which is the outcome
this whole design is arranged to prevent.

A question that needs a product and has none SHALL say so. A question about
something else entirely SHALL NOT be answered.

#### Scenario: A refusal names what could be asked instead

- **WHEN** a question finds no evidence
- **THEN** the refusal names what could be asked
- **AND** `tests/test_chat.py::test_a_refusal_says_what_could_be_asked_instead`
  asserts it

#### Scenario: A missing product and an unrelated question are each declined

- **WHEN** a question needing a product arrives without one, and when a question
  about something else entirely arrives
- **THEN** the first says so and the second is not answered
- **AND** `tests/test_chat.py::test_a_question_needing_a_product_says_so_when_there_is_none`
  and `::test_a_question_about_something_else_entirely_is_not_answered` assert
  both

### Requirement: The composed answer states each thing once and mangles nothing

A repeated finding SHALL be stated once. The reply SHALL NOT restate its own
headline. An attribute path SHALL be rendered as written rather than
capitalised into something else.

A spoken rendering SHALL drop the attribution the screen keeps, which a reader
can see and a listener cannot use.

#### Scenario: Nothing is said twice and nothing is renamed

- **WHEN** a reply covering a repeated finding is composed
- **THEN** the finding appears once, the headline is not restated, and attribute
  paths are unchanged
- **AND** `tests/test_chat.py::test_the_template_states_a_repeated_finding_once`,
  `::test_the_template_does_not_restate_its_own_headline` and
  `::test_an_attribute_path_is_not_capitalised_into_something_else` assert each

#### Scenario: The spoken answer differs from the written one

- **WHEN** an answer is rendered for speech
- **THEN** the attribution the screen carries is dropped
- **AND** `tests/test_chat.py::test_the_spoken_answer_drops_the_attribution_the_screen_keeps`
  asserts it

### Requirement: The route carries evidence, refuses what it cannot take, and holds no logic

The route SHALL answer carrying the evidence behind the answer, SHALL refuse an
empty question, SHALL name what it can answer, and SHALL truncate a question
longer than any real question.

The route SHALL hold no business logic of its own.

#### Scenario: The route answers with evidence and refuses what it should

- **WHEN** a question, an empty question, and an over-long question are each
  submitted
- **THEN** the first is answered with its evidence, the second refused, and the
  third truncated
- **AND** `tests/test_chat.py::test_the_route_answers_and_carries_its_evidence`,
  `::test_the_route_refuses_an_empty_question`,
  `::test_the_route_names_what_it_can_answer` and
  `::test_a_question_longer_than_any_real_question_is_truncated` assert each

#### Scenario: The route delegates

- **WHEN** the route body is examined
- **THEN** it holds no business logic
- **AND** `tests/test_chat.py::test_the_chat_routes_hold_no_business_logic`
  asserts it
