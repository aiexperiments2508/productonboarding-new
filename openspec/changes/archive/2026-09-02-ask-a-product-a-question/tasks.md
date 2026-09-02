## 1. Deterministic routing

- [x] 1.1 Pick the surfaces a question reaches from a closed keyword table, so
      no model chooses what to look up; verify via
      `tests/test_chat.py::test_each_kind_of_question_reaches_the_surface_that_answers_it`
- [x] 1.2 Let a document speaking outweigh the noun it speaks about; verify via
      `tests/test_chat.py::test_a_document_speaking_outweighs_the_noun_it_speaks_about`
- [x] 1.3 Generate inflections so a word the table never spelled out still
      routes; verify via
      `tests/test_chat.py::test_a_word_the_table_never_spelled_out_still_routes`
- [x] 1.4 Let a hand-written spelling always beat a generated one, so expanding
      the table cannot take a word from another intent; verify via
      `tests/test_chat.py::test_expanding_the_table_never_takes_a_word_from_another_intent`
- [x] 1.5 Close the three routing gaps found by asking the surface rather than
      by reading the table, keeping "where it may be sold" apart from "what it
      sold"; verify via
      `tests/test_chat.py::test_where_it_may_be_sold_is_not_what_it_sold`

## 2. Evidence before phrasing

- [x] 2.1 Gather evidence first and hand the reply step facts, giving it no
      retrieval tool, so answering from memory is unavailable rather than
      discouraged
- [x] 2.2 Walk two hops from the variant with no detour through the product, so
      a sibling's stock and certificates cannot arrive labelled as this one's;
      verify via
      `tests/test_chat.py::test_an_answer_about_stock_counts_only_this_variants_stock`
- [x] 2.3 Reach what hangs off the product by one hop from the product node, and
      assert it against the graph's own adjacency rather than a hand-written
      count; verify via
      `tests/test_chat.py::test_certificates_named_in_the_graph_match_the_record`
- [x] 2.4 Produce no evidence at all for an unknown product; verify via
      `tests/test_chat.py::test_an_unknown_product_produces_no_evidence_at_all`

## 3. What the answer may say

- [x] 3.1 Refuse where there is no evidence, naming what could be asked instead;
      verify via `tests/test_chat.py::test_a_refusal_says_what_could_be_asked_instead`
- [x] 3.2 Render a refusal in a different treatment from prose, so an admission
      of ignorance cannot be skimmed as a confident sentence
- [x] 3.3 Say a repeated finding once and not restate the headline; verify via
      `tests/test_chat.py::test_the_template_states_a_repeated_finding_once` and
      `::test_the_template_does_not_restate_its_own_headline`
- [x] 3.4 Leave an attribute path alone rather than capitalising it into
      something else; verify via
      `tests/test_chat.py::test_an_attribute_path_is_not_capitalised_into_something_else`
- [x] 3.5 Say when a question needs a product and none was given, and answer
      nothing that is about something else entirely; verify via
      `tests/test_chat.py::test_a_question_needing_a_product_says_so_when_there_is_none`
      and `::test_a_question_about_something_else_entirely_is_not_answered`

## 4. The route

- [x] 4.1 Answer carrying the evidence, and refuse an empty question; verify via
      `tests/test_chat.py::test_the_route_answers_and_carries_its_evidence` and
      `::test_the_route_refuses_an_empty_question`
- [x] 4.2 Name what it can answer; verify via
      `tests/test_chat.py::test_the_route_names_what_it_can_answer`
- [x] 4.3 Truncate a question longer than any real question; verify via
      `tests/test_chat.py::test_a_question_longer_than_any_real_question_is_truncated`
- [x] 4.4 Hold no business logic in the route itself; verify via
      `tests/test_chat.py::test_the_chat_routes_hold_no_business_logic`

## 5. Speaking the answer

- [x] 5.1 Use the browser's own speech synthesis, uploading nothing, and work
      with the speakers muted
- [x] 5.2 Drop the attribution the screen keeps from the spoken answer; verify
      via `tests/test_chat.py::test_the_spoken_answer_drops_the_attribution_the_screen_keeps`
- [x] 5.3 Read the voice list asynchronously rather than once at load, and
      resume on a timer, since one browser stops speaking after about fifteen
      seconds

## 6. The panel, and one fix found on the way

- [x] 6.1 Put the panel above the five sections and link down into whichever one
      the answer concerned
- [x] 6.2 Key the back office campaign filter on the objective, which only a
      campaign has, since a promotion carries a campaign identifier too and was
      throwing on render
