## Purpose

The documents this system is answerable to, made editable by the people
answerable for them.

The corpus is not reference material. Three readiness checks retrieve from it
and between them they decide what publishes, so a retailer who cannot add a
regulation without a developer has a compliance surface as current as its last
deployment. This capability is the door that changes it, and every requirement
below is about keeping that door narrow.

## ADDED Requirements

### Requirement: A caller names a document, never a path

Every operation on a corpus document SHALL address it by document identifier.
The system SHALL locate the file by reading document metadata and SHALL compose
the path itself when creating one. No filesystem path SHALL be accepted from a
caller.

There is then no traversal to filter, because there is no caller-supplied path
to traverse. That is a stronger guarantee than stripping parent references, and
unlike stripping it does not have to be correct about drive letters, share
prefixes or normalisation order in order to hold.

The identifier SHALL be validated against a narrow pattern, and a composed path
SHALL be asserted to lie inside the corpus root as a second line of defence.

#### Scenario: An identifier cannot escape the corpus

- **WHEN** a document identifier containing path syntax is submitted
- **THEN** it is refused
- **AND** `tests/test_corpus_library.py::test_a_document_id_cannot_escape_the_corpus`
  asserts it

#### Scenario: A title cannot escape the corpus

- **WHEN** a new document is created with a title containing path syntax
- **THEN** the composed path stays inside the corpus root
- **AND** `tests/test_corpus_library.py::test_a_title_cannot_escape_the_corpus`
  asserts it

### Requirement: Every mutation is attributable, audited, and rebuilt under one lock

Creating, editing, retiring, restoring and destroying a document SHALL each
require a named actor, SHALL be refused without one, and SHALL be written to the
audit ledger.

Each mutation SHALL write and then rebuild the index under a single lock. The
index is a process-wide cache rebuilt in full and the handlers run in a
threadpool, so two concurrent saves without the lock is a corrupt index.

A type that is synthesised on every build SHALL NOT be authorable, because a
file of one would be silently overwritten by the next rebuild.

#### Scenario: A change has to be attributable

- **WHEN** a mutation arrives with no actor
- **THEN** it is refused
- **AND** `tests/test_corpus_library.py::test_a_change_has_to_be_attributable`
  asserts it

#### Scenario: Every mutation reaches the ledger

- **WHEN** each kind of mutation is performed
- **THEN** the ledger holds a row for it naming the actor
- **AND** `tests/test_corpus_library.py::test_every_mutation_is_audited_against_a_name`
  asserts it

#### Scenario: A synthesised type cannot be authored

- **WHEN** a document of a type the build synthesises is submitted
- **THEN** it is refused
- **AND** `tests/test_corpus_library.py::test_a_synthesised_type_cannot_be_authored`
  asserts it

### Requirement: A document survives an edit unchanged except where it was edited

Document metadata SHALL round-trip through the writer for every authored
document. Keys the writer does not model SHALL be preserved rather than
dropped.

A value that would read back as a different shape than it was written - a
scalar that would parse as a list, or a list item containing the separator -
SHALL be refused rather than written. A body that begins with a horizontal rule
SHALL NOT be read back as a second metadata block.

Dropping a key nobody happened to model is a field disappearing out of a
compliance record because a form had no box for it.

Writes SHALL be atomic, so an interrupted save cannot leave a half-written
regulation in the corpus.

#### Scenario: Front matter round-trips for every authored document

- **WHEN** every authored document is read and written back
- **THEN** its metadata is unchanged
- **AND** `tests/test_corpus_library.py::test_frontmatter_round_trips_for_every_authored_document`
  asserts it

#### Scenario: A value that would read back differently is refused

- **WHEN** a scalar that would parse as a list, or a list item containing the
  separator, is submitted
- **THEN** it is refused
- **AND** `tests/test_corpus_library.py::test_a_scalar_that_would_read_back_as_a_list_is_refused`
  and `::test_a_list_item_containing_a_comma_is_refused` assert both

#### Scenario: Unmodelled keys survive an edit

- **WHEN** a document carrying keys the writer does not model is edited
- **THEN** those keys are still present afterwards
- **AND** `tests/test_corpus_library.py::test_unmodelled_frontmatter_keys_survive_an_edit`
  asserts it

#### Scenario: A body opening with a rule is not a second header

- **WHEN** a document whose body begins with a horizontal rule is written and
  read back
- **THEN** the body is intact and no second metadata block is parsed
- **AND** `tests/test_corpus_library.py::test_a_body_starting_with_a_rule_is_not_read_as_a_second_header`
  asserts it

### Requirement: Removal is retirement, and destruction is a second armed act

A document SHALL be removable from the index by retirement, which SHALL leave
the file in place. A retired document SHALL produce no chunks and SHALL be
restorable.

A decision taken while a document was in force has to stay readable against it,
so retirement never deletes.

Destroying a document SHALL be refused until it has been retired, and SHALL
write the document's whole text to the audit ledger before unlinking it.
Recoverable has to mean recoverable when the branch was never committed.

The status filter SHALL be applied where the corpus is walked, not where a
single document's text is chunked, so that "this text produces these chunks"
stays a fact about the text rather than about a status that moves under the
tests asserting it.

#### Scenario: A created document is retrievable at once

- **WHEN** a document is created
- **THEN** it is retrievable without a further rebuild
- **AND** `tests/test_corpus_library.py::test_a_created_document_is_retrievable_at_once`
  asserts it

#### Scenario: Retiring leaves the file and clears the index

- **WHEN** a document is retired
- **THEN** it produces no chunks and its file is still on disk
- **AND** `tests/test_corpus_library.py::test_a_retired_document_leaves_the_index_and_stays_on_disk`
  and `::test_restoring_puts_it_back` assert both directions

