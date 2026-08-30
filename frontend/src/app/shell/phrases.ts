/* What the graph is doing, in words.
 *
 * Lifted out of the status strip because two surfaces now narrate the same run:
 * the strip, which is what you read while looking at something else, and the
 * run stage, which is what a room reads while the loop is working. One copy of
 * the vocabulary, so the footer and the stage can never say different things
 * about the same node.
 *
 * Both maps are read-throughs, not registries: the graph names its own nodes
 * and the run names its own status, and anything unrecognised is shown as it
 * arrived with the underscores opened up. Adding a node to the graph costs a
 * phrase here, never a broken strip. The raw name stays in the tooltip, because
 * that is the string a reviewer greps the trace for.
 */

export const NODE_PHRASE: Record<string, string> = {
  starting: "starting",
  monitor: "watching the feed",
  extract: "reading the document",
  scope_case: "settling which correction this run decides",
  triage: "sizing the blast radius",
  resolve_scope: "settling which variants it names",
  plan_candidates: "drafting resolutions",
  validate_one: "validating a resolution",
  rank: "ranking resolutions",
  propagate: "propagating the corrected values",
  scan_claims: "checking the claims",
  regenerate: "rewriting the copy",
  enrich: "filling the gaps",
  validate_final: "re-validating the whole change set",
  recommend: "writing the recommendation",
  request_approval: "waiting on review",
  publish: "republishing",
  ack_and_park: "parking the correction",
  close: "closing",
  apply_precedent: "applying the precedent",
  supplier_clarification: "drafting a supplier question",
  blocked_review: "re-reading the channel rules",
  verify_publish: "verifying the republish",
};

export const STATUS_PHRASE: Record<string, string> = {
  MONITORING: "watching the feed",
  QUIET: "nothing material",
  EXTRACTING: "reading the document",
  CASE_SCOPED: "scoped to one correction case",
  TRIAGED: "blast radius sized",
  SCOPED: "scope settled",
  PRECEDENT: "precedent applied",
  CLARIFICATION_REQUESTED: "waiting on the supplier",
  PLANNED: "resolutions drafted",
  PROPAGATED: "changes propagated",
  NOTHING_TO_PROPAGATE: "nothing to propagate",
  CLAIMS_SCANNED: "claims checked",
  REGENERATED: "copy rewritten",
  ENRICHED: "gaps filled",
  VALIDATED: "validated",
  RANKED: "resolutions ranked",
  NO_OPTIONS: "no publishable resolution",
  NOTHING_PUBLISHABLE: "nothing publishable",
  AWAITING_APPROVAL: "waiting on review",
  REPLANNING: "revising the resolution",
  REPLANNING_AFTER_CONFLICT: "revising after a publish conflict",
  CONFLICT_UNRESOLVED: "publish conflict unresolved",
  PUBLISH_REFUSED: "republish refused",
  PUBLISHED: "republished",
  PARKED: "parked",
};

export const readable = (raw: string, table: Record<string, string>) =>
  table[raw] ?? raw.toLowerCase().replace(/_/g, " ");
