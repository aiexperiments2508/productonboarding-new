## 1. The answer key

- [x] 1.1 Emit `data/golden/extractions.jsonl` from the generator, one row per
      document the extractor is asked to read, out of the same event payloads
      the prose was written from; verify via
      `tests/test_golden.py::test_key_covers_exactly_the_documents_extract_reads`
- [x] 1.2 Carry in each row the fields a correct reading produces, plus the
      scope the payload settles and the readings that are defensible where it
      settles more than one; verify via
      `test_every_keyed_row_is_something_the_catalog_can_hold`
- [x] 1.3 Assert the key still holds the classes the measurement turns on - an
      ambiguous correction, an immaterial document, a multi-value correction, a
      determinate scope; verify via `test_the_key_still_contains_the_question`
- [x] 1.4 Assert the key and the deterministic fallback agree on every field
      both read; verify via `test_key_agrees_with_the_deterministic_fallback`
      over the eight shared fields and
      `test_key_agrees_with_the_fallback_on_correction_kind`
- [x] 1.5 Pin the scope-vocabulary translation between the prompt's three
      answers and the catalog's own words; verify via
      `test_the_fallback_answers_applies_to_in_the_catalogs_vocabulary`
- [x] 1.6 Git-ignore the key and the eval output, since both are regenerated
      rather than carried; verify `data/golden/` and `data/eval/` are ignored

## 2. Grading the prompt that ships

- [x] 2.1 Lift the extraction messages into one function the node and the scorer
      both call; verify via
      `test_the_prompt_the_eval_grades_is_the_prompt_that_ships`
- [x] 2.2 Lift the claim-scan inputs into one function the node and the scorer
      both call; verify by inspection that the scan node and the scorer take the
      same rows, assets and confirmed set

## 3. The harness

- [x] 3.1 Grade extraction per document - path, value raw and coerced,
      materiality, correction kind, scope class, and the rows a correct reading
      would leave behind; verify against the recorded run in
      `data/eval/report.json`
- [x] 3.2 Count a reply the gateway will not accept as a refusal with a named
      reason, excluded from the accuracy denominators; verify the recorded run
      reports ten answered, five refused and the reason for all five
- [x] 3.3 Report materiality as precision and recall with their counts, never as
      one combined score; verify the recorded run reports 1.00 and 0.83 with the
      confusion counts beside them
- [x] 3.4 Report the scope answer as a three-class confusion matrix, counting an
      off-contract reply as its own class, and report the ambiguous-answered-as-
      variant cell on its own; verify the recorded run reports it as zero
- [x] 3.5 Grade scope resolution and the claim scan on real runs, taking the
      scope truth as the corrections delivered for that product by that day and
      reporting rather than grading a run the record leaves open; verify against
      the five scope rows in the recorded run
- [x] 3.6 Bucket stated confidence against observed accuracy with the safety
      threshold as its own edge, and report the at-or-above-threshold count
      separately; verify against the calibration section of the recorded run
- [x] 3.7 Pace the harness, back off on a provider rate limit, fail fast once a
      full chain has failed, and label rate-limited rows as quota results;
      verify the recorded run carries its minimum interval and backoff count
- [x] 3.8 Keep the response cache in a sidecar outside the store each scenario
      drops, and reseed with the checkpoints cleared between scenarios; verify a
      repeat run returns the same report
- [x] 3.9 Refuse to run against an unreachable gateway rather than reporting
      fallback readings as model results; verified by inspection of the health
      check at entry, which exits naming the gateway address and the reason.
      Not observed running - a gateway is reachable in this environment
- [x] 3.10 Write the report with the gateway, the key, the document count, the
      thresholds in force and the notes naming what the measurement cannot say;
      verify `data/eval/report.json` carries all four notes
- [x] 3.11 Record the first run against a live gateway; verify
      `data/eval/report.json` exists and carries the fifteen-document result

## 4. Outstanding

- [ ] 4.1 Update the README: it still reports 267 tests where the suite is 304,
      and it has no evaluation section at all - no mention of what the harness
      measures, what the first run found, or how to run it. The `.gitignore`
      note says the numbers worth keeping are the ones recorded in the README,
      and none of them are. Verify by finding the corrected count and an
      evaluation section in `README.md`
- [ ] 4.2 Measure the fail-closed safety gate. No document carrying a
      safety-class attribute falls inside the eval window, so the recorded run
      reports `safety_documents: 0` and the gate's threshold is justified by
      nothing. Verify by a run whose safety-gate section is non-empty
- [ ] 4.3 Run the comparison across models. Only the extraction touchpoint has
      been swept - `data/eval/by_model.json`, three models, extract only - and
      scope, claims and calibration have never run against more than one model.
      Verify by a report carrying more than one model with all three touchpoints
      populated
- [ ] 4.4 Widen the labelled set. Fifteen documents cannot support a headline
      accuracy figure; the useful output today is the confusion matrix and the
      named failure modes, and the report should keep saying so until the set is
      large enough that it need not. Verify by a document count that makes a
      percentage defensible, or by the report continuing to lead with the matrix
- [ ] 4.5 Decide the open question in design.md: whether a safety-class document
      is added to the tape's eval window, or the gate is measured by a separate
      fixture
