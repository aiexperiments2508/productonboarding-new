# review-and-publish Specification

## Purpose
Guards the boundary between a proposed resolution and a channel: the gates a
resolution must pass to be published - a recorded human approval, evidence that
has not moved, and no open safety violation - together with exclusive publish
locks, replay-safe tool calls, ranking and rollback.

## Requirements

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

It SHALL also retract what the publish put out. For every fact the publish
recorded that nothing has since superseded, a new fact SHALL be asserted from
the instant of the rollback onwards, restoring the value that publish displaced
- the value in force immediately before the publish where the record holds one,
and the prepared catalog value otherwise, which is what the prepared content
stands on. Where the record held nothing to restore, the retraction SHALL assert
nothing rather than invent a value.

The retraction SHALL be an insertion, never an edit or a deletion: a value read
as of a moment while the content was live SHALL still return what the channel
held then, because it did hold it, while a read taken after the rollback SHALL
return the restored value and no longer return what has been pulled. Rolling the
same resolution back again SHALL retract nothing a second time. The rollback
SHALL report how many facts it retracted, and the audit entry SHALL carry that
count alongside the number of actions reversed.

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

#### Scenario: A rollback retracts what went out, without rewriting that it went out

- **WHEN** an approved correction is published, read back as of the moment it
  was live, and then rolled back
- **THEN** the rollback reports the facts it retracted; a read taken afterwards
  returns the value the publish displaced and no published value against the
  listing; and a read taken as of the moment it was live still returns what went
  out
- **AND** `tests/test_orchestration.py::test_rollback_retracts_what_was_published`
  asserts each

#### Scenario: A repeated rollback retracts nothing twice

- **WHEN** a published resolution is rolled back and then rolled back again
- **THEN** the second rollback retracts no facts
- **AND** `tests/test_orchestration.py::test_a_repeated_rollback_retracts_nothing_twice`
  asserts the empty retraction

### Requirement: A dispatch can be planned without being made

What a resolution would be sent to, and which of those systems would refuse it,
SHALL be answerable without publishing anything.

A reviewer approving a correction should see that the printed catalogue is
inside its freeze window before deciding, rather than discovering it from a
report afterwards. Planning SHALL write nothing: a surface that published as a
side effect of being looked at would be the worst possible way to learn this.

#### Scenario: Planning writes nothing

- **WHEN** a dispatch is planned
- **THEN** no action is committed
- **AND** `tests/test_publication.py::test_planning_a_dispatch_sends_nothing`
  asserts the count is unchanged

#### Scenario: A channel that cannot recall is deferred, not attempted

- **WHEN** a dispatch is planned for a correction reaching a channel inside a
  freeze window whose artefact cannot be recalled
- **THEN** that system is deferred and the deferral names the window
- **AND** `tests/test_publication.py::test_a_frozen_channel_is_deferred_rather_than_attempted`
  asserts both

### Requirement: Publishing and rollback report per system

A dispatch SHALL report an outcome for each publication system it reaches -
sent, deferred, or refused - each carrying its reason where it is not sent.

"Failed" is not an answer a caller can act on: it does not distinguish nothing
having gone out from almost everything having gone out, and the difference
decides what somebody does next.

The counts a dispatch reports SHALL be derived from the rows it returns, so the
summary cannot disagree with the detail beneath it.

#### Scenario: The counts agree with the rows

- **WHEN** a dispatch reports
- **THEN** the sent, deferred and refused counts equal the rows carrying each
  outcome
- **AND** `tests/test_publication.py::test_the_dispatch_report_counts_agree_with_its_rows`
  asserts each

#### Scenario: A channel never sent to is not reported as reverted

- **WHEN** a resolution is rolled back and one of the systems it reached was
  deferred rather than sent to
- **THEN** that system reports that it was never sent rather than reporting a
  reversal
- **AND** `tests/test_publication.py::test_a_channel_never_sent_to_is_not_reported_as_reverted`
  asserts the distinction, because reporting a reversal there would be a false
  statement about a printed page

### Requirement: A refusal is a property of the resolution, not of a channel

