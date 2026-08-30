## 1. No model named in application code

- [x] 1.1 Remove the two alias lists from the gateway client and have
      `available_models` ask the registry, which parses the shipped
      configuration rather than duplicating it; verify via
      `tests/test_models.py::test_available_models_answers_from_the_registry_not_a_list`
- [x] 1.2 Remove the embedding default, resolving the tier instead; verify the
      index still builds and `tests/test_rag.py` passes unchanged
- [x] 1.3 Replace the last-resort alias with an explicit refusal, so a caller is
      never handed a name the gateway would reject; verify via
      `tests/test_models.py::test_no_model_available_is_said_rather_than_invented`
- [x] 1.4 Guard the fix with a grep over the application, ignoring comments and
      requiring a version or a named tier so it cannot fire on the dict key
      "command"; verify via
      `tests/test_models.py::test_no_model_is_named_in_application_code`

## 2. The directory

- [x] 2.1 Serve one document at `/.well-known/agent-cards.json`, built from the
      cards actually served; verify via
      `tests/test_directory.py::test_the_directory_and_the_cards_agree`
- [x] 2.2 Omit a capability that failed to publish rather than advertising it;
      verify via
      `tests/test_directory.py::test_an_unpublished_capability_is_not_advertised`
- [x] 2.3 Keep peers and connected systems distinguishable, each naming its
      protocol and a system naming its state; verify via
      `tests/test_directory.py::test_a_peer_and_a_system_are_distinguishable`
- [x] 2.4 Derive the counts from the entries so the summary cannot disagree with
      the list under it; verify via
      `tests/test_directory.py::test_the_counts_agree_with_the_entries`
- [x] 2.5 State what each peer may not do rather than leaving it to be inferred
      from absence; verify via
      `tests/test_directory.py::test_every_peer_entry_names_its_limits`

## 3. Discovery is not admission

- [x] 3.1 Add `admitted_tools` to the evidence desk, reading only connections
      that are answering; verify via
      `tests/test_directory.py::test_a_degraded_systems_tool_leaves_the_desk`
- [x] 3.2 Leave the catalogue unchanged when a system connects; verify via
      `tests/test_directory.py::test_connecting_a_system_does_not_widen_the_desk`
- [x] 3.3 Add an admitted tool named with its system, so a model can tell a
      catalog lookup from a supplier's own answer; verify via
      `tests/test_directory.py::test_an_admitted_tool_joins_the_desk_named_with_its_system`
- [x] 3.4 Make the desk survive an estate it cannot read, so no external system
      is load-bearing for a run; verify via
      `tests/test_directory.py::test_the_desk_survives_an_estate_it_cannot_read`

## 4. The board

- [x] 4.1 Show the directory in System Control, peers and systems apart, with
      the well-known address named; verify by opening System Control
- [x] 4.2 Show declared tools beside admitted tools, so a system that has
      declared ten and had none admitted reads as such; verify by connecting a
      system and looking

## 5. Outstanding

- [ ] 5.1 Record an admission in the audit ledger. NOT DONE. Admitting a tool
      changes what a model can reach and is currently a state change with no
      entry beside the approvals and publishes it belongs with. The ledger's
      schema is shaped around a correction case and an admission is not one,
      which is the reason and not an excuse.
- [ ] 5.2 Let a peer declare its own limits rather than having them authored in
      the directory. NOT DONE: an agent whose handler quietly gained the
      ability to publish would still advertise that it cannot.
