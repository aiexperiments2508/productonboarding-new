/* Typed client for the backend.
 *
 * Mirrors sc/contracts.py. When that changes, this changes - they are the
 * day-0 contract the workstreams agreed on.
 */

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = await res.text();
    try {
      detail = JSON.stringify(JSON.parse(detail).detail ?? detail);
    } catch {
      /* keep the raw body */
    }
    throw new Error(`${res.status} ${detail.slice(0, 300)}`);
  }
  return res.json() as Promise<T>;
}

const get = <T,>(p: string) => req<T>(p);
const post = <T,>(p: string, body?: unknown) =>
  req<T>(p, { method: "POST", body: JSON.stringify(body ?? {}) });
const del = <T,>(p: string) => req<T>(p, { method: "DELETE" });

/* --- provenance --------------------------------------------------------- */

export type ProvenanceKind =
  | "RECORDED" | "INFERRED" | "DECIDED" | "SIMULATED" | "COMMITTED";

export interface Provenance {
  kind: ProvenanceKind;
  source_id?: string | null;
  confidence?: number | null;
  agent?: string | null;
  model?: string | null;
  run_id?: string | null;
  note?: string | null;
}

/** Where a value came from. A proposed change without one is a violation, not
 *  a stylistic lapse, so the UI renders its absence rather than hiding it. */
export interface SourceRef {
  doc_id: string;
  version: string;
  excerpt: string;
  chunk_id?: string | null;
}

/* --- catalog ------------------------------------------------------------ */

export type CatalogNodeKind =
  | "SYSTEM" | "SUPPLIER" | "PRODUCT" | "VARIANT" | "CHANNEL";

/** One box on the map.
 *
 *  Carries no position. A tier whose membership changes while the application
 *  is running cannot be laid out from coordinates written at generation time,
 *  so the map computes each box's place from its tier and that tier's live
 *  membership. */
export interface CatalogNode {
  id: string; kind: CatalogNodeKind; name: string; group: string;
  /** Systems only: whether the connection is still answering. */
  state?: string;
  transport?: string;
  tools?: number;
  conforms?: boolean | null;
  regulated: boolean; single_source: boolean;
}

export type AttributeDtype = "int" | "float" | "str" | "bool" | "list[str]";

export interface AttributeDef {
  path: string; label: string; dtype: AttributeDtype; unit: string | null;
  /** Drives the fail-closed gate: a low-confidence inference here withholds
   *  the listing instead of degrading it. */
  safety_class: boolean;
  ordered: boolean;
  required_for: string[];
  applies_to: string[];
}

export interface Product {
  id: string; name: string; category: string; supplier: string;
  regulated: boolean;
}

export interface Variant {
  id: string; product_id: string; name: string; is_base: boolean;
}

export type ChannelKind = "WEB" | "MARKETPLACE" | "PRINT" | "SHELF" | "SEARCH";

export interface Channel {
  id: string; name: string; kind: ChannelKind; taxonomy: string;
  /** Days of frozen content before a print run. A correction landing inside
   *  the window needs a reprint decision before it can publish. */
  freeze_days: number;
  attribute_map: Record<string, string>;
  category_map: Record<string, string>;
}

export type ChannelRuleKind =
  | "REQUIRED" | "DTYPE" | "MAX_LEN" | "FORMAT" | "ENUM"
  | "ORDERED_MATCH" | "CATEGORY_MAPPED";

export interface ChannelRule {
  id: string; channel_id: string; field: string; kind: ChannelRuleKind;
  attribute_path: string | null; value: unknown;
  severity: "HARD" | "SOFT"; detail: string;
}

export type ListingStatus = "LIVE" | "PREPARED" | "WITHHELD" | "REJECTED";

/** One variant on one channel - the unit the blast radius is counted in. */
export interface Listing {
  id: string; variant_id: string; channel_id: string;
  status: ListingStatus; published_version: string;
}

/** A derived output: a title, a bullet, a feed row, a shelf label.
 *
 *  `derived_from` carries qualified references ("VAR-01B:specs.power_w"). It
 *  is the lineage that makes propagation deterministic - no model decides
 *  what a correction touches. */
export interface ContentAsset {
  id: string; listing_id: string; field: string; text: string;
  derived_from: string[]; claims_used: string[];
  built_at_version: string; regulated: boolean;
}

export type SourceDocKind =
  | "SPEC_SHEET" | "LABEL_ARTWORK" | "PORTAL_FEED" | "SPREADSHEET"
  | "EMAIL" | "CERTIFICATE";

/** A supplier document, versioned. `precedence` is the policy order used to
 *  settle contradictions between sources - higher wins - so a conflict is
 *  resolved by a published rule rather than by a model's opinion. */
export interface SourceDoc {
  id: string; supplier: string; kind: SourceDocKind; version: string;
  title: string; received_at: string;
  status: "ACTIVE" | "SUPERSEDED" | "WITHDRAWN";
  precedence: number; body_path: string | null;
}

/** The factory map plus whatever corrections are in force at the instant.
 *
 * `as_of` moves along valid time, `as_of_recorded` along recorded time; the
 * pair is what lets the map show what was believed when the copy was written
 * as well as what is true now. */
/** One derived edge from the server's map.
 *
 *  Most of the map's edges are rebuilt client-side from products, variants and
 *  listings, because the client already holds all three. The systems tier is
 *  the exception: which system fed which source is a fact about what has
 *  arrived, which only the server knows. */
export interface CatalogEdge {
  from: string;
  to: string;
  relation: string;
  listing?: string;
  status?: string;
}

