"""publishing-execution - the publishing pipeline, over MCP.

    python -m sc.mcp.publishing_execution

The only toolset in the estate that changes what a channel sees, which is the
reason the partition is worth having: an operator can hand out the other five
and withhold this one.

The safeguards travel with the tools rather than sitting in the caller.
``commit_plan`` refuses without a recorded APPROVE decision for that resolution,
and every mutating call carries an idempotency key, so a replayed call is a
no-op. Exposing a tool over MCP does not exempt it from either.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from sc.mcp._runtime import instrumented, serve
from sc.tools import planning

mcp = FastMCP("publishing-execution")


@mcp.tool()
def run_scenario(change_set: dict, as_of: str | None = None,
                 as_of_recorded: str | None = None) -> dict:
    """Validate one candidate resolution against the catalog and the channels.

    Deterministic: the same change set against the same state returns the same
    trace_hash, every time. as_of_recorded reads the record as it stood at an
    earlier instant, which is how a resolution is checked against what was known
    when it was proposed rather than against corrections that landed since.
    """
    return instrumented(planning.run_scenario)(
        change_set, as_of=as_of, as_of_recorded=as_of_recorded)


@mcp.tool()
def compare_scenarios(deltas: list[dict], weights: dict | None = None,
                      as_of: str | None = None) -> dict:
    """Validate several candidates and rank them, with the Pareto front.

    Safety is a pre-sort rather than a weight: a resolution with an open safety
    flag never outranks one without, whatever the weights say.
    """
    return instrumented(planning.compare_scenarios)(deltas, weights, as_of=as_of)


@mcp.tool()
def propose_change(incident_id: str, scenario_id: str, change_set: dict,
                   idempotency_key: str | None = None) -> dict:
    """Take soft publish locks on the (channel, product) pairs a candidate
    would republish.

    Conflicts surface here, at proposal time, rather than after a reviewer has
    approved something that cannot be published.
    """
    return instrumented(planning.propose_change)(
        incident_id, scenario_id, change_set,
        idempotency_key=idempotency_key)


@mcp.tool()
def reserve_publish(resource_id: str, bucket_date: str, incident_id: str,
                    scenario_id: str, status: str = "SOFT") -> dict:
    """Claim one (channel, product) for one publish batch date.

    A HARD claim is exclusive and the exclusivity is enforced by the database.
    The second one to arrive is refused - this is what makes two runs
    publishing different corrections of the same product to the same channel
    impossible rather than merely unlikely.
    """
    return instrumented(planning.reserve_publish)(
        resource_id, bucket_date, incident_id, scenario_id, status)


@mcp.tool()
def commit_plan(incident_id: str, scenario_id: str, actions: list[dict],
                actor: str = "publisher",
                idempotency_key: str | None = None) -> dict:
    """Publish an approved resolution.

    REFUSES without a recorded APPROVE decision for this resolution, if a
    source document has moved since it was validated, or if a safety or
    allergen declaration is still open on an affected listing. The checks live
    in the tool, not in the caller, so no client - MCP or otherwise - can route
    around them.
    """
    return instrumented(planning.commit_plan)(
        incident_id, scenario_id, actions, actor=actor,
        idempotency_key=idempotency_key)


@mcp.tool()
def rollback(incident_id: str, scenario_id: str, reason: str = "",
             idempotency_key: str | None = None) -> dict:
    """Reverse a publish: release its hard locks and mark its actions undone."""
    return instrumented(planning.rollback)(
        incident_id, scenario_id, reason=reason,
        idempotency_key=idempotency_key)


if __name__ == "__main__":
    serve(mcp, "publishing-execution")
