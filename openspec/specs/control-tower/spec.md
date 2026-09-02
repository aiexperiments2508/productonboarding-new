# control-tower Specification

## Purpose

One surface that answers a question about the estate rather than about one
thing: where every feed's rows have got to, what arrived over a window, and how
well the whole loop is working.

It is a join and only a join. Every verdict, gate outcome, stage, lane and cost
is read from the module that already owns it. A dashboard that reached its own
conclusion would be a second answer to "is this ready", and the one on the big
screen is the one people would quote.

## Requirements

### Requirement: Nothing on the tower decides anything, and nothing is stored

Every figure the control tower reports SHALL be derived on read from a module
that already owns the decision behind it. The tower SHALL NOT weigh, score, or
reach a verdict of its own, and SHALL NOT hold a snapshot table or a stored
rollup.

A stored figure is a second account of the truth, and the first thing it
disagrees about is whatever somebody just changed.

Reading the tower SHALL record no fact and SHALL move no ingestion cursor.

#### Scenario: Reading the tower changes nothing

- **WHEN** every tower surface is read
- **THEN** no fact is recorded and no cursor moves
- **AND** `tests/test_tower.py::test_reading_the_tower_records_no_fact_and_moves_no_cursor`
  asserts it

### Requirement: A row's position is one of seven states, decided by a pure function

A feed's row SHALL be placed in exactly one of seven states from received to on
sale. The placement SHALL be a pure function of whether the record has ingested
the feed, whether the onboarding gate passed the product, its readiness
verdict, its lifecycle lane and the count of decisions open against it - with
no clock and no database read of its own.

Every state SHALL be reachable. A state no combination of inputs can produce is
a name on a screen with nothing behind it.

#### Scenario: The placement is pure

- **WHEN** the placement function is called with the same inputs twice
- **THEN** it returns the same state, having read no clock and no database
- **AND** `tests/test_tower.py::test_state_of_is_pure` asserts it

#### Scenario: Every state has a path to it

- **WHEN** the states are enumerated
- **THEN** each is produced by some combination of inputs
- **AND** `tests/test_tower.py::test_every_state_is_reachable` asserts it

### Requirement: The precedence between states is fixed and argued

Where more than one signal is true at once, the placement SHALL resolve them in
this order: not yet ingested outranks everything; stopped outranks downstream;
downstream outranks waiting on a person.

A product the record has not taken in has no verdict worth reporting, and
showing the last assessment beside a feed that has just landed would date-stamp
the screen with an answer about a different version of the record. A product
that is on sale *and* has just been refused by the gate is the single row
somebody has to look at, and filing it under "on sale" would hide it.

#### Scenario: An uningested feed reports no verdict

- **WHEN** a feed's events are behind the ingestion watermark
- **THEN** every row reads as received, whatever the last assessment said
- **AND** `tests/test_tower.py::test_not_ingested_outranks_every_other_signal`
  asserts it

#### Scenario: A stopped row that is also on sale reads as stopped

- **WHEN** a product on sale is refused by the gate
- **THEN** it is placed as stopped
- **AND** `tests/test_tower.py::test_a_stopped_row_that_is_also_on_sale_reads_as_stopped`
  asserts it

### Requirement: Stopped means the gate or a blocking finding, and nothing else

A row SHALL be reported as stopped only where the onboarding gate refused it or
a blocking finding stands against it - the two things a supplier has to fix. A
record merely returned to source, with a gap the gate let through, SHALL be
reported as in progress.

That record is mid-flight: the gate passed it, nothing is wrong with it that a
value would not fix, and the next thing that happens is the system trying to
fill the gap from what it already holds. Filing it as a failure would count the
entire correction lane as one.

A row waiting on a person SHALL NOT be counted as cleared. It has not got
through; it has stopped somewhere politer.

#### Scenario: A gap the gate let through is not blocked

- **WHEN** a record is returned to source with no gate refusal and no blocking
  finding
- **THEN** it is reported as in progress rather than as blocked
- **AND** `tests/test_tower.py::test_a_gap_the_gate_let_through_is_not_reported_as_blocked`
  asserts it

#### Scenario: A row awaiting a decision has not cleared

- **WHEN** a row has an undecided proposal against it
- **THEN** it is not counted among the rows that got through
- **AND** `tests/test_tower.py::test_a_row_waiting_on_a_person_has_not_cleared`
  asserts it

### Requirement: Position is exclusive; what the AI did is carried beside it

A row SHALL hold exactly one state, and the counts of values written unattended
and values settled by a person SHALL be reported alongside that state rather
than as states of their own.

"The AI corrected this" is a fact about the past that does not stop being true
when the product moves on. Filing every row under exactly one heading would
either lose the unattended fills into the cleared count, where nobody would see
them, or report a row as corrected when what it now *is* is on sale.

#### Scenario: A corrected row that is on sale is counted in both readings

- **WHEN** a row was filled unattended and has since gone on sale
- **THEN** it is placed on sale and is also counted among the rows the system
  corrected

### Requirement: The grain is the row a supplier sent, and the payload says so

The tower SHALL report at the grain of the row a supplier sent - a variant - and
SHALL declare that grain in its own response.

The lifecycle board places a *product*, and a product is as blocked as its worst
variant. A pack whose 500ml is fit to sell and whose 1L is not is one product
there and two rows here, one cleared and one not. Both answers are correct and
they will disagree, so each surface names the question it answered.

The variant's lane SHALL be computed from the same lane function and the same
signals the product board uses - the same rule at a finer grain, never a second
set of rules.

