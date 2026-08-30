## MODIFIED Requirements

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
