## 1. The kinds the queue could not see

- [x] 1.1 Make ingestion's gap predicate public and derive open data gaps from
      it, so the queue and the ingestion that recorded the row cannot disagree
      about what counts as missing; verify via
      `tests/test_graph.py::test_a_required_value_submitted_empty_opens_a_case_as_a_gap`
- [x] 1.2 Recompute a source conflict from the event that carried the losing
      value against what is in force now, bounding how far back the tape is
      read; verify via
      `tests/test_graph.py::test_a_feed_row_that_lost_a_precedence_contest_opens_a_case`
- [x] 1.3 Retire a conflict the record came round to, by deriving rather than
      storing it; verify via
      `tests/test_graph.py::test_a_conflict_the_record_came_round_to_stops_being_open`
- [x] 1.4 Derive a withdrawn-document signal from the document status the
      overlay already carries

## 2. Scoping the withdrawal

- [x] 2.1 Build the map of which entity stands on which document *version* on
      the lineage walk that is already happening, rather than in a second scan
- [x] 2.2 Move the unchanged-value short-circuit after that resolution, because
      an unchanged value is still standing on whatever asserted it
- [x] 2.3 Open a case only where a fact in force pins the retracted version, so
      a retraction that clears an earlier notice does not become an incident;
      verify via
      `tests/test_graph.py::test_withdrawing_a_revision_nothing_stands_on_opens_nothing`
- [x] 2.4 Raise one signal per entity rather than one per attribute path
- [x] 2.5 Mark the signal as not a resolver, so it cannot retire the signals it
      stands beside; verify via the existing
      `tests/test_graph.py::test_a_withdrawal_retires_what_it_clears` and
      `::test_a_withdrawal_does_not_cancel_an_unrelated_correction` continuing
      to pass

## 3. The Fabric reads left to right

- [x] 3.1 Put what is arriving, the graph, and what is in force in that order
- [x] 3.2 Move the live event feed beside the picture it is about, rather than
      beside the transport that released it
- [x] 3.3 Show what suppliers have sent as a queue of bundles waiting to be
      processed, filled from the arrival broadcast rather than by polling

## 4. The walk

- [x] 4.1 Call the sequential pass from the queue, lighting the working product
      and leaving a verdict-coloured ring on the one before
- [x] 4.2 Pace the reading on the client, and ask the server for the work as
      fast as it can do it, because a buffering transport collapses a
      server-paced stream into one frame
- [x] 4.3 Pin the map to the walking supplier for the duration, once per bundle,
      so nothing is assessed off-page
- [x] 4.4 Restore the reader's own map filters when the walk gives the map back

## 5. The map stops shouting

- [x] 5.1 Draw a listing at full weight only when it is traced, in the blast
      radius, being worked, or stopped
- [x] 5.2 Ride the remaining count on the variant as a chip that traces it, so
      nothing is hidden
- [x] 5.3 Put the systems tier behind a toggle, off by default, because it is
      the estate rather than the catalog

## 6. The sweep

- [x] 6.1 Work every open case in turn, each as its own run stopping at its own
      approval gate
- [x] 6.2 Re-read the case list between runs, so a case a run opened is picked
      up rather than waiting to be noticed
- [x] 6.3 Give the run starter a flag for whether to announce itself, so the
      sweep does not move the reader off the map after the first case
- [x] 6.4 Bound the loop, so "walks until the queue is empty" has a ceiling
      somebody wrote down
- [x] 6.5 Let the sweep be stopped, and report its own tally when it ends

## 7. Verified against the running platform

- [x] 7.1 A pack pushed through the vendor portal appears in the queue with no
      reload
- [x] 7.2 The walk lights one product per beat
- [x] 7.3 The sweep reaches its approval gate without taking the reader off the
      map