#### Scenario: A feed places every row it named

- **WHEN** a feed is read
- **THEN** every entity the submission named that the catalog holds is placed
  in a state
- **AND** `tests/test_tower.py::test_a_feed_places_every_row_it_named` asserts it

#### Scenario: A feed that does not exist is not invented

- **WHEN** an unknown feed identifier is read
- **THEN** nothing is returned rather than an empty feed
- **AND** `tests/test_tower.py::test_an_unknown_feed_is_not_invented` asserts it

### Requirement: A feed is a submission, not a new object

The arrival register SHALL report one row per submission, using the
submission's own identifier, supplier, carrier, timestamp, events and entities.
It SHALL NOT mint a second identifier for a feed.

An image feed SHALL NOT be modelled as a separate kind of arrival. What
distinguishes it is the carrier and the payload type, both of which are already
recorded, so the register reports the media-event count and the carrying system
and lets a caller filter on either - rather than inventing a second feed type
the estate would immediately contradict.

The register and the per-feed view SHALL agree about the same feed.

#### Scenario: Two views of one feed agree

- **WHEN** the same feed is read through the register and through the per-feed
  view
- **THEN** the counts agree
- **AND** `tests/test_tower.py::test_the_feed_and_the_register_agree_on_the_same_feed`
  asserts it

### Requirement: Windows filter the simulated clock and durations measure the real one

Every window SHALL filter timestamps that run on the replay clock. Every
duration SHALL be measured between two timestamps that run on the real clock,
and the response SHALL name which clock its durations were measured on.

A duration whose ends do not subtract, or which subtracts negative, SHALL be
reported as absent rather than as a figure. A negative duration on a dashboard
is worse than a missing one, and subtracting across the two clocks would report
a feed that arrived in simulated August and published this morning as having
taken four weeks.

A window outside the recorded horizon SHALL be empty rather than everything.

#### Scenario: The window filters the simulated clock

- **WHEN** a window is applied
- **THEN** it selects on the replay clock, not on wall-clock time
- **AND** `tests/test_tower.py::test_the_window_filters_the_simulated_clock_not_the_real_one`
  asserts it

#### Scenario: A window outside the horizon is empty

- **WHEN** a window falls outside the recorded flight
- **THEN** it returns nothing rather than everything
- **AND** `tests/test_tower.py::test_a_window_outside_the_horizon_is_empty_rather_than_everything`
  asserts it

#### Scenario: A duration across two clocks is refused

- **WHEN** a duration would be measured with one end on each clock
- **THEN** it is reported as absent
- **AND** `tests/test_tower.py::test_a_duration_across_two_clocks_is_refused`
  and `::test_durations_are_measured_on_the_real_clock` assert it

### Requirement: A rate over nothing is absent, and a truncated window says so

Every rate SHALL be reported as absent when its denominator is empty, and SHALL
NOT be reported as zero. A window whose result was truncated by a limit SHALL
say so, so that every figure below it reads as a sample.

Reporting a 0% compliance pass rate for a window in which nothing was assessed
is the kind of figure that gets screenshotted.

The flag saying that the reading checks did not complete SHALL survive
aggregation, so a narrower count is never presented as a cleaner one.

#### Scenario: An empty denominator yields no rate

- **WHEN** a rate is computed over an empty window
- **THEN** it is absent rather than zero
- **AND** `tests/test_tower.py::test_a_rate_over_nothing_is_none_rather_than_zero`
  asserts it

#### Scenario: A truncated window declares itself

- **WHEN** a window is cut short by its limit
- **THEN** the response says so
- **AND** `tests/test_tower.py::test_a_truncated_window_says_so` asserts it

#### Scenario: The incomplete-checks flag survives aggregation

- **WHEN** feeds assessed without a model are aggregated
- **THEN** the aggregate reports that the checks did not complete
- **AND** `tests/test_tower.py::test_checks_complete_survives_aggregation`
  asserts it

### Requirement: The KPIs count what the flow placed

Every quality figure SHALL be counted from the states the flow already placed,
rather than recomputed from the record. A figure the tower derived
independently could disagree with the screen beside it about the same rows.

#### Scenario: The KPI totals match the placement

- **WHEN** the KPIs are computed over a window
- **THEN** their state counts equal the flow's own
- **AND** `tests/test_tower.py::test_the_kpis_count_the_states_the_flow_placed`
  asserts it

### Requirement: A persona is a lens and says so in its own contract

The tower SHALL offer named personas, each declaring the tab it opens on and
the figures it leads with, declared once so that the API and the console read
one list.

A persona SHALL change only which figures are shown. It SHALL NOT restrict
which figures may be requested, and the persona surface SHALL state that it
enforces nothing.

There is no identity provider in this system. What an action records is the
name whoever took it typed - attribution, not authentication. A picker that
looked like access control and was not would be worse than no picker, because
somebody would build a process on it.

Every persona's declared tiles SHALL name figures the KPI surface actually
returns, and every persona SHALL open on a tab that exists.

#### Scenario: The lens declares that it enforces nothing

- **WHEN** the persona surface is read
- **THEN** it states that no persona restricts access
- **AND** `tests/test_tower.py::test_the_persona_surface_states_that_it_enforces_nothing`
  asserts it

#### Scenario: No persona points at a figure or a tab that does not exist

- **WHEN** the personas are enumerated
- **THEN** every tile names a KPI the surface returns and every default tab
  exists
- **AND** `tests/test_tower.py::test_every_persona_tile_is_a_kpi_that_exists`
  and `::test_every_persona_opens_on_a_tab_that_exists` assert both