export interface CatalogState {
  as_of: string;
  as_of_recorded: string | null;
  nodes: CatalogNode[];
  edges?: CatalogEdge[];
  products: Product[];
  variants: Variant[];
  channels: Channel[];
  rules: ChannelRule[];
  listings: Listing[];
  attributes: AttributeDef[];
  horizon_start: string;
  horizon_days: number;
  correction: {
    /** "VAR-01B:specs.power_w" -> the value now in force. */
    attributes: Record<string, unknown>;
    /** Listing id -> status, for anything no longer PREPARED. */
    listings: Record<string, string>;
    /** Documents superseded or withdrawn as of this instant. */
    docs: string[];
    assets_stale: number;
    summary: string[];
  };
}

/* --- events ------------------------------------------------------------- */

export type EventType =
  | "SUPPLIER_FEED" | "SPEC_DOC" | "CHANNEL_STATUS" | "CATALOG_UPDATE"
  | "PUBLISH_TELEMETRY" | "COMMS";

export interface SCEvent {
  id: string; seq: number; ts: string; type: EventType; source: string;
  payload: Record<string, unknown>; body?: string | null;
}

export interface ReplayState {
  running: boolean; speed: number; cursor_seq: number;
  total_events: number; sim_clock: string | null;
}

/** One bitemporal fact.
 *
 * Two time axes, and they answer different questions. `valid_from`/`valid_to`
 * is when the fact is true *in the world*; `recorded_at` is when we learned
 * it. A recommendation is reproducible only against what was known at the time
 * it was made, which is why both are kept and why `supersedes_id` chains
 * corrections rather than overwriting them.
 */
export interface Fact {
  id: string;
  entity_type: string;
  entity_id: string;
  attr: string;
  value: unknown;
  valid_from: string;
  valid_to: string | null;
  recorded_at: string;
  supersedes_id: string | null;
  provenance: Provenance;
}

/* --- correction signals and impact -------------------------------------- */

export type CorrectionKind =
  | "SPEC_CORRECTION" | "ALLERGEN_CHANGE" | "INGREDIENT_CHANGE"
  | "SOURCE_CONFLICT" | "CHANNEL_REJECTION" | "DOC_WITHDRAWN" | "DATA_GAP";

/** A detected correction, structured or read out of prose.
 *
 *  `provenance.kind` is RECORDED off a feed and INFERRED when a model read it
 *  from a document - the badge differs, and only the latter is subject to the
 *  safety gate. `resolves_issue` marks a notice that *clears* an earlier one
 *  rather than revising a value. */
export interface CorrectionSignal {
  id: string;
  kind: CorrectionKind;
  detected_at: string;
  entities: string[];
  attribute_paths: string[];
  old_value?: unknown;
  new_value?: unknown;
  unit?: string | null;
  window_start?: string | null;
  window_end?: string | null;
  summary: string;
  source_event_id?: string | null;
  source?: SourceRef | null;
  resolves_issue: boolean;
  provisional: boolean;
  provenance: Provenance;
}

/** The id a case carries when nothing attributed its corrections to a product.
 *  Not a product that happens to be missing - a correction nobody can decide
 *  about, which is a governance signal rather than a queue item. */
export const UNSCOPED_CASE = "UNSCOPED";

/** One open correction case: every signal in force on one product.
 *
 *  Keyed by product because that is the unit a reviewer commits - the publish
 *  lock is `channel_id:product_id` - and because a disagreement between two
 *  supplier documents about one product has to stay one case rather than split
 *  down the document seam. `case_id` is the product id, or `UNSCOPED_CASE`.
 */
export interface OpenCase {
  case_id: string;
  /** The product id, or "" when the corrections named no product. */
  product: string;
  title: string;
  signal_ids: string[];
  signals: CorrectionSignal[];
  /** Every document the case stands on - the source of each signal, plus any
   *  document named as an entity, which is how a source conflict cites both
   *  sides of itself. */
  documents: string[];
  attribute_paths: string[];
  safety: boolean;
  regulated: boolean;
  first_detected: string;
  /** How bad the case looks before triage measures it. A hint, never a verdict. */
  severity_hint: string;
}

/** A case as the graph checkpoints it: the same shape without the signal
 *  bodies, which the run already carries in `signals`. */
export type CaseSummary = Omit<OpenCase, "signals">;

/** One hop from corrected source to impacted output. */
export interface CausalLink {
  from_ref: string; to_ref: string; relation: string;
  explanation: string; evidence: string[];
}

/** The blast radius, counted in the units a reviewer cares about. */
export interface AffectedScope {
  products: string[];
  variants: string[];
  /** Qualified attribute references, "VAR-01B:specs.power_w". */
  attributes: string[];
  assets: string[];
  listings: string[];
  channels: string[];
}

/* --- change sets -------------------------------------------------------- */

export type ScopeLevel = "BASE" | "VARIANT" | "ALL";

/** One reading of who a correction applies to. Candidates are competing
 *  answers to this question; the deterministic validator decides between
 *  them. */
export interface ChangeScope {
  level: ScopeLevel;
  entities: string[];
  confidence: number;
  rationale: string;
  evidence: string[];
}

export type ActionKind =
  | "SET_ATTRIBUTE" | "REGENERATE_COPY" | "REMAP_TAXONOMY" | "SET_FACET"
  | "WITHHOLD_CHANNEL" | "REQUEST_SUPPLIER_INPUT";

export interface ActionBase {
  id: string;
  rationale?: string;
  /** The publish lock this action needs; the reservation ledger reads it. */
  resource_id?: string | null;
  bucket_date?: string | null;
  qty?: number;
  source?: SourceRef | null;
}

export interface SetAttributeAction extends ActionBase {
  kind: "SET_ATTRIBUTE";
  entity_id: string;
  attribute_path: string;
  old_value?: unknown;
  new_value?: unknown;
  unit?: string | null;
  confidence?: number;
}

