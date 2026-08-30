## 1. The publication estate

- [x] 1.1 Derive one publication system per channel, with its own endpoint and
      the three verbs it accepts, rather than configuring a list beside the
      channels; verify via
      `tests/test_publication.py::test_publication_systems_are_derived_from_the_channels`
- [x] 1.2 Take recallability from the freeze window rather than storing it
      twice, so the two cannot disagree; verify via
      `tests/test_publication.py::test_a_channel_that_cannot_be_recalled_says_so`

## 2. The blast radius, in the vocabulary people act in

- [x] 2.1 Resolve a trace to affected SKUs, each carrying the listings and
      channels it is live on; verify via
      `tests/test_publication.py::test_the_blast_radius_answers_in_skus`
- [x] 2.2 Confirm the sibling case survives the translation - a correction
      scoped to one variant still names the other, which is the finding the
      whole propagation design exists to produce; verify via
      `tests/test_publication.py::test_a_correction_to_one_variant_names_the_siblings_it_reaches`
- [x] 2.3 Group the reached listings by the system that owns them, carrying the
      SKUs affected on each; verify via
      `tests/test_publication.py::test_the_systems_to_tell_are_grouped_with_their_skus`
- [x] 2.4 Order everything so two reads of one trace agree; verify via
      `tests/test_publication.py::test_grouping_is_stable_across_reads`

## 3. Dispatch

- [x] 3.1 Produce a dispatch plan that writes nothing; verify via
      `tests/test_publication.py::test_planning_a_dispatch_sends_nothing`
- [x] 3.2 Defer a channel whose artefact cannot be recalled rather than
      attempting it; verify via
      `tests/test_publication.py::test_a_frozen_channel_is_deferred_rather_than_attempted`
- [x] 3.3 Report per system, with counts derived from the rows; verify via
      `tests/test_publication.py::test_the_dispatch_report_counts_agree_with_its_rows`
- [x] 3.4 Leave the three refusals where they are and let a refusal apply to
      every system, carrying the boundary's own reason; verify via
      `tests/test_publication.py::test_a_dispatch_without_an_approval_refuses_every_system`
      and
      `tests/test_publication.py::test_a_refused_dispatch_reports_one_reason_not_six`
- [x] 3.5 Never report a channel that was never sent to as reverted; verify via
      `tests/test_publication.py::test_a_channel_never_sent_to_is_not_reported_as_reverted`

## 4. The surface

- [x] 4.1 Add the routes - the systems, the impact in SKUs, and dispatch and
      revert; verify via
      `tests/test_publication.py::test_the_impact_route_answers_in_skus_and_systems`
- [x] 4.2 Refuse a dispatch missing its identifiers rather than guessing; verify
      via
      `tests/test_publication.py::test_a_dispatch_route_without_its_identifiers_refuses`

## 5. Each publisher as its own endpoint, and the view over it
- [x] 5.1 Serve each publication system as its own MCP endpoint at
      `/mcp/publish/{channel}`, exposing two reads and one write; verify via
      `tests/test_publication.py::test_every_publisher_exposes_two_reads_and_one_write`,
      and by connecting one from the estate panel and watching the handshake
      return its three tools
- [x] 5.2 Show the impact view in Blast Radius - the affected SKUs, and what
      would happen to each publication system if this were dispatched now;
      verify by working a correction and reading the panel above the scope
      resolution

- [x] 5.3 Keep the safeguards with the tool rather than the caller: a publisher
      reached over a pipe still refuses without a recorded approval, because it
      cannot publish and has to ask the boundary that can; verify via
      `tests/test_publication.py::test_reaching_a_publisher_over_a_pipe_does_not_exempt_it`
- [x] 5.4 Refuse a print run inside its freeze window at the tool rather than
      expecting the caller to check - a tool that would start something it
      cannot stop should not exist; verify via
      `tests/test_publication.py::test_a_publisher_refuses_a_run_it_could_not_stop`
- [x] 5.5 Scope a publisher's reads to its own channel, so an estate of six is
      not one database with six front doors; verify via
      `tests/test_publication.py::test_a_publisher_will_not_report_another_channels_impact`
- [x] 5.6 Keep publisher endpoints distinguishable from ingest ones, so an
      operator can see from the path alone which can change a live listing;
      verify via
      `tests/test_publication.py::test_a_publisher_endpoint_is_distinct_from_an_ingest_one`
