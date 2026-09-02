## 1. The assortment as data

- [x] 1.1 Add `data/profiles/ashcombe.json` carrying eight branches, the
      taxonomy, the supplier roster, the catalogue and the per-branch facts the
      running system needs
- [x] 1.2 Select the profile by environment variable, the way the data seed is
      already selected
- [x] 1.3 Write the parts the platform consults into `catalog.json`, and read
      the category prefixes from the baseline in `readiness/checks.py`,
      `readiness/preview.py` and `lifecycle/` rather than spelling them out
- [x] 1.4 Give products lines a shopper would recognise and supplier brands that
      are entirely invented

## 2. Twenty-six attributes, six of them safety-class

- [x] 2.1 Widen the attribute registry from twelve to twenty-six, six
      safety-class rather than two
- [x] 2.2 Confirm the widening makes escalation, mandatory review, the
      fail-closed confidence gate, withholding and per-channel redaction
      reachable outside the two allergen paths, with no new rule code
- [x] 2.3 Have both surfaces name the same attribute for one finding; verify via
      `tests/test_readiness.py::test_both_surfaces_name_the_same_attribute`

## 3. Fifteen correction kinds and seven new arcs

- [x] 3.1 Widen the correction kinds from seven to fifteen
- [x] 3.2 Keep the classifier's kind table and the generator's as one table;
      verify via `tests/test_golden.py::test_the_two_kind_tables_are_the_same_table`
- [x] 3.3 Offer only kinds that exist in the classifier prompt; verify via
      `tests/test_golden.py::test_every_kind_the_prompt_offers_is_a_kind_that_exists`
- [x] 3.4 Add seven arcs - a pack shrinking, a certificate lapsing, a country of
      origin moving, a withdrawal notice, an export-control classification, a
      fibre label revised, and cosmetics particulars amended
- [x] 3.5 Select arc targets from the assortment rather than naming them, and
      prefer undamaged ones so the finding is the arc's own
- [x] 3.6 Leave the original six arcs on their days, so the demonstration's
      spine does not move

## 4. A withdrawal is not a correction

- [x] 4.1 Add `sale_prohibited` as its own publish-time constraint in the safety
      gate, independent of confidence; verify via
      `tests/test_validator.py::test_the_sale_gate_is_part_of_the_publish_refusal`
- [x] 4.2 Block every listing the product reaches, not only the one that
      noticed; verify via
      `tests/test_validator.py::test_a_withdrawal_blocks_every_listing_the_product_reaches`
- [x] 4.3 Leave a product still permitted ungated; verify via
      `tests/test_validator.py::test_a_product_still_permitted_is_not_gated`
- [x] 4.4 Refuse to treat a withdrawal as something copy can fix; verify via
      `tests/test_validator.py::test_a_withdrawal_is_not_something_copy_can_fix`
- [x] 4.5 Add `sale_permitted` as a seventh deterministic readiness check, so a
      withdrawn product is blocked with no model reachable; verify via
      `tests/test_readiness.py::test_a_withdrawn_product_is_blocked_without_a_model`
- [x] 4.6 Raise nothing for a product still permitted; verify via
      `tests/test_readiness.py::test_a_product_still_permitted_raises_nothing`

## 5. Documents and precedence

- [x] 5.1 Add nine corpus documents, so every new finding cites something a
      reviewer can open
- [x] 5.2 Add `NOTICE` to the source precedence at 50, above label artwork,
      because artwork is the legal source for what a pack says and a notice is
      the legal source for whether it may be sold at all
- [x] 5.3 Make `NOTICE` the one source kind no supplier can issue

## 6. Two defects that were true by coincidence

- [x] 6.1 Record hero membership rather than pattern-matching an identifier
      prefix, which stopped being true when the background passed 199
- [x] 6.2 Read the allergen code map from the catalog in both the generator and
      the validation engine, so an assortment declaring celery cannot make the
      two disagree

## 7. Product 360

- [x] 7.1 Replace the single unlabelled panel with four labelled ones
- [x] 7.2 Put the verdict and every action in a sticky bar, rather than a
      primary action inside a panel header beside a truncating title
- [x] 7.3 Add a control that jumps to a section, and delete the two lines of the
      demo guide that existed to work around its absence
- [x] 7.4 Let the record table overflow rather than compress, and show
      superseded values inline rather than on hover
- [x] 7.5 Stop two scroll regions fighting over one viewport below the single
      breakpoint

## 8. The pack still holds

- [x] 8.1 Keep the pack byte-identical run to run for a seed
- [x] 8.2 Keep the untouched catalog validating with zero violations
