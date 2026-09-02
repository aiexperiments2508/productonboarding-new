## ADDED Requirements

### Requirement: A shared endpoint owns its session for the session's whole life

The endpoint a connected application reaches the platform through SHALL own its
transport session in a task of its own, for the life of the session. It SHALL
NOT open the session inside a request and leave it belonging to that request.

The transport runs its reader in the task that opened it. A session opened
inside a request therefore stops being read the moment that request finishes,
and the next caller gets a session whose replies nobody is reading - it waits
for ever and holds the endpoint while waiting, so every later call queues behind
a call that will never finish. Nothing raises; the page shows a spinner.

Concurrent callers SHALL all be answered. A call SHALL be shielded from its
caller's cancellation, so a browser that navigated away or a request that timed
out takes nothing down with it. A call that does not answer within a bounded
time SHALL be abandoned and its session reopened, so an endpoint wedged by some
other cause recovers without the process being restarted.

#### Scenario: Two calls at once do not wedge the endpoint

- **WHEN** two calls to one endpoint overlap
- **THEN** both are answered and the endpoint remains usable
- **AND** `tests/test_app_boundary.py::test_two_calls_at_once_do_not_wedge_an_endpoint`
  asserts it

#### Scenario: A caller that gives up leaves the endpoint usable

- **WHEN** a caller is cancelled mid-call
- **THEN** the session survives and the next call is answered
- **AND** `tests/test_app_boundary.py::test_a_caller_that_gives_up_does_not_take_the_session_with_it`
  asserts it

These two tests pin what is assertable in-process. They do **not** reproduce the
original deadlock, which needs the real transport's task affinity and therefore
a live platform, and they say so - a test named for a bug it cannot reproduce
reads as coverage that is not there.
