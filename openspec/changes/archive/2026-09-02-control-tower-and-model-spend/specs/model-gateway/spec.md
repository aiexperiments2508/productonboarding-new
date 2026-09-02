## MODIFIED Requirements

### Requirement: An unreachable gateway fails fast and is reported, never fatally

Every model call SHALL go through one egress so that selection, token accounting
and cost are captured in one place. Where the gateway cannot be reached, repeated
connection attempts SHALL be suppressed for a cooldown after a small number of
consecutive failures, so a run degrading gracefully does not also spend twenty
seconds per node paying connection timeouts. A caller SHALL receive a gateway
error it can catch and fall back from, carrying a message an operator can act on,
and a successful probe SHALL clear the suppression so starting the gateway
mid-session recovers without a restart.

**Every invocation through that egress SHALL append to the spend ledger**,
embedding calls included, and the append SHALL NOT be able to raise into the
call it is recording. Capturing accounting in one place is only true if the
place records every call; embedding spend that is not written down is a reindex
that costs real money and reports nothing.

**A breached spend cap SHALL raise the same gateway error an unreachable
gateway raises.** Every model step already has a deterministic fallback for
that error and the whole suite exercises those fallbacks, so a cap degrades the
system exactly as far as losing the network does - narrower answers, reported as
narrower - rather than introducing a failure mode nothing has a fallback for.

The cap MAY overshoot by up to one batch of concurrent calls, because
concurrent readers clear the check together before any of them records a token.
Closing that would mean serialising calls deliberately made concurrent, to
harden a control whose design is to be soft.

#### Scenario: A run against a closed port completes and says the gateway was unreachable

- **WHEN** a full correction run is executed with the gateway pinned to a closed
  port
- **THEN** the run completes and records an error naming the gateway as
  unreachable, rather than raising
- **AND** `tests/test_graph.py::test_the_correction_is_read_without_a_model`
  asserts the recorded error, and the graph, branch and replan suites all run
  under that pinning

#### Scenario: A reply that is not a JSON object is a gateway failure

- **WHEN** a model answers a structured request with an array or a string
- **THEN** it is refused as a gateway error rather than returned, so the caller
  routes into the deterministic fallback it already has instead of failing
  halfway down a node
- **AND** this is verified by inspection of the parse guard; no test covers it
  directly

#### Scenario: A breached cap degrades the run rather than failing it

- **WHEN** a spend cap is breached and a model step runs
- **THEN** the step receives the same error it receives from an unreachable
  gateway and takes its existing fallback
- **AND** `tests/test_tower.py::test_a_breached_cap_refuses_the_way_an_unreachable_gateway_does`
  asserts it

#### Scenario: Embedding spend is recorded like any other call

- **WHEN** an embedding request leaves the egress
- **THEN** a ledger row is written for it
- **AND** `tests/test_tower.py::test_spend_is_attributable_to_a_feed_and_a_surface`
  asserts the attribution the row carries