Where publication is refused, every system SHALL be reported refused, carrying
the single reason the approval boundary gave.

The gates - a recorded approval, evidence that has not moved, no open safety
violation - are properties of the resolution. Publishing to four channels a
resolution nobody approved would be four problems rather than none, and a
per-channel refusal would invite exactly that reading.

The reason SHALL be the one the boundary returned rather than one re-derived
here. Two accounts of why a publish was refused is one account too many.

#### Scenario: With no approval on record, every system refuses

- **WHEN** a dispatch is attempted for a resolution with no approval recorded
- **THEN** nothing is sent, every system is reported refused, and the response
  names the reason
- **AND** `tests/test_publication.py::test_a_dispatch_without_an_approval_refuses_every_system`
  asserts each

#### Scenario: One refusal is reported once

- **WHEN** a dispatch is refused across several systems
- **THEN** every system carries the same reason, and it is the response's own
- **AND** `tests/test_publication.py::test_a_refused_dispatch_reports_one_reason_not_six`
  asserts both

### Requirement: Republishing over a safety redaction needs its own release decision

Where a listing holds a safety redaction, publishing to it SHALL be refused
until a release decision has been recorded - a fourth refusal beside those the
publish path already applies.

A release decision SHALL be recorded in its own table and SHALL NOT be written
to the approvals table. If it lived there it would satisfy the first gate by
itself, and "we agreed the old value was wrong" would silently become "we agreed
the new value is right" - which is the one substitution the whole approval
architecture exists to prevent.

A release approval alone SHALL NOT publish an unapproved resolution, and a
rejected release SHALL NOT open the gate. A redaction of an ordinary field SHALL
NOT hold a publish at all, and an open safety violation SHALL still be reported
ahead of the release gate, so a reviewer sees the substantive problem rather
than only the procedural one.

Every release SHALL be recorded against the person who took it.

#### Scenario: The release decision is kept apart from the approval

- **WHEN** a release decision is recorded
- **THEN** the approvals table is unchanged
- **AND** `tests/test_redaction.py::test_a_release_decision_is_not_written_to_the_approvals_table`
  asserts it

#### Scenario: The publish is refused, then goes through

- **WHEN** a publish is attempted against a listing holding a safety redaction,
  and again once the release is recorded
- **THEN** the first is refused and the second proceeds
- **AND** `tests/test_redaction.py::test_publishing_to_a_listing_holding_a_safety_redaction_is_refused`
  and `::test_the_same_publish_goes_through_once_the_release_is_recorded` assert
  both

#### Scenario: Neither gate substitutes for the other

- **WHEN** only a release is recorded, and separately when a release is rejected
- **THEN** the unapproved resolution does not publish, and the rejection does not
  open the gate
- **AND** `tests/test_redaction.py::test_a_release_approval_alone_does_not_publish_an_unapproved_resolution`
  and `::test_a_rejected_release_does_not_open_the_gate` assert both

#### Scenario: An ordinary redaction holds nothing, and the real violation is still reported

- **WHEN** an ordinary field is redacted, and separately when an allergen
  violation is open behind a release gate
- **THEN** the first holds no publish and the second is still reported
- **AND** `tests/test_redaction.py::test_a_redaction_of_an_ordinary_field_does_not_hold_a_publish`
  and `::test_an_open_allergen_violation_is_still_reported_before_the_release_gate`
  assert both

#### Scenario: A release names who took it

- **WHEN** a release decision is recorded
- **THEN** it carries the person who took it
- **AND** `tests/test_redaction.py::test_a_release_is_recorded_against_the_person_who_took_it`
  asserts it

### Requirement: A publisher declares which of its tools mutate

Each publication system's endpoint SHALL declare which of its tools can write,
and SHALL serve exactly the tools it declares. The declared verb list SHALL
cover every tool that can write.

The count of tools is not the property worth asserting - it goes stale the
moment the surface grows. What matters is that the server serves what it
declares and that the mutating set is declared rather than guessed at from the
verbs, so an operator who wants to show somebody a blast radius does not have to
hand over the ability to act on it.

#### Scenario: A publisher serves exactly what it declares