export interface RegenerateCopyAction extends ActionBase {
  kind: "REGENERATE_COPY";
  listing_id: string;
  asset_id: string;
  field: string;
  old_excerpt?: string;
  proposed_text?: string;
  reason?: string;
}

export interface RemapTaxonomyAction extends ActionBase {
  kind: "REMAP_TAXONOMY";
  listing_id: string;
  from_node: string;
  to_node: string;
}

export interface SetFacetAction extends ActionBase {
  kind: "SET_FACET";
  channel_id: string;
  facet: string;
  op: "ADD" | "REMOVE";
  reason?: string;
}

/** The fail-closed block, recorded as an act rather than as an absence: it
 *  appears in the diff, needs approval, and lands in the audit trail. */
export interface WithholdChannelAction extends ActionBase {
  kind: "WITHHOLD_CHANNEL";
  listing_id: string;
  channel_id: string;
  reason?: string;
}

/** Ask a human to ask the supplier. Never executed by the system. */
export interface RequestSupplierInputAction extends ActionBase {
  kind: "REQUEST_SUPPLIER_INPUT";
  supplier: string;
  doc_ref?: string;
  question?: string;
}

export type Action =
  | SetAttributeAction
  | RegenerateCopyAction
  | RemapTaxonomyAction
  | SetFacetAction
  | WithholdChannelAction
  | RequestSupplierInputAction;

/** A candidate resolution of one correction. The only thing the validator
 *  accepts and the only thing a reviewer approves. */
export interface ChangeSet {
  id: string;
  scope: ChangeScope;
  actions: Action[];
}

/* --- validation --------------------------------------------------------- */

export type ViolationSeverity = "HARD" | "SOFT";

/** A rule breach, always naming what bound. A blocked channel is shown with
 *  its reason, never silently dropped. */
export interface Violation {
  constraint: string;
  severity: ViolationSeverity;
  entity_id: string;
  channel_id: string | null;
  bucket_date: string | null;
  required: number;
  available: number;
  detail: string;
}

/** What a resolution costs, in figures the validator computes. No model
 *  produces any of these. */
export interface KPIs {
  fields_affected: number;
  assets_stale: number;
  channels_blocked: number;
  listings_ready_pct: number;
  completeness_pct: number;
  safety_flags: number;
  republish_steps: number;
}

export interface SimResult {
  delta_id: string;
  feasible: boolean;
  violations: Violation[];
  kpis: KPIs;
  /** Two validations of the same change set against the same catalog must
   *  agree here. It is the determinism claim, made checkable. */
  trace_hash: string;
  runtime_ms: number;
}

/** A candidate resolution plus its verdict, as the contracts define it. */
export interface Scenario {
  id: string;
  incident_id: string;
  name: string;
  summary: string;
  delta: ChangeSet;
  sim: SimResult | null;
  score: number | null;
  pareto_optimal: boolean;
  /** Narrative only - never the source of any number. */
  rationale: string;
  citations: string[];
  provenance: Provenance;
}

/** The flatter shape `planning.compare_scenarios` puts on the wire: one
 *  validated candidate with its verdict inlined, which is what the ranked
 *  table renders a row from. */
export interface SimScenario {
  scenario_id: string; name: string; summary: string;
  delta: ChangeSet; kpis: KPIs; feasible: boolean;
  violations: Violation[]; trace_hash: string; runtime_ms: number;
  score?: number; pareto_optimal?: boolean;
}

/* --- recommendation, approval, audit ------------------------------------ */

export interface Citation {
  chunk_id: string; doc_id: string; doc_type: string; title: string;
  heading: string; source: string; score: number; excerpt: string;
}

/** One row of the reviewer's diff: source -> old value -> new value -> what it
 *  impacts. Assembled deterministically so the UI never parses prose. */
export interface ChangeSummaryLine {
  entity_id: string;
  attribute_path: string;
  old_value?: unknown;
  new_value?: unknown;
  unit?: string | null;
  source?: SourceRef | null;
  confidence?: number | null;
  impacted_assets: string[];
  impacted_channels: string[];
  safety: boolean;
}

export interface Recommendation {
  id: string; incident_id: string; scenario_id: string; scenario_name: string;
  confidence: number; narrative: string;
  trade_offs: { dimension: string; gain: string; cost: string }[];
  assumptions: string[];
  rejected_alternatives: { scenario_id: string; why: string }[];
  evidence: string[]; kpis: KPIs; feasible: boolean;
  violations: Violation[]; delta: ChangeSet; citations: Citation[];
  /** The change diff the brief requires, one line per corrected field. */
  changes: ChangeSummaryLine[];
  /** Regulated product or moved safety attribute - approval is not optional. */
  requires_review: boolean;
  provenance: Provenance;
  /** Which revision produced this, what it replaces, and the model's account
   *  of what moved. The figures behind `change` come from `plan_diff`. */
  revision?: number;
  supersedes?: string | null;
  change?: string;
  signals_seen?: { id: string; kind: CorrectionKind }[];
}

export type ApprovalDecision = "APPROVE" | "REJECT" | "MODIFY";

export interface Approval {
  id: string; incident_id: string; scenario_id: string;
  decision: ApprovalDecision; actor: string; comment: string;
  decided_at: string;
  modified_delta?: ChangeSet | null;
}

/** A publish lock on one channel/product for one batch date. HARD locks are
 *  made exclusive by a partial unique index, so a second concurrent republish
 *  fails at the database rather than at a code path someone can forget. */
export interface Reservation {
  id: string; resource_id: string; bucket_date: string; qty: number;
  status: "SOFT" | "HARD" | "RELEASED";
  incident_id: string; scenario_id: string;
  expires_at: string | null;
}

export interface AuditEntry {
  id: string; ts: string; actor: string; action: string;
  entity_type: string; entity_id: string;
  detail: Record<string, unknown>; provenance: Provenance;
}

