## Purpose

A second reading of the same catalog, as a graph over seven domains - so that
"what is this product connected to" is one bounded question rather than a new
join per asking.

Two constraints shape everything below. **A real graph database is optional**,
which is why there are two backends that must agree. And **four of the seven
domains have no source data**, which is why invented data arrives on a lane that
cannot reach a verdict.

## ADDED Requirements

### Requirement: Two backends walk one projection, and the response says which answered

The graph SHALL be served by a real graph database where one answers, and by an
identical projection walked in process where one does not. Both SHALL return the
same node sets and the same rows for every saved query.

Every response SHALL name the engine that answered it. A graph that silently
fell back would make a difference in engines look like a difference in the data.

The database driver SHALL be imported inside a function rather than at module
load, so an installation without it still imports, starts and serves every
route.

Two implementations of one projection is exactly the shape that drifts. The only
defence is that both are exercised, which is why the equality is a test rather
than a claim.

#### Scenario: Both backends hold the same graph and answer the same

- **WHEN** the same graph and the same saved queries are read from each backend
- **THEN** the node sets and the rows are identical
- **AND** `tests/test_kg_neo4j.py::test_both_backends_return_the_same_graph` and
  `::test_both_backends_answer_the_saved_queries_the_same` assert both

#### Scenario: The response names its engine

- **WHEN** any graph read is answered
- **THEN** it says which backend answered
- **AND** `tests/test_kg_api.py::test_the_response_says_which_backend_answered`
  and `::test_status_reports_the_backend_and_what_it_holds` assert both

#### Scenario: The schema applies, re-applies, and merges idempotently

- **WHEN** the schema and the load are applied twice
- **THEN** neither errors and the second changes nothing
- **AND** `tests/test_kg_neo4j.py::test_the_schema_applies_and_re_applies`,
  `::test_merge_is_idempotent`,
  `::test_every_label_and_relationship_survived_the_load` and
  `tests/test_kg_schema.py::test_the_schema_is_idempotent_statement_by_statement`
  assert each

### Requirement: There is no free-text query, and every value is a parameter

Every statement SHALL be parameterised. No caller-supplied value SHALL be
written into a statement.

Three values cannot be parameters and each SHALL be constrained instead:

- **depth**, which the query language will not bind, SHALL come from a closed
  set of literal patterns, and a depth outside it SHALL be refused;
- **a domain filter** SHALL be an enum, and one carrying query syntax SHALL be
  refused;
- **a saved query** SHALL be checked against an allowlist by name, so an unknown
  one never reaches a builder.

An out-of-range parameter SHALL be refused rather than clamped. Clamping answers
a question the caller did not ask and reports it as the answer to the one they
did.

The row cap SHALL be the same in both implementations. A cap that differed would
make the backends disagree about a large result, and the disagreement would read
as a difference in the data.

#### Scenario: Every placeholder is bound and no caller value is inlined

- **WHEN** the statements the builders produce are examined
- **THEN** every placeholder is bound, every parameter is used, and no caller
  value appears in a statement - including a hostile identifier
- **AND** `tests/test_kg_cypher.py::test_every_placeholder_is_bound_and_every_parameter_is_used`,
  `::test_no_caller_value_is_written_into_a_statement` and
  `::test_a_hostile_node_id_stays_a_parameter` assert each

#### Scenario: Depth, domain and query name are each constrained

- **WHEN** a depth outside the set, a domain filter carrying query syntax, or an
  unknown saved query is submitted
- **THEN** each is refused before reaching a builder or the database
- **AND** `tests/test_kg_cypher.py::test_a_depth_outside_the_closed_set_is_refused`,
  `::test_a_domain_filter_carrying_cypher_is_refused`,
  `::test_an_unknown_insight_never_reaches_a_builder` and
  `tests/test_kg_neo4j.py::test_a_depth_the_builder_refuses_never_reaches_neo4j`
  assert each

#### Scenario: An out-of-range parameter is refused, not clamped

- **WHEN** a parameter outside its range is submitted
- **THEN** it is refused
- **AND** `tests/test_kg_cypher.py::test_an_out_of_range_parameter_is_refused_not_clamped`
  asserts it

#### Scenario: Both implementations cap alike

- **WHEN** the row caps of the two implementations are compared
- **THEN** they are the same
- **AND** `tests/test_kg_cypher.py::test_the_row_cap_is_the_same_in_both_implementations`
  asserts it

### Requirement: The schema is asserted rather than documented

Every label SHALL belong to a domain and every domain SHALL have at least one
label. Every label SHALL have a business key with a constraint behind it. Every
relationship SHALL declare both of its ends, and an edge SHALL take the domain
of what it reaches. No range index SHALL repeat a constraint. The search index
SHALL be named identically in both places and SHALL cover exactly the searchable
labels, each findable by its own key. The depth bound SHALL be small and stated.

These are the properties that make the projection re-runnable, which is what
makes "both backends hold the same graph" checkable at all.

#### Scenario: The model is internally consistent

- **WHEN** the schema is examined
- **THEN** domains, keys, constraints, relationship ends, indexes and the depth
  bound all hold
