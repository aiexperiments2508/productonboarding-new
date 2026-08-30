## Purpose

Guards the boundary between a proposed resolution and a channel: the gates a
resolution must pass to be published - a recorded human approval, evidence that
has not moved, and no open safety violation - together with exclusive publish
locks, replay-safe tool calls, ranking and rollback.

## ADDED Requirements

### Requirement: Publishing requires a recorded approval

A publish SHALL be refused unless a reviewer decision approving that resolution
is on record. A decision that is not an approval SHALL also refuse, naming the
decision that was taken. Refusal SHALL be a recorded event rather than an
absence, so "why did this not go out" is answerable from the audit trail.

#### Scenario: No decision on record refuses

- **WHEN** a publish is attempted with no reviewer decision recorded
- **THEN** it is refused as not approved
- **AND** `tests/test_orchestration.py::test_commit_without_approval_is_refused`
  asserts both

#### Scenario: A rejection refuses and says so

- **WHEN** the recorded decision is a rejection and a publish is attempted
- **THEN** it is refused and the detail names the recorded decision
- **AND** `tests/test_orchestration.py::test_commit_after_rejection_is_refused`
  asserts both

#### Scenario: An approved publish writes an audit trail

- **WHEN** an approved resolution is published
- **THEN** exactly one commit entry is written, with published provenance
- **AND** `tests/test_orchestration.py::test_approved_commit_writes_an_audit_trail`
  asserts both

### Requirement: A publish records what each channel received

A publish SHALL record the published value as a fact with published provenance
citing the source document version it came from, both against the entity
corrected and against every listing that received it, so that "what did this
channel receive, and on whose authority" stays answerable after the next
correction lands.

#### Scenario: The published value and every listing that got it are recorded

- **WHEN** an approved variant correction is published
- **THEN** the corrected value is held with published provenance citing the
  source document version, and a published value is recorded against each of the
  four listings that carry it
- **AND** `tests/test_orchestration.py::test_a_commit_records_what_went_live`
  asserts each

### Requirement: Publish locks are exclusive at the database

An exclusive publish lock on a channel, product and batch date SHALL be held by
at most one resolution, enforced by the store rather than by application logic,
so a conflicting concurrent publish fails rather than races. A conflict SHALL
name the resource and the holder. Non-exclusive holds SHALL NOT block each
other, and different batch dates SHALL NOT conflict. Releasing a lock SHALL free
the batch.

#### Scenario: Two exclusive locks on one batch conflict

- **WHEN** two resolutions take an exclusive lock on the same channel, product
  and batch date
- **THEN** the first succeeds, the second is refused as a conflict, and the
  refusal names the holding resolution
- **AND** `tests/test_orchestration.py::test_two_hard_locks_on_the_same_channel_product_day_conflict`
  asserts each

#### Scenario: A conflict is reported as a violation naming the resource

- **WHEN** a second resolution from a different case tries the same batch
- **THEN** the returned violation names the publish-conflict constraint, the
  resource, the channel, and the holding resolution
- **AND** `tests/test_orchestration.py::test_conflict_names_the_resource_and_the_holder`
  asserts each

#### Scenario: Exploration is not exclusive

- **WHEN** two resolutions take non-exclusive holds on the same batch, and
  separately two exclusive locks are taken on different batch dates
- **THEN** all four succeed
- **AND** `tests/test_orchestration.py::test_soft_holds_do_not_block_each_other`
  and `test_different_batch_dates_do_not_conflict` assert them

#### Scenario: Releasing frees the batch

- **WHEN** an exclusive lock is released and another resolution retries
- **THEN** the retry succeeds
- **AND** `tests/test_orchestration.py::test_released_lock_frees_the_batch`
  asserts it

#### Scenario: Two approved resolutions cannot both publish the same batch

- **WHEN** two separately approved resolutions publish the same change to the
  same channel batch
- **THEN** the first commits and the second is refused as a conflict
- **AND** `tests/test_orchestration.py::test_second_publish_of_the_same_listing_is_refused`
  asserts both

#### Scenario: Conflicts surface before a reviewer approves

- **WHEN** a batch is already held and a resolution is proposed against it
- **THEN** the proposal is refused and names the conflict, rather than waiting
  until after approval
- **AND** `tests/test_orchestration.py::test_proposal_surfaces_conflicts_before_approval`
  asserts both

### Requirement: A replayed call returns its original result

A mutating call carrying an idempotency key SHALL, on replay of that key, return
the result of the original call and act only once, and SHALL mark the replay as
such. Distinct keys SHALL NOT be deduplicated. A call that failed SHALL NOT be
cached as a result, so a later properly approved retry can succeed.

#### Scenario: A replayed publish does not act twice