/* --- run state ---------------------------------------------------------- */

export interface TraceStep {
  node: string; summary: string; detail: Record<string, unknown>;
  /** Milliseconds since the previous trace line - the work between the two,
   *  which is how "which node is slow" gets answered from the run itself. */
  elapsed_ms?: number;
}

/** What one node spent on models. Written per node because the state reducer
 *  merges by key: a flat accumulator would keep only the last writer. */
export interface NodeUsage {
  calls: number; prompt_tokens: number; completion_tokens: number;
  total_tokens: number; cost_usd: number; cache_hits: number;
}

/** One request the investigator made of the evidence desk, and what came back.
 *  REFUSED entries are kept: what the agent wanted and did not get is often
 *  the more interesting half of the record. */
export interface EvidenceRecord {
  tool: string;
  argument: string;
  why: string;
  status: "OK" | "REFUSED" | "ERROR";
  result: Record<string, unknown>;
}

export interface EvidenceTool {
  name: string;
  takes: string;
  describes: string;
}

/** A claim the scan believes the corrected value makes untrue.
 *  Advisory: `upheld` is the deterministic CLAIM_RULES verdict, and only that
 *  turns into a violation. */
export interface ClaimFlag {
  claim: string;
  entity_id: string;
  detail: string;
  upheld: boolean;
}

/** What moved between the superseded plan and this one. Computed by the
 *  validator, never written by a model.
 *
 *  Every field is optional because the graph carries an *empty* diff between
 *  the start of a revision and the re-scoring that fills it in - `monitor`
 *  clears it, `rank` writes it. An empty object is truthy, so a consumer that
 *  tests the object rather than its contents renders a panel with nothing in
 *  it; the optionality here is what makes the compiler say so. */
export interface PlanDiff {
  revision?: number;
  held?: boolean;
  headline?: string;
  previous?: { scenario_id?: string; name?: string; kpis?: Partial<KPIs> };
  current?: { scenario_id?: string; name?: string; kpis?: Partial<KPIs> };
  previous_now_ranked?: number | null;
  previous_still_feasible?: boolean | null;
  moved?: Record<string, number>;
  new_signals?: { id: string; kind: CorrectionKind; summary: string }[];
  reason?: string;
}

export interface RunValues {
  run_id?: string; incident_id?: string; as_of?: string;
  signals?: CorrectionSignal[];
  /* --- the case this run is about --------------------------------------- */
  /** The product the run is scoped to. Empty only on a run that found nothing
   *  open, since a run always works one case. */
  case_id?: string;
  case?: CaseSummary;
  /** Everything else still open, so a decision here is taken in view of what
   *  it is not about. */
  other_open_cases?: CaseSummary[];
  severity?: string; material?: boolean; triage_reason?: string;
  affected?: AffectedScope & { totals?: Record<string, number | string[]> };
  causal_chain?: CausalLink[];
  root_causes?: string[]; symptoms?: string[]; prior_incidents?: string[];
  citations?: Citation[];
  scenarios?: { id: string; name: string; summary: string; delta: ChangeSet }[];
  rejected_actions?: { action: Action; why: string }[];
  ranked?: SimScenario[];
  recommendation?: Recommendation;
  approval?: Pick<Approval, "decision" | "actor" | "comment" | "decided_at">;
  commit_result?: { committed?: boolean; error?: string; detail?: string;
                    actions?: string[]; conflicts?: unknown[] };
  status?: string; trace?: TraceStep[]; errors?: string[];
  /** Model spend, keyed by the node that made the calls. */
  usage?: Record<string, NodeUsage>;

  /* --- scope, copy and the final pass ----------------------------------- */
  scope_candidates?: ChangeScope[];
  chosen_scope?: ChangeScope;
  claim_flags?: ClaimFlag[];
  regenerated?: RegenerateCopyAction[];
  enrichments?: SetAttributeAction[];
  final_validation?: SimResult;

  /* --- re-planning ------------------------------------------------------ */
  revision?: number;
  replan_reason?: string;
  previous_recommendation?: Recommendation;
  previous_ranked?: SimScenario[];
  plan_diff?: PlanDiff;

  /* --- the investigator's evidence desk --------------------------------- */
  evidence_log?: EvidenceRecord[];
}

export interface RunSnapshot {
  thread_id: string; incident_id?: string; status?: string;
  awaiting_approval: boolean; interrupt: unknown; next: string[];
  values: RunValues;
  /** `values.usage` summed across nodes. Absent on the streamed snapshots,
   *  which carry the state as the graph wrote it. */
  usage_total?: NodeUsage & { nodes: number };
}

/* --- system ------------------------------------------------------------- */

export interface GraphTopology {
  nodes: string[];
  edges: { source: string; target: string; conditional: boolean }[];
}

export interface ModelInfo { id: string; tier: "fast" | "reasoning" | "embedding" }

export interface ModelListing {
  models: ModelInfo[];
  by_tier: Record<string, string[]>;
  source: "gateway" | "fallback" | "none";
  error?: string | null;
  active: string; embed: string; cache_enabled: boolean; gateway_url: string;
}

export interface Health {
  ok: boolean;
  gateway: { ok: boolean; url: string; detail: unknown;
             circuit?: { open: boolean; failures: number; retry_in_seconds: number } };
  replay: ReplayState;
  data: { nodes: number; listings: number; assets: number; events: number };
  ingest_cursor: number;
}

export interface IndexStatus {
  chunks: number; documents: number; vectors: boolean; dimensions: number;
  built_at: string | null; embed_model: string | null;
  by_type: Record<string, number>;
}

/* --- MCP toolsets -------------------------------------------------------- */

/** One toolset server, standing in for an independently-owned system.
 *  `read_only` is the property that makes the partition worth having: five of
 *  the six can be handed out, and one cannot. */
