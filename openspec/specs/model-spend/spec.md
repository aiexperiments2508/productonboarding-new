# model-spend Specification

## Purpose

What the models cost, what the cache saved, and the two caps that stop
unattended spend.

The whole design is one distinction: **a cache and a ledger want opposite
shapes.** A cache is keyed by the question, so asking it twice leaves one row. A
ledger is keyed by the invocation, so asking twice leaves two. One table cannot
be both, and the attempt produces a cost figure that answers a question nobody
asked.

## Requirements

### Requirement: The ledger is append-only and separate from the cache

Model invocations SHALL be recorded in an append-only ledger holding one row per
invocation, distinct from the response cache. Each row SHALL carry the model,
the surface that called it, the run and the feed it was working, its token
counts, its cost, whether it was priced, whether it was served from cache, and
both a real and a simulated timestamp.

The cache's own key is the question asked, so its timestamp is the first time
that prompt was ever seen, there is one row per distinct prompt rather than per
call, and no column names the feed. A window over it cannot answer "what did
July cost" and an attribution over it cannot answer "which archive caused this".

The ledger SHALL be written at every choke point through which a model is
invoked, embedding included. Embedding spend that is not recorded is a reindex
that costs real money and reports nothing.

The append SHALL NOT be on any read path and SHALL NOT be able to raise into a
model call. The call has already happened; a ledger that could take the gateway
down would be a worse trade than no ledger.

#### Scenario: Two identical calls leave two ledger rows and one cache row

- **WHEN** the same prompt is issued twice
- **THEN** the ledger holds two rows and the cache holds one
- **AND** `tests/test_tower.py::test_two_identical_calls_leave_two_ledger_rows_and_one_cache_row`
  asserts it

#### Scenario: Spend is attributable to the feed and the surface that caused it

- **WHEN** a model is invoked while working a feed
- **THEN** the ledger row names both the feed and the calling surface
- **AND** `tests/test_tower.py::test_spend_is_attributable_to_a_feed_and_a_surface`
  asserts it

### Requirement: A cache hit is recorded, not skipped

A call served from the response cache SHALL be written to the ledger with its
token counts intact and no cost of its own, marked as served from cache.

Spend and spend avoided SHALL therefore be two sums over one table rather than
one number with a footnote. What a cached call would have cost SHALL be read
off the cache's own recorded price and SHALL NOT be re-estimated.

Summing the cost column can then never overstate spend, and the honest reading
and the flattering one are the same reading - which is the only good reason to
prefer this shape.

#### Scenario: A hit counts as avoided and never as spend

- **WHEN** a call is served from the cache
- **THEN** its tokens count towards avoided spend, its cost towards neither,
  and the money it saved is read from the cached record
- **AND** `tests/test_tower.py::test_a_cache_hit_is_recorded_as_avoided_and_never_as_spend`
  asserts it

### Requirement: A cost of zero is not a claim about the price

Cost SHALL be taken from the gateway's own reported figure. Where the gateway
returns none - a model its price map does not recognise - the row SHALL be
marked unpriced, and a window SHALL report how many of its calls could not be
priced rather than reporting a confident zero.

#### Scenario: An unpriced call is not reported as free

- **WHEN** a window contains calls the gateway could not price
- **THEN** the window reports them as unpriced rather than as costing nothing
- **AND** `tests/test_tower.py::test_an_unpriced_call_is_not_reported_as_free`
  asserts it

### Requirement: The ledger may be sliced only by a closed set of groupings

A caller SHALL be able to group spend by a fixed set of dimensions, and a
grouping outside that set SHALL be refused rather than substituted.

The grouping names a column in a query. An open set is an injection.

#### Scenario: An unknown grouping is refused

- **WHEN** a grouping outside the set is requested
- **THEN** it is refused rather than silently replaced with a default
- **AND** `tests/test_tower.py::test_an_unknown_grouping_is_refused_rather_than_silently_substituted`
  asserts it

### Requirement: Spend is capped in two currencies, and either cap trips alone

An operator SHALL be able to set a cap in money and a cap in tokens, and either
SHALL be able to stop further model calls on its own. A refusal SHALL name which
cap tripped.

A money cap on a gateway that prices nothing is a control that can never fire,
which is precisely the configuration under which somebody would most want one.
Tokens are always counted. A refusal that did not say which cap tripped would
send an operator to raise the wrong number.

#### Scenario: A token cap fires where a money cap cannot

- **WHEN** an unpriced workload runs against both caps
- **THEN** the token cap trips and the refusal names it
- **AND** `tests/test_tower.py::test_a_token_cap_fires_where_a_money_cap_cannot`
  asserts it

### Requirement: A breached cap refuses the way an unreachable gateway refuses

Past a cap, the gateway SHALL raise the same error it raises when it cannot be
reached.

Every model step in this system already has a deterministic fallback for that
error, and the whole test suite exercises those fallbacks. Reusing the error
means a breached cap degrades the system exactly as far as losing the network
does - narrower answers, and an assessment that says its reading checks did not
complete - rather than producing a new failure mode nobody has a fallback for.

#### Scenario: Work continues with narrower answers past the cap

- **WHEN** a cap is breached and a model step runs
- **THEN** it takes the same fallback it takes when the gateway is unreachable,
  and the assessment reports that its checks did not complete
- **AND** `tests/test_tower.py::test_a_breached_cap_refuses_the_way_an_unreachable_gateway_does`
  asserts it

### Requirement: The meter starts when the cap is set

A cap SHALL be measured against spend recorded after it was set, anchored to a
ledger position rather than to a timestamp.

An unscoped meter would make a newly set cap read as instantly breached against
spend that had already happened. A timestamp anchor is not enough: two rows
written in the same second can carry the same string, so a call made moments
before the cap was set would count against it.

Raising a cap SHALL restart its meter. Where no cap is set, checking SHALL cost
nothing.

#### Scenario: A new cap does not count what came before it

- **WHEN** a cap is set after spend has already been recorded
- **THEN** the earlier spend does not count against it
- **AND** `tests/test_tower.py::test_the_meter_starts_when_the_cap_is_set` and
  `::test_raising_a_cap_restarts_its_meter` assert it

#### Scenario: No cap costs nothing to check

- **WHEN** no cap is set
- **THEN** the check performs no query
- **AND** `tests/test_tower.py::test_no_cap_costs_nothing_to_check` asserts it

### Requirement: Setting a cap demands a name and is audited

Setting or changing a cap SHALL require a named actor and SHALL be written to
the audit ledger with what it was and what it became.

Moving a cap changes what the system will do unattended, which is a decision
with a person behind it. It stays on a surface where the name is demanded, and
is deliberately not offered as an agent-callable tool.

#### Scenario: The cap demands a name and writes it down

- **WHEN** a cap is set
- **THEN** the actor is required and the change reaches the ledger
- **AND** `tests/test_tower.py::test_the_cap_demands_a_name_and_writes_it_to_the_ledger`
  asserts it
