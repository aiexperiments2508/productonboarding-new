## 1. The route contract

- [x] 1.1 Replace the supplier and bill-of-materials routes with the variant
      table and the derivation read, and delete the sampling route with the
      sampling layer; verified by inspection of `sc/main.py`
- [x] 1.2 Fix the two routes that had never run - the health read against a
      catalog that no longer had a network or an order book, and the publish
      route passing a keyword that had been renamed; verified by inspection
- [x] 1.3 Take change sets on the validate and compare routes, refusing a
      request that carries none; verified by inspection
- [x] 1.4 Serve every catalog read from the function the pipeline calls, so the
      console and the pipeline cannot drift; verified by inspection, with the
      functions themselves covered by `tests/test_propagation.py`
- [x] 1.5 Return the catalog tool's own cell on the variant table - value,
      version, document, provenance and confidence - rather than flattening it
      to a bare value; the cell contents are asserted by
      `tests/test_propagation.py::test_variant_diff_shows_the_document_each_value_stands_on`
- [x] 1.6 Add the open-cases route and accept a case on both run routes; the
      grouping it serves is asserted by
      `tests/test_graph.py::test_cases_are_ordered_worst_first_and_deterministically`
- [x] 1.7 Sum the per-stage model spend on the run-state route rather than
      storing a total; the per-stage records are asserted by
      `tests/test_graph.py::test_spend_is_keyed_by_node_so_one_writer_does_not_erase_another`
- [x] 1.8 Stream a run and a revision stage by stage on a worker thread, pushing
      a failure onto the stream rather than dropping the connection; verified by
      inspection
- [x] 1.9 Read the topology out of the compiled pipeline; the topology it reads
      is asserted by `tests/test_branches.py::test_the_graph_actually_branches`
- [x] 1.10 Accept only approve, reject and modify as decisions, and deliver them
      into the suspended run rather than acting beside it; the recording is
      asserted by `tests/test_graph.py::test_a_decision_is_recorded_with_decided_provenance`
- [x] 1.11 Confirm the pending list against each run's checkpoint rather than a
      status column alone; verified by inspection
- [x] 1.12 Refuse a revision on a thread with nothing to revise, as a conflict;
      verified by inspection of the refusal it translates
- [x] 1.13 Drive the replay clock through one command, ingesting and
      broadcasting what it releases before returning; the ingestion is asserted
      by `tests/test_ingest.py`
- [x] 1.14 Default both fact axes to the replay clock, and expose one value's
      correction chain; the bitemporal behaviour is asserted by
      `tests/test_bitemporal.py`
- [x] 1.15 Serve the evidence allowlist, the toolset partition and the peer
      roster from the structures that enforce them; those structures are
      asserted by `tests/test_replan.py` and `tests/test_protocols.py`
- [x] 1.16 Mount the peers at import behind a guard, so a mount failure costs the
      roster and not the application; verified by inspection
- [x] 1.17 Mount the console last so its catch-all cannot shadow an API route,
      and start without one; verified by inspection

## 2. The model gateway

- [x] 2.1 Classify tiers on whole tokens rather than substrings; verify via
      `tests/test_models.py::test_tier_classification` and
      `test_gemini_is_not_mistaken_for_a_mini_model`
- [x] 2.2 Read the model list from the gateway, reporting whether the answer is
      live or the fallback; verify via `test_listing_groups_by_tier`
- [x] 2.3 Parse the fallback list from the shipped gateway configuration rather
      than duplicating it; verify via `test_fallback_is_parsed_from_the_shipped_config`
- [x] 2.4 Degrade an empty reasoning tier to the strongest fast model; verify via
      `test_reasoning_degrades_to_the_strongest_fast_model`
- [x] 2.5 Stop asserting that a reasoning tier exists - a claim about one
      deployment - and assert the documented degradation instead; verify by the
      absence of that assertion in `test_listing_groups_by_tier`
