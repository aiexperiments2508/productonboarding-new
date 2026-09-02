## 1. Rewriting fields at once

- [x] 1.1 Give `_rewrite` its own spend and error collections rather than the
      shared lists it appends to today, and return them beside the text, so a
      worker owns everything it produces; verify by inspection that no shared
      mutable is written from inside a worker
- [x] 1.2 Fan the rewrite targets across a bounded pool sized by a module
      constant beside `MAX_REGENERATIONS`, assembling results by target index
      rather than by completion; verify via
      `tests/test_graph.py::test_results_follow_the_targets_not_the_replies`
- [x] 1.3 Keep the serial case reachable by setting the pool to one, so the two
      paths can be compared in a single run; verify via
      `tests/test_graph.py::test_parallel_regeneration_matches_the_sequential_result`
      over the actions, their order, the text, the citations and the trace hash
- [x] 1.4 Fold each worker's spend into the stage's record and deduplicate the
      outage line once, after the pool drains; verify via
      `tests/test_graph.py::test_spend_within_a_stage_survives_concurrent_workers`
      and
      `tests/test_graph.py::test_a_gateway_outage_is_reported_once_however_many_workers_meet_it`

## 2. Reading documents at once, writing them in order

- [x] 2.1 Split `extract` into a concurrent prefetch of every document's reading
      and the existing sequential persistence loop over readings already in
      hand; verify by inspection that the watermark still advances inside the
      sequential half
- [x] 2.2 Assert that persistence order follows the tape whatever order the
      readings completed in, and that a covering email restating its own
      specification still records nothing; verify via
      `tests/test_graph.py::test_extraction_persists_in_tape_order_however_its_readings_raced`
- [x] 2.3 Confirm the prefetch pays for readings the loop later skips, and
      record that cost in `design.md` rather than hiding it

## 3. Making the progress visible

- [x] 3.1 Merge each streamed stage result into view state as it arrives instead
      of discarding it and re-fetching at the end; verify by starting a run and
      watching content appear before the run finishes
- [x] 3.2 Render the arriving stages as a staggered sequence using the entrance
      already defined in `motion.css`, not a new one
- [x] 3.3 Confirm the final message still reconciles the view, so a stage whose
      result was superseded mid-run does not persist on screen

## 4. Paying no first-call cost in a rehearsal

- [x] 4.1 Warm the response cache from `scripts/prepare_demo.py` so a rehearsed
      run reads every repeated call from SQLite; verify the second run of the
      same correction reports cache hits for every stage that reached a model
- [x] 4.2 Leave the cache honest: a warmed run must still be a real run, so
      record cache hits as hits rather than as calls; verify via
      `tests/test_graph.py::test_a_served_call_is_recorded_as_a_hit_not_as_work`
      and
      `tests/test_graph.py::test_warming_the_cache_leaves_no_pending_decision`

## 5. Confirming the claim

- [x] 5.1 Time a cold run end to end against a live gateway and record the
      figure in the proposal; the target is under 45 seconds. **Measured at
      21.4 seconds** to the approval gate, with sixteen fresh model calls and
      no cache hits on any pipeline stage
- [x] 5.2 Re-run the whole suite with the gateway unreachable and confirm
      nothing regressed: 304 passed and 6 skipped before this change, 309
      passed and 6 skipped after it, the five being the ones added here
- [x] 5.3 Confirm the concurrency does not move `trace_hash`; verify via
      `tests/test_graph.py::test_two_validations_of_one_change_set_agree_on_the_trace_hash`.
      Checked against one change set at a pinned instant rather than across two
      whole runs, because a run pins its recorded instant from the wall clock
      and the validator folds that instant into the hash - so two runs
      legitimately disagree for a reason that has nothing to do with
      concurrency, and asserting otherwise would be a test of the clock