- **WHEN** each publisher's tools are listed against its declaration
- **THEN** they match, and the mutating set is among them
- **AND** `tests/test_publication.py::test_every_publisher_declares_which_of_its_tools_mutate`
  asserts it

#### Scenario: The verb list covers every writing tool

- **WHEN** the declared verbs are compared with the tools that can write
- **THEN** the verbs cover them
- **AND** `tests/test_publication.py::test_the_declared_verbs_cover_every_tool_that_can_write`
  asserts it

### Requirement: A prohibited sale is its own publish-time refusal, independent of confidence

Where a market authority has prohibited the sale of a product, publishing SHALL
be refused by a constraint of its own in the safety gate. That refusal SHALL NOT
depend on the confidence of any inference.

This is the reason the constraint exists rather than being left to the machinery
already present. **The safety gate only ever fires on a low-confidence
inference.** A withdrawal notice is recorded *confidently* - it is a document
from a market authority saying so - which means the existing gate has no
objection to it. The product would be escalated for review, the review would
agree the notice is real, and the publish would proceed.

The refusal SHALL apply to every listing the product reaches, not only the one
that raised it, and SHALL NOT be treated as something regenerating copy can
resolve. A product may not be sold; rewriting the sentence about it does not
change that.

A product still permitted SHALL NOT be gated.

#### Scenario: The sale gate is part of the publish refusal

- **WHEN** a publish is attempted for a product whose sale is prohibited
- **THEN** it is refused by the sale constraint
- **AND** `tests/test_validator.py::test_the_sale_gate_is_part_of_the_publish_refusal`
  asserts it

#### Scenario: A withdrawal blocks every listing the product reaches

- **WHEN** a withdrawn product's listings are validated
- **THEN** every one of them is blocked
- **AND** `tests/test_validator.py::test_a_withdrawal_blocks_every_listing_the_product_reaches`
  asserts it

#### Scenario: Copy cannot fix a withdrawal

- **WHEN** the remediation for a withdrawal is derived
- **THEN** regenerating copy is not among the options
- **AND** `tests/test_validator.py::test_a_withdrawal_is_not_something_copy_can_fix`
  asserts it

#### Scenario: A permitted product is not gated

- **WHEN** a product with no prohibition against it is validated
- **THEN** the sale constraint does not fire
- **AND** `tests/test_validator.py::test_a_product_still_permitted_is_not_gated`
  asserts it

### Requirement: A channel may ask what it is carrying, and only what it is carrying

The publication surface SHALL offer a read answering what lines a channel is
carrying, scoped to the asking system. It SHALL NOT name a line belonging to
another channel.

The existing listing lookup deliberately refuses to confirm a line the asking
channel does not carry, which is what stops one channel discovering another's
assortment by exhaustive guessing. Telling a channel what is on its own shelf is
a different act, and the scoping is what keeps it different.

The answer SHALL be in the catalogue's own order rather than sorted by
identifier. Sorting by identifier orders a shop by brand prefix, which is
alphabetical rather than meaningful.

A downstream application SHALL obtain what a channel carries by asking. It SHALL
NOT hold its own copy of the catalogue - a list written down outside the
platform is wrong the next time a product is renamed, and it fails silently,
because "not carrying these lines" is a truthful answer about lines that no
longer exist.

#### Scenario: A channel can be asked what it is carrying

- **WHEN** a channel asks for its shelf
- **THEN** it is answered with the lines it carries
- **AND** `tests/test_publication.py::test_a_channel_can_be_asked_what_it_is_carrying`
  asserts it

#### Scenario: A shelf never names another channel's line

- **WHEN** a channel asks for its shelf
- **THEN** no line belonging to another channel appears in the answer
- **AND** `tests/test_publication.py::test_a_shelf_never_names_another_channels_line`
  asserts it

#### Scenario: The shelf leads with what the catalogue leads with

- **WHEN** a shelf is returned
- **THEN** its order is the catalogue's, not the identifier ordering
- **AND** `tests/test_publication.py::test_a_shelf_leads_with_the_lines_the_catalog_leads_with`
  asserts it