- [x] 2.6 Allow a per-deployment tier pin and validate it against the gateway's
      own list, warning rather than returning a retired alias; verify via
      `test_a_tier_can_be_pinned_per_deployment` and
      `test_a_pin_the_gateway_does_not_serve_is_refused`
- [x] 2.7 Hot-load and persist a selection together; verify via
      `test_selection_is_hot_loaded_and_persisted`,
      `test_cache_toggle_round_trips` and
      `test_embed_model_selection_is_honoured_at_runtime`
- [x] 2.8 Preserve comments, ordering and unrelated keys on write-back, and write
      nothing when nothing changed; verify via
      `test_write_back_preserves_comments_and_other_keys` and
      `test_no_change_writes_nothing`
- [x] 2.9 Never create a credential into a file that does not carry one; verify
      via `test_write_back_never_invents_a_credential`
- [x] 2.10 Refuse a model the gateway does not serve, and an embedding model
      asked to do chat, before either reaches a run; verify via
      `test_unknown_model_is_rejected_before_it_reaches_a_run` and
      `test_embedding_model_cannot_be_selected_for_chat`
- [x] 2.11 Suppress repeated connection attempts to an unreachable gateway for a
      cooldown, so the fallback paths run at speed; exercised by the whole graph
      suite running against a closed port
- [x] 2.12 Refuse a reply that is not a JSON object as a gateway failure, so the
      caller reaches its own fallback; verified by inspection of the parse guard

## 3. Entry and launcher

- [x] 3.1 Move configuration loading into the bootstrap so every door reads it,
      using set-if-absent so a real environment variable still wins; verified by
      inspection
- [x] 3.2 Attach to an already-running gateway by default when one is named,
      rather than starting a second proxy and ignoring it; verified by inspection
- [x] 3.3 Add the missing import shim to the index builder so it runs directly;
      verified by inspection
- [x] 3.4 Drop `python-dotenv`, which nothing imported; verified by inspection of
      the requirements
- [x] 3.5 Key the launcher's seed-data check on the file the generator actually
      writes, rather than one it deletes; verified by inspection
- [x] 3.6 Refuse to start when the API port is held, naming the process that
      holds it; verified by inspection

## 4. The console

- [x] 4.1 Give the client a vocabulary for corrections - the value difference,
      the source citation, the provenance badge - and separate a pulse from
      membership of a blast radius
- [x] 4.2 Build the blast-radius view and the factory floor, and drop the
      scatter and the weight sliders that presented two readings of one document
      as an efficient frontier
- [x] 4.3 Render the reviewer's decision as source, old value, new value and
      impacted outputs, from lines the backend assembles rather than from parsed
      prose
- [x] 4.4 Land a finished run on the blast radius and offer the pending decision
      as an action rather than a redirect
- [x] 4.5 Give the live node stream the middle of the screen while a run is in
      flight, rather than twelve pixels in the footer
- [x] 4.6 Send the tape-jump parameter that was typed through the client, the
      shell and the panel and never sent
- [x] 4.7 Stop the navigation describing a frontier the view itself argues
      against having
- [x] 4.8 Rebuild the committed bundle so the served console matches the source

## 5. Verification and what is still open

- [x] 5.1 Confirm the model suite passes with no gateway reachable, against the
      example configuration file
- [ ] 5.2 Add route-level tests. Nothing in the suite exercises an HTTP route,
      and the two defects this change fixed - a health read against a catalog
      shape that no longer existed, and a publish call passing a renamed keyword
      - are precisely the class a route-level test catches and inspection does
      not
- [ ] 5.3 Correct the README's claim that a model is invited to exactly four
      points. There are seven call sites - extraction, triage, scope resolution,
      claim scanning, regeneration, enrichment and the narrative - and the
      accurate statement is the one the architecture actually rests on: none of
      them may originate a number, a verdict or a publish decision, and every one
      has a deterministic fallback
- [ ] 5.4 Cover the console. There is not one frontend test in the repository, so
      every claim in section 4 is verified by using the application and by
      nothing else