export interface MCPServer {
  id: string;
  module: string;
  title: string;
  owner: string;
  why: string;
  tools: string[];
  mutating: string[];
  read_only: boolean;
  command: string;
  /** Where this came from. "built-in" ships here; "connected" was reached at
   *  runtime and can leave again. */
  source?: "built-in" | "connected";
  state?: string;
  /** Tools an operator has allowed a model to call. Connecting a system
   *  records what it can do; it does not admit any of it. */
  admitted?: string[];
  /** Discovered names a built-in toolset already owns. The built-in keeps the
   *  name; these are reported so the shadowing attempt is visible. */
  collisions?: string[];
}

/* --- product 360 -------------------------------------------------------- */

export interface ProductHit {
  entity_id: string; sku: string; name: string;
  product_id: string; product_name: string; category: string;
  supplier: string; regulated: boolean; is_base: boolean;
  /** Present on list results. The list exists to show which products are
   *  holding a launch up, so a row without one is a row nobody can act on. */
  verdict?: string;
  findings?: number;
  checks_complete?: boolean;
}

export interface RecordAttribute {
  path: string; label: string; value: unknown; unit?: string | null;
  source?: string | null;
  /** The external system that carried it. Null is an answer - "we do not know
   *  which system sent this" - rather than an oversight. */
  system?: string | null;
  defects: string[];
  /** Values that lost a precedence contest. A settled disagreement is settled,
   *  not absent. */
  superseded: { value: unknown; system?: string | null; source?: string | null }[];
}

export interface ProductMedia {
  id?: string; role: string; uri: string; alt_text: string;
  system?: string | null;
}

export interface ProductRecord {
  entity_id: string; sku: string; name: string; is_base: boolean;
  product: {
    id: string; name: string; category: string; supplier: string;
    regulated: boolean;
  };
  attributes: RecordAttribute[];
  media: ProductMedia[];
  listings: string[];
}

export interface ReadinessFinding {
  check: string; subject: string; detail: string; severity: string;
  system?: string | null; basis: string; citation: string;
}

/** Deliberately carries no score. A product with three open findings is not
 *  seventy per cent ready - it is not ready, and the findings are what anybody
 *  acts on. */
export interface Readiness {
  entity_id: string;
  verdict: "READY_TO_LAUNCH" | "RETURN_TO_SOURCE" | "BLOCKED" | string;
  ready: boolean;
  findings: ReadinessFinding[];
  blocking: ReadinessFinding[];
  by_system: Record<string, ReadinessFinding[]>;
  /** False when the reading checks could not reach a model. The assessment
   *  found fewer things; it is narrower, not cleaner. */
  checks_complete: boolean;
  caveat?: string | null;
  record?: ProductRecord;
}

export interface Differentiator {
  text: string; attributes: string[]; citation: string; source: string;
  written_by_model: boolean; note: string;
}

export interface Preview {
  entity_id: string;
  rendered: boolean;
  verdict?: string;
  findings?: ReadinessFinding[];
  reason?: string;
  sku?: string;
  title?: string;
  category?: string;
  specification?: { path: string; label: string; value: unknown;
                    unit?: string | null }[];
  media?: ProductMedia[];
  claims?: string[];
  differentiator?: Differentiator | null;
}

/* --- the publication estate -------------------------------------------- */

/** One SKU a correction reaches, and where it is live.
 *
 *  A blast radius expressed only in internal identifiers is one only this
 *  system can read. Everybody who has to act on one works in SKUs. */
export interface AffectedSku {
  sku: string;
  entity_id: string;
  name: string;
  product_id: string;
  listings: string[];
  channels: string[];
}

/** One publication system, with the work it has to do. */
export interface DispatchRow {
  system: string;
  channel_id: string;
  title: string;
  recallable: boolean;
  freeze_days: number;
  listings: string[];
  skus: string[];
  verb: string;
  outcome: "SENT" | "DEFERRED" | "REFUSED" | string;
  reason: string;
  endpoint: string;
}

export interface PublicationImpact {
  root: string;
  totals: Record<string, number>;
  skus: AffectedSku[];
  systems: Omit<DispatchRow, "verb" | "outcome" | "reason" | "endpoint">[];
  /** What would happen if this were dispatched now, without dispatching. */
  dispatch_plan: DispatchRow[];
}


/* --- the capability directory ------------------------------------------- */

/** One capability the estate publishes.
 *
 *  `kind` is load-bearing: "peer" is something this system implements and
 *  another organisation's agent may call; "system" is something it merely knows
 *  how to reach. Flattening the two would say this estate can do things it can
 *  only ask somebody else to do. */
export interface Capability {
  kind: "peer" | "system";
  id: string;
  name: string;
  description: string;
  protocol: string;
  endpoint: string;
  version?: string;
  card_url?: string;
  skills?: { id: string; name: string; description: string;
             examples: string[] }[];
  /** Peers only. Stated rather than left to be inferred from absence. */
  may_not?: string[];
  /** Systems only. */
  owner?: string;
  state?: string;
  tools?: string[];
  admitted?: string[];
}

export interface CapabilityDirectory {
  provider: { organization: string; url: string };
  version: string;
  capabilities: Capability[];
  counts: { peers: number; systems: number; reachable: number };
}


/* --- the external estate ------------------------------------------------ */

/** One external system, as the manifest declares it and the arrivals count it. */
export interface EstateSystem {
  id: string;
  title: string;
  owner: string;
  why: string;
  emits: string[];
  defects: string[];
  defect_rate: number;
  precedence: number;
  well_behaved: boolean;
  index: number;
  /* Present once the system has delivered anything. */
  arrivals?: number;
  batches?: number;
  defective?: number;
  last_seen?: string | null;
}

