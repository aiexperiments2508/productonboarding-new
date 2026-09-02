## 1. The shelf

- [x] 1.1 Add a read on the publication server answering what a channel is
      carrying; verify via
      `tests/test_publication.py::test_a_channel_can_be_asked_what_it_is_carrying`
- [x] 1.2 Scope it to the asking system, so it cannot become the exhaustive
      lookup the listing read refuses to be; verify via
      `tests/test_publication.py::test_a_shelf_never_names_another_channels_line`
- [x] 1.3 Order it by the catalogue's own order rather than by SKU, which sorts
      a shop by brand prefix; verify via
      `tests/test_publication.py::test_a_shelf_leads_with_the_lines_the_catalog_leads_with`
- [x] 1.4 Have the storefront ask rather than hold a list of SKUs, so a rename
      cannot empty the shop
- [x] 1.5 Key prices the way the generator keys them, by variant rather than by
      SKU, and show no price where there is none

## 2. The endpoint session

- [x] 2.1 Own the session in a task of its own for its whole life, rather than
      opening it inside whichever request arrived first
- [x] 2.2 Answer every one of two overlapping calls; verify via
      `tests/test_app_boundary.py::test_two_calls_at_once_do_not_wedge_an_endpoint`
- [x] 2.3 Shield a call from its caller's cancellation, so a browser that
      navigated away leaves the endpoint usable; verify via
      `tests/test_app_boundary.py::test_a_caller_that_gives_up_does_not_take_the_session_with_it`
- [x] 2.4 Give up on a call that does not answer inside thirty seconds and
      reopen the session, so an endpoint wedged another way recovers without a
      restart
- [x] 2.5 Say in the tests that they do not reproduce the original deadlock,
      which needs the real transport's task affinity and a live platform - a
      test named for a bug it cannot reproduce reads as coverage

## 3. The decision on a proposed line

- [x] 3.1 Put the acceptance panel first in the drawer for a card in the
      Proposed lane, because on a proposal it is the only thing there is to do
- [x] 3.2 Ask for a name and write it to the ledger, since accepting a line
      means taking responsibility for what it says about something never sold
- [x] 3.3 Offer the SKU without insisting on it, minting one when it is left
      empty
- [x] 3.4 Do not ask for the name or category, which came from the supplier
- [x] 3.5 Say afterwards that the line is incomplete and with its supplier,
      rather than reporting a product created
- [x] 3.6 Say afterwards that accepting is not publishing, and that putting the
      line on a channel is a decision behind its own gate
