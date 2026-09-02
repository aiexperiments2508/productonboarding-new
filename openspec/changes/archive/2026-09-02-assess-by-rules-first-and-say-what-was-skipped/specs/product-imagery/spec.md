## Purpose

The images a product holds, the files behind them, and the gap where a role the
category requires was never delivered.

One rule carries most of this: **a missing photograph and a broken page must
not look the same.** Before an asset mount exists, a request for an image
returns the application shell with a success status, which a browser renders as
a broken image - exactly as it renders a genuinely absent one.

## ADDED Requirements

### Requirement: Every asset the catalog holds has a file behind it, and every declared gap has none

An image the catalog records SHALL have a file behind it, generated
deterministically from the seed. An image the seed pack deliberately omits
SHALL have no file either.

Assets are drawn rather than shipped, which keeps the pack reproducible and
keeps image bytes out of the repository. The second half matters as much as the
first: a gap that quietly acquired a file would make the missing-media finding
unreachable, and the check would pass because the data had been fixed rather
than because the product had.

#### Scenario: Held assets have files and gaps do not

- **WHEN** the catalog's assets are compared with the files on disk
- **THEN** every held asset has one and every deliberate gap has none
- **AND** `tests/test_media.py::test_every_asset_the_catalog_holds_has_a_file_behind_it`
  and `::test_the_deliberate_gaps_have_no_file_either` assert both

### Requirement: A missing image is a 404 and never the application shell

Assets SHALL be served from a mount registered ahead of the single-page
application's catch-all. A request for an image that does not exist SHALL
answer not-found; it SHALL NOT answer with the application shell.

A catch-all that answers an image request with HTML and a success status makes
a missing photograph indistinguishable from a broken page, so neither failure
can be diagnosed from the outside.

#### Scenario: An image is served as an image, and a missing one is not

- **WHEN** a held image and a missing one are each requested
- **THEN** the first is served as an image and the second is not-found rather
  than the application shell
- **AND** `tests/test_media.py::test_a_held_image_is_served_as_an_image` and
  `::test_a_missing_image_is_a_404_and_not_the_application_shell` assert both

### Requirement: A missing role is a gap that names who owes it

Where a category requires an image role that nobody has delivered, the product
SHALL report a gap naming the system that owes it. A category that requires no
imagery SHALL NOT report one.

The media strip a reviewer reads and the readiness finding that holds the
product SHALL be derived from the same source, so a strip showing a gap beside
a check reporting none is not a state the two can reach.

#### Scenario: The strip and the finding report the same gap

- **WHEN** a product missing a required image role is read
- **THEN** the media strip and the readiness finding report the same gap
- **AND** `tests/test_media.py::test_the_media_strip_reports_the_gap_the_finding_reports`
  asserts it

#### Scenario: A gap names the system that owes it

- **WHEN** a required role has not been delivered
- **THEN** the gap names the system responsible for delivering it
- **AND** `tests/test_media.py::test_a_missing_slot_names_who_owes_it` asserts it

#### Scenario: A category needing no imagery is not held for missing it

- **WHEN** a product in a category that requires no imagery is assessed
- **THEN** no missing-media gap is reported
- **AND** `tests/test_media.py::test_a_category_that_needs_no_imagery_is_not_reported_as_missing_it`
  asserts it