/** A connection made at runtime: an address, what it said it could do, and
 *  whether it is still answering. */
export interface Connection {
  id: string;
  title: string;
  owner: string;
  url: string;
  transport: string;
  state: "connected" | "degraded" | string;
  detail: string;
  discovered_tools: string[];
  admitted_tools: string[];
  collisions: string[];
  connected_at: string;
  last_seen?: string | null;
}

export interface EstateState {
  systems: EstateSystem[];
  connections: Connection[];
  defects: string[];
  defect_counts: Record<string, number>;
}

/** One delivery landing. Real wall clock, not simulated: an arrival is a fact
 *  about two processes talking, not about the world the tape replays. */
export interface Arrival {
  id: string;
  system_id: string;
  batch_id: string;
  event_id: string;
  seq: number;
  arrived_at: string;
  defects: string[];
}

export interface MCPTransport {
  enabled: boolean;
  routed_tools: string[];
  /** Toolsets retired after a failed spawn; their calls run in-process. */
  degraded: string[];
}

export interface MCPCall {
  seq: number;
  at: number;
  tool: string;
  toolset: string;
  /** "in-process" or "stdio" — which path the call actually took, not which
   *  one was configured. */
  transport: string;
  ms: number;
  ok: boolean;
  detail: string;
}

/* --- A2A peers ----------------------------------------------------------- */

export interface A2AAgent {
  id: string;
  name: string;
  description: string;
  skill: { id: string; name: string; description: string; examples: string[] };
  card_url: string;
  rpc_url: string;
  version: string;
}

export interface A2ATransport {
  enabled: boolean;
  base_url: string;
  agents: string[];
  degraded: string[];
}

export interface A2ACall {
  seq: number;
  at: number;
  agent: string;
  skill: string;
  /** "a2a" or "in-process". */
  transport: string;
  ms: number;
  ok: boolean;
  detail: string;
}

/* --- endpoints ---------------------------------------------------------- */