#### Scenario: Chunking still answers for a retired file

- **WHEN** a retired document's text is chunked directly
- **THEN** it still produces its chunks, because that is a fact about the text
- **AND** `tests/test_corpus_library.py::test_chunk_document_still_answers_for_a_retired_file`
  asserts it

#### Scenario: A hard delete requires retirement first

- **WHEN** an active document is destroyed
- **THEN** it is refused until it has been retired
- **AND** `tests/test_corpus_library.py::test_hard_delete_requires_retirement_first`
  asserts it

#### Scenario: A destroyed document is recoverable from the ledger

- **WHEN** a retired document is destroyed
- **THEN** its whole text is in the ledger
- **AND** `tests/test_corpus_library.py::test_a_deleted_document_is_recoverable_from_the_ledger`
  asserts it

### Requirement: What would notice a document leaving is shown before it leaves

Before a document is retired or destroyed, the system SHALL report what depends
on it: the identifiers the application names literally, and whether the document
is the last active member of a type something load-bearing reads.

A reading check that retrieves nothing returns no findings and reports the
assessment complete. So retiring the last regulation does not fail loudly - it
makes every product **pass** the check that exists to stop it, and calls the
assessment complete. A fail-open that reads as a clean run is the worst shape a
compliance failure can take.

The refusal SHALL be distinguishable from a malformed request, because the
request was well formed and the state of the corpus is what refused it, and a
caller who has read the list SHALL be able to repeat the request having
acknowledged it.

The dependency scan SHALL NOT report its own example strings as references.

#### Scenario: Removing a document the code names is refused

- **WHEN** a document whose identifier appears literally in the application is
  retired
- **THEN** it is refused with the references listed, and the refusal is
  distinguishable from a bad request
- **AND** `tests/test_corpus_library.py::test_removing_a_document_the_code_names_is_refused`
  asserts it

#### Scenario: The last of a load-bearing type is flagged

- **WHEN** the last active document of a load-bearing type is retired
- **THEN** the response names the check that stops working
- **AND** `tests/test_corpus_library.py::test_retiring_the_last_of_a_load_bearing_type_is_flagged`
  asserts it

#### Scenario: The scan does not report its own examples

- **WHEN** the dependency scan runs
- **THEN** identifiers appearing only as its own examples are not reported
- **AND** `tests/test_corpus_library.py::test_the_reference_scan_does_not_report_its_own_examples`
  asserts it

### Requirement: An upload is extracted for a person to read, never written unread

An uploaded document SHALL be converted to editable text and returned to the
editor. It SHALL NOT become a corpus document until a person saves it.

Extraction is a guess. A regulation is what three readiness checks are
answerable to, and a mis-parsed table that silently becomes cited regulation is
a worse outcome than an upload that needs five minutes of tidying.

Markdown, plain text and word-processor documents SHALL be readable with no
additional dependency; heading structure SHALL be preserved, because a document
arriving as one unbroken block retrieves badly and cites worse. PDF support
SHALL be feature-detected and SHALL report its absence in a sentence rather
than failing at import, and SHALL insert page markers, because a PDF carries no
heading structure and without them every chunk of a long regulation cites the
same empty heading.

A file whose content does not match its declared type, and a suffix that is not
accepted, SHALL each be refused by name. Upload size SHALL be capped at the same
figure the estate intake uses. A stored original SHALL NOT be indexed a second
time beside the document made from it.

#### Scenario: A word-processor document becomes markdown with its headings

- **WHEN** a `.docx` is uploaded
- **THEN** it is returned as markdown carrying its heading levels, and can then
  be saved and retrieved
- **AND** `tests/test_corpus_library.py::test_a_docx_becomes_markdown_with_its_headings`
  and `::test_an_extracted_docx_can_be_saved_and_retrieved` assert both

#### Scenario: A PDF gets page headings

- **WHEN** a PDF is uploaded with the reader available
- **THEN** page markers are inserted so the chunks cite distinguishable
  headings
- **AND** `tests/test_corpus_library.py::test_a_pdf_gets_page_headings` asserts
  it

#### Scenario: A mislabelled or unacceptable upload is refused by name

- **WHEN** a file that is not what it claims, or a suffix that is not accepted,
  is uploaded
- **THEN** it is refused with a reason
- **AND** `tests/test_corpus_library.py::test_a_mislabelled_pdf_says_so` and
  `::test_an_unaccepted_suffix_is_refused` assert both

#### Scenario: Upload size is capped

- **WHEN** an upload exceeds the cap
- **THEN** it is refused
- **AND** `tests/test_corpus_library.py::test_upload_size_is_capped` asserts it

#### Scenario: A stored original is not indexed twice

- **WHEN** an uploaded file is stored beside the document made from it
- **THEN** only the document is indexed
- **AND** `tests/test_corpus_library.py::test_a_stored_original_is_not_indexed_twice`
  asserts it

### Requirement: A save rebuilds the lexical index and reports the vectors as behind

Saving a document SHALL rebuild the lexical index without invoking a model, and
SHALL NOT rebuild the embedding matrix. The index SHALL report that its vectors
have fallen behind, and rebuilding them SHALL be a separate explicit act.

Editing has to be free or nobody edits: no gateway, no tokens, milliseconds.
Embeddings cost money and can fail, which makes them a different kind of act.

#### Scenario: An edited document is findable immediately

- **WHEN** a document is edited
- **THEN** the new text is retrievable at once, and the index reports the
  vectors as stale
- **AND** `tests/test_corpus_library.py::test_a_created_document_is_retrievable_at_once`
  covers the immediacy, and
  `::test_an_edit_that_preserves_the_chunk_count_invalidates_the_matrix` covers
  the staleness