- **WHEN** the same publish is called twice with one key
- **THEN** both report success, the second is marked a replay, and exactly one
  committed action exists
- **AND** `tests/test_orchestration.py::test_replayed_commit_returns_the_original_result`
  asserts each

#### Scenario: A different key is a different call

- **WHEN** the same publish is called under two different keys
- **THEN** the second is not marked a replay
- **AND** `tests/test_orchestration.py::test_distinct_keys_are_not_deduplicated`
  asserts it

#### Scenario: A refusal stays refusable

- **WHEN** an unapproved publish is refused under a key, the resolution is then
  approved, and the same key is retried
- **THEN** the retry succeeds rather than returning the cached refusal
- **AND** `tests/test_orchestration.py::test_failed_calls_are_not_cached_as_results`
  asserts both

### Requirement: Publishing is refused once the evidence has moved

Immediately before writing, a publish SHALL re-check every attribute it touches
against what is in force at that instant, and SHALL refuse if any of them now
stands on a later source version than the one the resolution was validated
against. The refusal SHALL name the attribute, report the version in force and
the version validated against, and be blocking. A refused publish SHALL take no
lock and SHALL be recorded.

#### Scenario: A later version in force refuses the publish

- **WHEN** a resolution validated against v2 is published after v3 has landed
- **THEN** it is refused for a stale version, and the violation names the
  attribute, reports 3 as required and 2 as available, is blocking, and says the
  resolution must be revalidated
- **AND** `tests/test_orchestration.py::test_publish_is_refused_once_a_later_source_version_is_in_force`
  asserts each

#### Scenario: A refusal leaves the batch free and leaves a record

- **WHEN** the same publish is refused
- **THEN** no lock is held afterwards and exactly one refusal entry is recorded
  naming the reason
- **AND** `tests/test_orchestration.py::test_a_refused_publish_takes_no_lock_and_is_on_the_record`
  asserts both

#### Scenario: The version the resolution cites still publishes

- **WHEN** the version in force is the one the resolution was validated against
- **THEN** the publish succeeds
- **AND** `tests/test_orchestration.py::test_the_source_version_the_resolution_cites_still_publishes`
  asserts it

### Requirement: Publishing is refused while a safety violation is open

A publish SHALL be refused while any blocking safety-confidence or
allergen-declaration violation is open on an affected listing, whatever the
reviewer approved. The refusal SHALL carry those violations and SHALL take no
lock.

#### Scenario: A low-confidence safety inference refuses the publish

- **WHEN** an approved resolution carries an allergen change at 0.62 confidence
- **THEN** the publish is refused for a safety hold, the safety-confidence
  violation is among those returned, and no lock is held
- **AND** `tests/test_orchestration.py::test_publish_is_refused_while_a_safety_violation_is_open`
  asserts each

#### Scenario: Confident is not the same as declared

- **WHEN** an approved resolution carries the same allergen change at 0.95
  confidence while no prepared page declares it
- **THEN** the publish is refused for a safety hold and every returned violation
  is a blocking allergen-declaration violation
- **AND** `tests/test_orchestration.py::test_publish_is_refused_while_an_allergen_declaration_is_open`
  asserts each

### Requirement: Safety ranks ahead of any reviewer weighting

Ranking of candidate resolutions SHALL place those with no open safety flag
ahead of those with one, as a pre-sort rather than a weighted term, so that no
setting of the reviewer's weights can make a flagged resolution outrank an
unflagged one.

#### Scenario: A flagged resolution cannot be weighted to the top

- **WHEN** a flagged resolution scoring perfectly on the weighted measure is
  ranked against an unflagged one scoring poorly, with the weight set entirely
  on that measure
- **THEN** the unflagged resolution ranks first, and not because it scored
  higher
- **AND** `tests/test_orchestration.py::test_a_safety_flag_outranks_any_weighting`
  asserts the order and the scores

### Requirement: Rollback frees the batch and reverses the actions

Rolling back a published resolution SHALL release its exclusive publish locks,
mark its committed actions reversed, reopen the case and record the rollback, so
that the batch is genuinely available to another resolution rather than merely
flagged.

#### Scenario: Locks are released and actions marked reversed

- **WHEN** a published resolution is rolled back
- **THEN** it reports success and the number of actions reversed, and the
  reservation on the batch is released
- **AND** `tests/test_orchestration.py::test_rollback_releases_locks_and_reverses_actions`
  asserts each

#### Scenario: The batch is publishable again

- **WHEN** a second approved resolution publishes the same batch after the
  rollback
- **THEN** it commits
- **AND** `tests/test_orchestration.py::test_the_batch_is_reusable_after_rollback`
  asserts it