export const api = {
  health: () => get<Health>("/api/health"),

  network: (asOf?: string, asOfRecorded?: string) => {
    const q = new URLSearchParams();
    if (asOf) q.set("as_of", asOf);
    if (asOfRecorded) q.set("as_of_recorded", asOfRecorded);
    const s = q.toString();
    return get<CatalogState>(`/api/network${s ? `?${s}` : ""}`);
  },
  trace: (entity: string) =>
    get<{ root: string; affected: Record<string, string[]>;
          totals: Record<string, number | string[]> }>(
      `/api/network/trace/${encodeURIComponent(entity)}`),

  /** The attribute table across a product's base and its variants.
   *
   *  `differs` names the paths the variants disagree on, which is the whole
   *  of scenario one: a correction that names the product but not the variant
   *  is only answerable against this table. */
  variants: (productId: string) =>
    get<{ product: string;
          variants: (Variant & { listings: string[] })[];
          /** attribute path -> variant id -> the value in force *and* the
           *  document version it stands on, which is the evidence the scope
           *  argument turns on rather than the number alone. */
          attributes: Record<string, Record<string, unknown>>;
          differs: string[] }>(
      `/api/catalog/variants/${encodeURIComponent(productId)}`),

  /** Lineage in both directions for one attribute, asset or listing: what it
   *  was built from, and every derived output still carrying it. */
  derivation: (id: string) =>
    get<{ id: string;
          derived_from: string[];
          assets: { id: string; listing_id: string; field: string;
                    channel_id: string; built_at_version: string;
                    stale: boolean }[];
          listings: string[]; channels: string[];
          totals: Record<string, number> }>(
      `/api/catalog/derivation/${encodeURIComponent(id)}`),

  events: (limit = 60) =>
    get<{ events: SCEvent[]; replay: ReplayState }>(`/api/events?limit=${limit}`),
  controlState: () =>
    get<{ replay: ReplayState; inject_seq: number; ingest_cursor: number }>(
      "/api/control/state"),
  replay: (body: { action: string; steps?: number; speed?: number; to_seq?: number }) =>
    post<{ replay: ReplayState; released: number; inject_seq: number }>(
      "/api/control/replay", body),

  /** The open correction cases at the replay clock, worst first.
   *
   * The order is the API's own - safety, then regulated, then oldest - and it
   * is the order the run itself picks in, so a caller that re-sorts is showing
   * a different queue from the one the loop works. */
  cases: () => get<{ cases: OpenCase[]; as_of: string }>("/api/cases"),

  /** Start a correction run against one case. Streamed node by node.
   *
   * A correction loop takes the better part of a minute, and a spinner for
   * that long says nothing about whether anything is happening. This reports
   * each node as the graph completes it, so what the reviewer watches is the
   * reasoning rather than a progress bar imitating one.
   *
   * Omitting `case_id` is not "work everything": the graph takes the worst
   * case open, so the reviewer still gets one coherent decision. */
  streamRun: (
    body: { incident_id?: string; thread_id?: string; weights?: unknown;
            case_id?: string },
    onEvent: (e: RunStreamEvent) => void,
  ) => sse("/api/runs", body, onEvent),

  /** A revision, streamed the same way. */
  streamReplan: (
    threadId: string, reason: string,
    onEvent: (e: RunStreamEvent) => void,
  ) => sse(`/api/runs/${threadId}/replan`, { reason }, onEvent),
  run: (threadId: string) => get<RunSnapshot>(`/api/runs/${threadId}`),

  /** Checkpoint history for a thread: the evidence that a run can be killed
   *  mid-flight and resumed, and that a revision continued rather than restarted. */
  history: (threadId: string, limit = 40) =>
    get<{ thread_id: string; checkpoints: {
      checkpoint_id: string; next: string[]; status?: string; created_at?: string;
    }[] }>(`/api/runs/${threadId}/history?limit=${limit}`),

  /** The investigator's tool allowlist, read from the running registry. */
  evidenceTools: () =>
    get<{ max_passes: number; max_requests_per_pass: number;
          tools: EvidenceTool[] }>("/api/evidence/tools"),

  /* --- MCP toolsets ----------------------------------------------------- */

  /** The toolset partition, and how the transport is currently running. */
  mcpServers: () =>
    get<{ servers: MCPServer[]; transport: MCPTransport;
          counts: Record<string, number> }>("/api/mcp/servers"),

  /** Recent tool calls, newest first, each labelled with the transport used. */
  mcpCalls: (limit = 60) =>
    get<{ calls: MCPCall[]; counts: Record<string, number> }>(
      `/api/mcp/calls?limit=${limit}`),

  /** Flip the MCP transport mid-demo. Takes effect on the next lookup. */
  setMcpTransport: (enabled: boolean) =>
    post<MCPTransport>("/api/mcp/transport", { enabled }),

  /* --- product 360 ------------------------------------------------------ */

  /** Find a product by SKU, internal identifier or name. An empty query lists
   *  everything: a page that stays blank until you type looks broken. */
  products: (q = "", limit = 20) =>
    get<{ query: string; results: ProductHit[] }>(
      `/api/products?q=${encodeURIComponent(q)}&limit=${limit}`),

  /** One product's merged record - values, media, carriers, disagreements. */
  productRecord: (id: string) =>
    get<ProductRecord>(`/api/products/${encodeURIComponent(id)}`),

  /** The nine checks and the verdict. */
  readiness: (id: string, useModel = true) =>
    get<Readiness>(
      `/api/products/${encodeURIComponent(id)}/readiness?use_model=${useModel}`),

  /** The staging page, or a refusal carrying the verdict and the findings.
   *
   *  `actor` is required, and is exactly what the approval gate requires -
   *  neither is authenticated. What it buys is accountability: "who looked at
   *  this before it launched" becomes answerable from the audit ledger. */
  preview: (id: string, actor: string, useModel = true) =>
    get<Preview>(
      `/api/products/${encodeURIComponent(id)}/preview` +
      `?use_model=${useModel}&actor=${encodeURIComponent(actor)}`),

  /* --- the publication estate ------------------------------------------ */

  /** What a correction to this entity reaches, in SKUs and in the systems
   *  that have to be told - plus what would happen if it were dispatched
   *  now, which looking at does not do. */
  publicationImpact: (entityId: string) =>
    get<PublicationImpact>(
      `/api/publication/impact/${encodeURIComponent(entityId)}`),

  /* --- the capability directory ----------------------------------------- */

  /** Everything this estate can do, in one document. Served from a well-known
   *  address so a caller who knows only the host can find it. */
  capabilities: () =>
    get<CapabilityDirectory>("/.well-known/agent-cards.json"),

  /* --- the external estate ---------------------------------------------- */

  /** Who feeds the retailer, what is reachable, and what has landed. */
  estate: () => get<EstateState>("/api/estate"),

  /** Deliveries as they landed, newest first. */
  arrivals: (limit = 120) =>
    get<{ arrivals: Arrival[] }>(`/api/estate/arrivals?limit=${limit}`),

  /** Connect a system by address. A handshake that fails answers 200 with a
   *  degraded connection carrying the reason - an unreachable supplier is a
   *  thing to report, not a reason to fail the request. */
  connectSystem: (url: string, title?: string, transport = "http") =>
    post<Connection>("/api/estate/connections", { url, title, transport }),

  /** Disconnect a system. What it delivered stays on the record. */
  disconnectSystem: (id: string) =>
    del<{ removed: boolean; connections: Connection[] }>(
      `/api/estate/connections/${encodeURIComponent(id)}`),

  /** Allow a model to call these tools on a connected system. Deliberately a
   *  separate act from connecting: discovery is not admission. */
  admitTools: (id: string, tools: string[]) =>
    post<Connection>(
      `/api/estate/connections/${encodeURIComponent(id)}/admit`, { tools }),

  /* --- A2A peers -------------------------------------------------------- */

  /** The peer roster and their published Agent Cards. */
  a2aAgents: () =>
    get<{ agents: A2AAgent[]; transport: A2ATransport }>("/api/a2a/agents"),

  /** Recent delegations, newest first. */
  a2aCalls: (limit = 60) =>
    get<{ calls: A2ACall[] }>(`/api/a2a/calls?limit=${limit}`),

  /** Switch delegation between A2A and in-process. */
  setA2aTransport: (enabled: boolean) =>
    post<A2ATransport>("/api/a2a/transport", { enabled }),

  graph: () => get<GraphTopology>("/api/graph"),
  pending: () =>
    get<{ pending: { id: string; thread_id: string; severity: string;
                     title: string; opened_at: string; interrupt: unknown }[] }>(
      "/api/approvals/pending"),
  decide: (threadId: string, body: { decision: string; actor: string;
                                     comment?: string; scenario_id?: string }) =>
    post<RunSnapshot>(`/api/approvals/${threadId}`, body),

  simulate: (delta: ChangeSet, asOf?: string) =>
    post<SimResult & { corrections: string[] }>(
      "/api/scenarios/simulate", { delta, as_of: asOf }),
  compare: (deltas: ChangeSet[], weights?: Record<string, number>) =>
    post<{ scenarios: SimScenario[]; pareto: string[] }>(
      "/api/scenarios/compare", { deltas, weights }),

  audit: (limit = 100) => get<{ entries: AuditEntry[] }>(`/api/audit?limit=${limit}`),
  reservations: () =>
    // Rows are Reservation; kept loose until the panel drops its own local
    // copy of the interface and imports this one.
    get<{ reservations: Record<string, unknown>[] }>("/api/reservations"),

  /** Facts of one kind in force at a moment, on both time axes. */
  facts: (entityType: string, attr?: string) => {
    const q = new URLSearchParams({ entity_type: entityType });
    if (attr) q.set("attr", attr);
    return get<{ facts: Fact[]; provenance_mix: Record<string, number> }>(
      `/api/facts?${q}`);
  },

  /** Every version of one fact, on both time axes. The bitemporal claim made
   *  inspectable rather than asserted. */
  lineage: (factId: string) =>
    get<{ lineage: Fact[] }>(
      `/api/facts/${encodeURIComponent(factId)}/lineage`),

  /** Reverse a committed publication. Pairs with the ledger: a decision that
   *  cannot be undone is a decision nobody should have been asked to make
   *  quickly. */
  rollback: (incidentId: string, scenarioId: string, reason: string) =>
    post<{ rolled_back?: boolean; actions_reversed?: number;
           error?: string; detail?: string }>(
      "/api/plan/rollback",
      { incident_id: incidentId, scenario_id: scenarioId, reason }),

  models: (refresh = false) =>
    get<ModelListing>(`/api/llm/models${refresh ? "?refresh=true" : ""}`),
  setModel: (body: { model?: string; embed_model?: string; cache_enabled?: boolean }) =>
    post<ModelListing & { persisted?: { updated?: Record<string, string>;
                                        created?: Record<string, string> } }>(
      "/api/llm/config", body),
  testModel: (model?: string) =>
    post<{ ok: boolean; model: string; response?: string; error?: string;
           latency_ms: number }>("/api/llm/test", { model }),
  usage: () =>
    get<{ calls: number; cache_hits: number; prompt_tokens: number;
          completion_tokens: number; cost_usd: number; avg_latency_ms: number }>(
      "/api/llm/usage"),

  sopStatus: () => get<IndexStatus>("/api/sop"),
  sopSearch: (q: string, opts?: { top_k?: number; doc_types?: string }) => {
    const p = new URLSearchParams({ q });
    if (opts?.top_k) p.set("top_k", String(opts.top_k));
    if (opts?.doc_types) p.set("doc_types", opts.doc_types);
    return get<{ query: string; results: Citation[]; index: IndexStatus }>(
      `/api/sop/search?${p}`);
  },
  reindex: (embed = true) =>
    post<{ chunks: number; documents: number; embedded: boolean;
           dimensions: number; embed_error?: string | null }>(
      "/api/sop/reindex", { embed }),
};