- **AND** `tests/test_kg_schema.py::test_every_label_belongs_to_a_domain`,
  `::test_every_domain_has_at_least_one_label`,
  `::test_every_label_has_a_business_key`,
  `::test_every_key_the_model_names_has_a_constraint_behind_it`,
  `::test_the_alternate_key_is_constrained_and_products_have_none`,
  `::test_every_relationship_declares_both_of_its_ends`,
  `::test_an_edge_takes_the_domain_of_what_it_reaches`,
  `::test_no_range_index_repeats_a_constraint`,
  `::test_the_search_index_is_named_the_same_in_both_places`,
  `::test_the_search_index_covers_exactly_the_searchable_labels`,
  `::test_every_searchable_label_can_be_found_by_its_own_key` and
  `::test_the_depth_bound_is_small_and_stated` assert each

### Requirement: Invented data is stamped, and derived data is derived

Where a domain has no source data, its nodes SHALL be marked synthetic, and
**only** those domains SHALL be so marked. Where the catalog already holds the
information, the graph SHALL derive it rather than invent it.

A reader has to be able to see at a glance which half of the picture is evidence
and which is illustration, and a stamp that spread to derived data would destroy
that distinction quietly.

#### Scenario: Only the invented domains are synthetic

- **WHEN** the projection's nodes are examined
- **THEN** exactly the domains with no source data carry the synthetic mark
- **AND** `tests/test_kg_insights.py::test_only_the_invented_domains_are_marked_synthetic`
  and `tests/test_kg_schema.py::test_the_synthetic_labels_are_the_ones_with_no_source_data`
  assert both

#### Scenario: What the catalog knows is read from the catalog

- **WHEN** certificate schemes and media coverage are projected
- **THEN** they are derived from the references and imagery the catalog already
  holds
- **AND** `tests/test_kg_data.py::test_the_scheme_is_read_off_the_catalogs_own_reference`,
  `::test_the_best_sellers_without_media_are_real_gaps` and
  `tests/test_kg_insights.py::test_weakest_media_coverage_is_derived_from_real_imagery`
  assert each

### Requirement: The graph answers a bounded neighbourhood and a fixed set of insights

A neighbourhood SHALL grow with depth and stop at a node cap. A domain filter
SHALL remove that domain and its edges. Expanding a node SHALL skip what the
caller already holds. A path between two products SHALL be returned said in
words. A product SHALL be findable by every name it has.

The graph SHALL cover all seven domains, and SHALL still hold the catalog when
no reference pack is present. Every edge SHALL join two labels the model admits.

Every saved insight SHALL answer within its cap and SHALL return the columns its
specification declares.

#### Scenario: The neighbourhood is bounded and filterable

- **WHEN** a neighbourhood is requested at increasing depth, with a domain
  filter, and while expanding
- **THEN** it grows and stops at the cap, loses the filtered domain and its
  edges, and omits what the caller already has
- **AND** `tests/test_kg_insights.py::test_a_neighbourhood_grows_with_depth_and_stops_at_the_cap`,
  `::test_a_domain_filter_removes_a_domain_and_its_edges`,
  `::test_expanding_a_node_skips_what_is_already_on_screen` and
  `tests/test_kg_api.py::test_depth_and_the_node_cap_both_bound_the_answer`
  assert each

#### Scenario: The projection is complete and admissible

- **WHEN** the projection is built, with and without a reference pack
- **THEN** it covers seven domains, still holds the catalog without the pack,
  and every edge joins admitted labels
- **AND** `tests/test_kg_insights.py::test_the_projection_covers_all_seven_domains`,
  `::test_a_graph_with_no_reference_pack_still_has_the_catalog` and
  `::test_every_edge_joins_two_labels_the_model_admits` assert each

#### Scenario: Every insight answers within its cap and its declared columns

- **WHEN** each saved insight is run
- **THEN** it answers within its cap and returns its declared columns
- **AND** `tests/test_kg_insights.py::test_every_insight_answers_and_answers_within_its_cap`,
  `tests/test_kg_cypher.py::test_every_saved_query_returns_the_columns_its_spec_declares`
  and `tests/test_kg_api.py::test_every_saved_query_runs_and_returns_its_declared_columns`
  assert each

### Requirement: The graph routes delegate, refuse and read the replay clock

The graph routes SHALL hold no query language of their own. An unknown key SHALL
be refused rather than answered with an empty graph, and a bad depth or a domain
filter carrying query syntax SHALL be refused. Only the saved queries SHALL run.
Reads SHALL be as of the replay clock rather than the wall clock.

An empty graph for an unknown product reads as a product with no connections,
which is a state a real product can be in.

#### Scenario: The routes hold no query language

- **WHEN** the route bodies are examined
- **THEN** none contains a query statement
- **AND** `tests/test_kg_api.py::test_the_graph_routes_delegate_and_hold_no_cypher`
  asserts it

#### Scenario: An unknown key is refused, not answered empty

- **WHEN** an unknown product key is requested
- **THEN** it is refused
- **AND** `tests/test_kg_api.py::test_an_unknown_key_is_a_404_and_not_an_empty_graph`
  asserts it

#### Scenario: Only the saved queries run, and the clock is the replay clock

- **WHEN** a query outside the allowlist is requested, and when any read is made
- **THEN** the first is refused and the second is as of the replay clock
- **AND** `tests/test_kg_api.py::test_the_saved_queries_are_the_only_ones_that_run`
  and `::test_the_as_of_is_the_replay_clock_and_not_the_wall_clock` assert both