/* --- run streaming ------------------------------------------------------ */

export type RunStreamEvent =
  | { kind: "run_started"; thread_id: string; incident_id?: string;
      replan?: boolean }
  | { kind: "node"; node: string; update?: Record<string, unknown>;
      error?: string }
  | ({ kind: "run_finished" } & RunSnapshot);

/** POST an endpoint that answers with server-sent events.
 *
 * `EventSource` cannot do this: it is GET-only, and these runs are POSTs
 * carrying a body. So the response is read as a stream and split on the
 * blank-line delimiter by hand. Buffering matters - a chunk boundary lands
 * mid-event often enough that parsing per-chunk drops nodes.
 *
 * Resolves with the final snapshot, so a caller can await the run and stream
 * it at the same time.
 */
async function sse(
  path: string,
  body: unknown,
  onEvent: (e: RunStreamEvent) => void,
): Promise<RunSnapshot> {
  const res = await fetch(`${BASE}${path}/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok || !res.body) {
    throw new Error(`${res.status} ${(await res.text()).slice(0, 300)}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: RunSnapshot | null = null;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let split = buffer.indexOf("\n\n");
    while (split !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      split = buffer.indexOf("\n\n");

      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      try {
        const event = JSON.parse(line.slice(5).trim()) as RunStreamEvent;
        onEvent(event);
        if (event.kind === "run_finished") final = event;
      } catch {
        /* keepalives and partial frames are not errors */
      }
    }
  }

  if (!final) throw new Error("the run ended without reporting a final state");
  return final;
}

/* --- live stream -------------------------------------------------------- */

export type StreamMessage = { kind: string } & Record<string, unknown>;

export function subscribe(onMessage: (m: StreamMessage) => void): () => void {
  const source = new EventSource(`${BASE}/api/events/stream`);
  source.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {
      /* keepalive comments arrive as non-JSON; ignore */
    }
  };
  return () => source.close();
}

/* --- formatting --------------------------------------------------------- */

export const fmt = {
  /** Money is now the exception rather than the rule - the audit trail's LLM
   *  spend is the only figure in the product measured in currency. */
  money: (n: number) =>
    `${n < 0 ? "-" : ""}${Math.abs(n).toLocaleString(undefined, {
      maximumFractionDigits: 0,
    })}`,
  signed: (n: number) =>
    `${n > 0 ? "+" : n < 0 ? "-" : ""}${Math.abs(n).toLocaleString(undefined, {
      maximumFractionDigits: 0,
    })}`,
  pct: (n: number) => `${n.toFixed(2)}%`,
  count: (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 }),
  /** An attribute value, whatever its declared dtype, for the old -> new rows
   *  of the change diff. Lists are joined in order because for `ordered`
   *  attributes - an ingredient declaration - the order is the value. */
  value: (v: unknown): string =>
    v === null || v === undefined
      ? "—"
      : Array.isArray(v)
      ? v.map((x) => String(x)).join(", ")
      : typeof v === "number"
      ? v.toLocaleString()
      : String(v),
  time: (iso?: string | null) => (iso ? iso.slice(11, 16) : "--:--"),
  date: (iso?: string | null) => (iso ? iso.slice(0, 10) : "----------"),
  stamp: (iso?: string | null) => (iso ? iso.slice(0, 16).replace("T", " ") : "-"),
};
