"""Shared contracts for the whole platform.

This module is the day-0 artifact: workstreams A (domain core), B (agent layer)
and C (UI) all depend on these definitions and on nothing else of each other's.
Change anything here and you owe the other two workstreams a heads-up.

Nothing in this file imports from elsewhere in ``sc`` - it must stay a leaf.

The domain is product information management. A supplier sends a corrected
specification after content has already been prepared for several channels; the
system must work out what the correction actually says, which product or variant
it applies to, every derived field and channel that used the old value, and what
has to be revalidated and republished before anything goes live.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Provenance - the spine of the audit story
# ---------------------------------------------------------------------------


class ProvenanceKind(StrEnum):
    """The five classes of knowledge the brief requires be kept distinct.

    Keeping these separate is what lets the UI show a reviewer *why* it believes
    an attribute value, and lets the audit trail distinguish a value read off a
    supplier feed from one a model read out of a PDF.
    """

    RECORDED = "RECORDED"    # observed fact from a source system or document
    INFERRED = "INFERRED"    # an LLM or heuristic concluded it
    DECIDED = "DECIDED"      # a human chose it
    SIMULATED = "SIMULATED"  # produced by the validator, never observed
    COMMITTED = "COMMITTED"  # published to a channel


class Provenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: ProvenanceKind
    source_id: str | None = None  # event id, document id, user id, run id
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    agent: str | None = None  # graph node that produced it
    model: str | None = None  # gateway model alias, when LLM-derived
    run_id: str | None = None
    note: str | None = None


class SourceRef(BaseModel):
    """Where a value came from.

    Every proposed attribute change and every regenerated sentence carries one.
    An action without a source is a rule violation, not a stylistic lapse - the
    brief requires that generated changes cite their evidence.
    """

    doc_id: str
    version: str = ""
    excerpt: str = ""          # the sentence the value was read from
    chunk_id: str | None = None  # retrieval chunk, when the source is corpus


# ---------------------------------------------------------------------------
# Catalog entities
# ---------------------------------------------------------------------------


class CatalogNodeKind(StrEnum):
    SUPPLIER = "SUPPLIER"
    PRODUCT = "PRODUCT"
    VARIANT = "VARIANT"
    CHANNEL = "CHANNEL"


class CatalogNode(BaseModel):
    """One box on the factory map.

    Fixed layout coordinates. The catalog is a known four-tier DAG - supplier,
    product, variant, channel - so the UI draws it as hand-rolled SVG rather
    than running a layout engine.
    """

    id: str
    kind: CatalogNodeKind
    name: str
    group: str  # category family for products, channel class for channels
    x: float
    y: float
    regulated: bool = False      # food, safety or otherwise claim-controlled
    single_source: bool = False  # exactly one supplier document defines it


class AttributeDef(BaseModel):
    """The schema for one product attribute.

    ``safety_class`` is the switch behind the fail-closed rule: a low-confidence
    inference on a safety attribute blocks publication rather than degrading it.
    """

    path: str          # "specs.power_w", "food.allergens.may_contain"
    label: str
    dtype: Literal["int", "float", "str", "bool", "list[str]"]
    unit: str | None = None
    safety_class: bool = False
    ordered: bool = False           # list order carries meaning (ingredients)
    required_for: list[str] = Field(default_factory=list)  # channel ids
    applies_to: list[str] = Field(default_factory=list)    # taxonomy prefixes


class Product(BaseModel):
    id: str
    name: str
    category: str  # internal taxonomy node, e.g. "home.air-treatment.purifiers"
    supplier: str
    regulated: bool = False


class Variant(BaseModel):
    """A sellable form of a product.

    The base-versus-variant distinction is the whole of scenario one: a
    correction that names the product but not the variant is ambiguous, and
    resolving it wrongly republishes the wrong number on the wrong page.
    """

    id: str
    product_id: str
    name: str
    is_base: bool = False


class ChannelKind(StrEnum):
    WEB = "WEB"                  # own product detail page
    MARKETPLACE = "MARKETPLACE"  # external feed with a strict schema
    PRINT = "PRINT"              # catalogue and printed shelf material
    SHELF = "SHELF"              # shelf-edge labels
    SEARCH = "SEARCH"            # derived facets and filters


class Channel(BaseModel):
    id: str
    name: str
    kind: ChannelKind
    taxonomy: str = "internal"  # which category namespace this channel speaks
    # Days before a press date during which content is frozen. Non-zero marks a
    # channel whose published artefact cannot be recalled, and the validator
    # holds those to the stale-version rule: a listing here whose
    # ``published_version`` has been overtaken is a HARD violation that
    # regenerating the copy does not clear. The number of days is the lead time
    # the channel documents, carried into the reviewer's explanation and into
    # triage severity; the press calendar itself is not in the catalog.
    freeze_days: int = 0
    # Internal attribute path -> the channel's own field name.
    attribute_map: dict[str, str] = Field(default_factory=dict)
    category_map: dict[str, str] = Field(default_factory=dict)


class ChannelRuleKind(StrEnum):
    REQUIRED = "REQUIRED"                # the field must be present
    DTYPE = "DTYPE"                      # must parse as the declared type
    MAX_LEN = "MAX_LEN"                  # character budget
    FORMAT = "FORMAT"                    # regex the rendered value must match
    ENUM = "ENUM"                        # value must be one of a fixed set
    ORDERED_MATCH = "ORDERED_MATCH"      # list order must match the source
    CATEGORY_MAPPED = "CATEGORY_MAPPED"  # taxonomy node must map to this channel


class ChannelRule(BaseModel):
    """One publishable-or-not rule, evaluated deterministically.

    Rules are data rather than code so the corpus can document the same rule a
    reviewer sees enforced, and so a channel can be added without touching the
    validator.
    """

    id: str
    channel_id: str
    field: str                     # the channel-side field name
    kind: ChannelRuleKind
    attribute_path: str | None = None
    value: object | None = None    # length, pattern, enum members
    severity: Literal["HARD", "SOFT"] = "HARD"
    detail: str = ""


class Listing(BaseModel):
    """One variant published (or about to be) on one channel.

    Listings are the edges of the catalog graph and the unit the blast radius
    is counted in: "this correction touches eleven listings across four
    channels" is the sentence the reviewer needs.
    """

    id: str
    variant_id: str
    channel_id: str
    status: Literal["LIVE", "PREPARED", "WITHHELD", "REJECTED"] = "PREPARED"
    # Source version the live content was built from, moved forward by every
    # commit. On a channel with a freeze window this is what the values in
    # force are compared against. Empty means the listing has never gone out,
    # so there is no artefact in the world that can be stale.
    published_version: str = ""


class ContentAsset(BaseModel):
    """A derived output - a title, a bullet, a feed row, a shelf label.

    ``derived_from`` is the lineage that makes propagation deterministic:
    correcting an attribute marks every asset naming it as stale, with no model
    involved in deciding what is affected.
    """

    id: str
    listing_id: str
    field: str  # "title" | "bullets" | "description" | "comparison_table" | ...
    text: str
    derived_from: list[str] = Field(default_factory=list)  # "VAR-01B:specs.power_w"
    claims_used: list[str] = Field(default_factory=list)
    built_at_version: str = ""  # source doc version the copy was written against
    regulated: bool = False


class SourceDocKind(StrEnum):
    SPEC_SHEET = "SPEC_SHEET"
    LABEL_ARTWORK = "LABEL_ARTWORK"
    PORTAL_FEED = "PORTAL_FEED"
    SPREADSHEET = "SPREADSHEET"
    EMAIL = "EMAIL"
    CERTIFICATE = "CERTIFICATE"


class SourceDoc(BaseModel):
    """A supplier document, versioned.

    ``precedence`` encodes the policy order used to settle contradictions
    between sources - label artwork outranks a portal feed, which outranks an
    email. Higher wins. Keeping it on the document means the resolution is
    explainable without asking a model what it thinks should count more.
    """

    id: str
    supplier: str
    kind: SourceDocKind
    version: str
    title: str
    received_at: datetime
    status: Literal["ACTIVE", "SUPERSEDED", "WITHDRAWN"] = "ACTIVE"
    precedence: int = 0
    body_path: str | None = None  # extracted text on disk, for SPEC_DOC events


class Catalog(BaseModel):
    """The static product model. Time-varying values live in the fact store."""

    nodes: list[CatalogNode]
    products: list[Product]
    variants: list[Variant]
    channels: list[Channel]
    rules: list[ChannelRule]
    listings: list[Listing]
    attributes: list[AttributeDef]
    taxonomy: dict[str, object] = Field(default_factory=dict)
    horizon_start: date
    horizon_days: int


# ---------------------------------------------------------------------------
# Bitemporal facts
# ---------------------------------------------------------------------------


class Fact(BaseModel):
    """A time-varying assertion about one entity attribute.

    Two independent time axes:

    * ``valid_from`` / ``valid_to`` - when the assertion is true in the world
    * ``recorded_at``               - when this system learned it

    Corrections never update in place. They insert a new row pointing at the
    one they replace via ``supersedes_id``, so "what did the content team know
    when they wrote this bullet?" and "what is actually true?" remain separately
    answerable - which is exactly what a late-arriving corrected specification
    demands.
    """

    id: str
    entity_type: str  # "variant" | "product" | "listing" | "channel" | "source_doc"
    entity_id: str
    attr: str         # "specs.power_w" | "food.allergens.may_contain" | "version"
    value: object

    valid_from: datetime
    valid_to: datetime | None = None  # None = still true
    recorded_at: datetime
    supersedes_id: str | None = None

    provenance: Provenance


# ---------------------------------------------------------------------------
# Events and correction signals
# ---------------------------------------------------------------------------


class EventType(StrEnum):
    SUPPLIER_FEED = "SUPPLIER_FEED"          # structured attribute rows
    SPEC_DOC = "SPEC_DOC"                    # a document version, body = text
    CHANNEL_STATUS = "CHANNEL_STATUS"        # feed acknowledgement or rejection
    CATALOG_UPDATE = "CATALOG_UPDATE"        # internal edit
    PUBLISH_TELEMETRY = "PUBLISH_TELEMETRY"  # routine liveness, never a signal
    COMMS = "COMMS"                          # unstructured: email / notice


class Event(BaseModel):
    id: str
    seq: int      # monotonic ordering key within the tape
    ts: datetime  # simulated wall-clock of the event
    type: EventType
    source: str   # "SUPPLIER_PORTAL" | "MAILBOX" | "PIM" | "CHANNEL_GATEWAY"
    payload: dict[str, object]
    body: str | None = None  # raw text for COMMS and SPEC_DOC events


class CorrectionKind(StrEnum):
    SPEC_CORRECTION = "SPEC_CORRECTION"
    ALLERGEN_CHANGE = "ALLERGEN_CHANGE"
    INGREDIENT_CHANGE = "INGREDIENT_CHANGE"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    CHANNEL_REJECTION = "CHANNEL_REJECTION"
    DOC_WITHDRAWN = "DOC_WITHDRAWN"
    DATA_GAP = "DATA_GAP"


class CorrectionSignal(BaseModel):
    """A detected correction, structured or extracted from prose.

    ``provenance.kind`` is RECORDED when it came from a structured feed and
    INFERRED when a model read it out of a document - the UI badges differ, and
    the fail-closed safety gate only applies to the latter.

    ``resolves_issue`` marks a notice that *clears* an earlier one rather than
    revising a value; the state reducer uses it to retire the signal it cancels
    instead of stacking a second open issue on top.
    """

    id: str
    kind: CorrectionKind
    detected_at: datetime
    entities: list[str]  # product / variant / listing / channel / doc ids
    attribute_paths: list[str] = Field(default_factory=list)
    old_value: object | None = None
    new_value: object | None = None
    unit: str | None = None
    # Effective dating: when the corrected value becomes true in the world.
    window_start: date | None = None
    window_end: date | None = None
    summary: str
    source_event_id: str | None = None
    source: SourceRef | None = None
    resolves_issue: bool = False
    provisional: bool = False
    provenance: Provenance


# ---------------------------------------------------------------------------
# Correction case and impact analysis
# ---------------------------------------------------------------------------


class CausalLink(BaseModel):
    """One hop in the chain from corrected source to impacted output."""

    from_ref: str
    to_ref: str
    relation: str  # "supersedes" | "defines" | "derives" | "lists_on" | "feeds"
    explanation: str
    evidence: list[str] = Field(default_factory=list)  # event / doc / fact ids


class AffectedScope(BaseModel):
    """The blast radius, counted in the units a reviewer cares about."""

    products: list[str] = Field(default_factory=list)
    variants: list[str] = Field(default_factory=list)
    attributes: list[str] = Field(default_factory=list)  # "VAR-01B:specs.power_w"
    assets: list[str] = Field(default_factory=list)
    listings: list[str] = Field(default_factory=list)
    channels: list[str] = Field(default_factory=list)


class IncidentStatus(StrEnum):
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMMITTED = "COMMITTED"
    PARKED = "PARKED"  # triaged as immaterial
    REJECTED = "REJECTED"


class Incident(BaseModel):
    """One correction case: a piece of new evidence and everything it moved.

    Named ``Incident`` throughout the schema and the graph state for continuity;
    the UI labels it "correction case".
    """

    id: str
    thread_id: str  # LangGraph thread - links the case to its run
    opened_at: datetime
    status: IncidentStatus
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    title: str

    signals: list[CorrectionSignal] = Field(default_factory=list)
    root_causes: list[str] = Field(default_factory=list)  # signal ids
    symptoms: list[str] = Field(default_factory=list)     # signal ids, secondary
    causal_chain: list[CausalLink] = Field(default_factory=list)
    affected: AffectedScope = Field(default_factory=AffectedScope)
    citations: list[str] = Field(default_factory=list)  # corpus chunk ids
    provenance: Provenance


# ---------------------------------------------------------------------------
# Change sets - the only thing the validator accepts and the reviewer approves
# ---------------------------------------------------------------------------


class ScopeLevel(StrEnum):
    BASE = "BASE"        # the base variant only
    VARIANT = "VARIANT"  # one named variant
    ALL = "ALL"          # every variant of the product


class ChangeScope(BaseModel):
    """One reading of who a correction applies to.

    The candidates a run compares are competing answers to this question, and
    the deterministic validator is what decides between them - the model's job
    is to argue for a reading, not to pick one.
    """

    level: ScopeLevel
    entities: list[str] = Field(default_factory=list)  # variant ids in scope
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    evidence: list[str] = Field(default_factory=list)


class ActionKind(StrEnum):
    SET_ATTRIBUTE = "SET_ATTRIBUTE"
    REGENERATE_COPY = "REGENERATE_COPY"
    REMAP_TAXONOMY = "REMAP_TAXONOMY"
    SET_FACET = "SET_FACET"
    WITHHOLD_CHANNEL = "WITHHOLD_CHANNEL"
    REQUEST_SUPPLIER_INPUT = "REQUEST_SUPPLIER_INPUT"


class _ActionBase(BaseModel):
    id: str
    rationale: str = ""
    # Every action that publishes to a channel names the lock it needs here.
    # The reservation ledger uses this to detect concurrent republishing.
    resource_id: str | None = None
    bucket_date: date | None = None
    qty: float = 0.0
    # Where the change came from. Absent on a change that alters a published
    # value is a violation, not a warning.
    source: SourceRef | None = None


class SetAttributeAction(_ActionBase):
    kind: Literal[ActionKind.SET_ATTRIBUTE] = ActionKind.SET_ATTRIBUTE
    entity_id: str
    attribute_path: str
    old_value: object | None = None
    new_value: object | None = None
    unit: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class RegenerateCopyAction(_ActionBase):
    kind: Literal[ActionKind.REGENERATE_COPY] = ActionKind.REGENERATE_COPY
    listing_id: str
    asset_id: str
    field: str
    old_excerpt: str = ""
    proposed_text: str = ""
    reason: str = ""


class RemapTaxonomyAction(_ActionBase):
    kind: Literal[ActionKind.REMAP_TAXONOMY] = ActionKind.REMAP_TAXONOMY
    listing_id: str
    from_node: str
    to_node: str


class SetFacetAction(_ActionBase):
    kind: Literal[ActionKind.SET_FACET] = ActionKind.SET_FACET
    channel_id: str
    facet: str
    op: Literal["ADD", "REMOVE"]
    reason: str = ""


class WithholdChannelAction(_ActionBase):
    """The fail-closed block, recorded as an explicit act.

    Withholding is a decision with consequences, so it is an action in the
    change set rather than an absence of one - it appears in the diff, needs
    approval like anything else, and shows up in the audit trail.
    """

    kind: Literal[ActionKind.WITHHOLD_CHANNEL] = ActionKind.WITHHOLD_CHANNEL
    listing_id: str
    channel_id: str
    reason: str = ""


class RequestSupplierInputAction(_ActionBase):
    """Ask a human to ask the supplier. Never executed by the system."""

    kind: Literal[ActionKind.REQUEST_SUPPLIER_INPUT] = ActionKind.REQUEST_SUPPLIER_INPUT
    supplier: str
    doc_ref: str = ""
    question: str = ""


Action = Annotated[
    Union[
        SetAttributeAction,
        RegenerateCopyAction,
        RemapTaxonomyAction,
        SetFacetAction,
        WithholdChannelAction,
        RequestSupplierInputAction,
    ],
    Field(discriminator="kind"),
]


class ChangeSet(BaseModel):
    """A candidate resolution of one correction.

    Change sets are the only thing the validator accepts, and the only thing a
    reviewer ever approves. Published content is never mutated in place.
    """

    id: str
    scope: ChangeScope = Field(default_factory=lambda: ChangeScope(level=ScopeLevel.ALL))
    actions: list[Action] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class ViolationSeverity(StrEnum):
    HARD = "HARD"  # blocks publication
    SOFT = "SOFT"  # publishable but breaches a target


class Violation(BaseModel):
    """A rule breach. Always names the binding rule - a blocked channel is shown
    with its reason, never silently dropped."""

    constraint: str  # "channel_schema" | "claim_consistency" | "safety_confidence"
    severity: ViolationSeverity
    entity_id: str            # "LST-04:title" | "VAR-01B:specs.power_w"
    channel_id: str | None = None
    bucket_date: date | None = None
    required: float = 0.0     # e.g. the 80-character budget
    available: float = 0.0    # e.g. the 94 characters actually written
    detail: str = ""


class KPIs(BaseModel):
    """What a resolution costs, measured only in things the validator computes.

    No model produces any of these numbers. They are what the ranked comparison
    and the change diff are built from.
    """

    fields_affected: int = 0       # attribute values this resolution changes
    assets_stale: int = 0          # derived outputs still on a superseded value
    channels_blocked: int = 0      # channels not publish-ready afterwards
    listings_ready_pct: float = 0.0    # affected listings passing every rule
    completeness_pct: float = 0.0      # mandatory fields filled, affected scope
    safety_flags: int = 0          # open HARD violations on a safety declaration
    republish_steps: int = 0       # regenerations + remaps + feed pushes pending


class SimResult(BaseModel):
    """The validator's verdict on one change set.

    Named ``SimResult`` for continuity with the run/scenario plumbing; it is the
    output of a deterministic validation pass, not a simulation of anything
    uncertain.
    """

    delta_id: str
    feasible: bool  # no HARD violations - i.e. publishable
    violations: list[Violation] = Field(default_factory=list)
    kpis: KPIs
    # Hash over the full internal trace. Two validations of the same change set
    # against the same catalog must produce the same hash - the determinism test.
    trace_hash: str
    runtime_ms: float = 0.0


class ObjectiveWeights(BaseModel):
    """Ranking weights. Safety is not among them on purpose: safety is a
    pre-sort, not a preference. A resolution with an open safety flag never
    outranks one without, whatever the reviewer sets these to."""

    readiness: float = 0.45   # how much of the affected scope becomes publishable
    precision: float = 0.30   # prefer the narrowest scope the evidence supports
    effort: float = 0.15      # fewer republish steps
    completeness: float = 0.10


class Scenario(BaseModel):
    """A candidate resolution plus its verdict. Labelled "resolution" in the UI."""

    id: str
    incident_id: str
    name: str
    summary: str
    delta: ChangeSet
    sim: SimResult | None = None
    score: float | None = None
    pareto_optimal: bool = False
    rationale: str = ""  # LLM narrative - never the source of any number
    citations: list[str] = Field(default_factory=list)
    provenance: Provenance


# ---------------------------------------------------------------------------
# Recommendation, approval, audit
# ---------------------------------------------------------------------------


class TradeOff(BaseModel):
    dimension: str  # "readiness" | "precision" | ...
    gain: str
    cost: str


class ChangeSummaryLine(BaseModel):
    """One row of the reviewer's diff: source, old value, new value, blast.

    The brief requires every generated change to show
    ``source -> old value -> new value -> impacted outputs``. This is that
    sentence, assembled deterministically so the UI never has to parse prose.
    """

    entity_id: str
    attribute_path: str
    old_value: object | None = None
    new_value: object | None = None
    unit: str | None = None
    source: SourceRef | None = None
    confidence: float | None = None
    impacted_assets: list[str] = Field(default_factory=list)
    impacted_channels: list[str] = Field(default_factory=list)
    safety: bool = False


class Recommendation(BaseModel):
    id: str
    incident_id: str
    scenario_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)  # event / fact / doc ids
    assumptions: list[str] = Field(default_factory=list)
    trade_offs: list[TradeOff] = Field(default_factory=list)
    changes: list[ChangeSummaryLine] = Field(default_factory=list)
    narrative: str = ""
    rejected_alternatives: list[str] = Field(default_factory=list)
    # Approval is not optional. Computed from the change set by
    # ``graph.nodes._review_grounds``, never by a model.
    requires_review: bool = False
    provenance: Provenance


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    MODIFY = "MODIFY"


class Approval(BaseModel):
    id: str
    incident_id: str
    scenario_id: str
    decision: ApprovalDecision
    actor: str
    comment: str = ""
    decided_at: datetime
    modified_delta: ChangeSet | None = None  # set when decision is MODIFY


class ReservationStatus(StrEnum):
    SOFT = "SOFT"  # held by a proposed resolution, expires
    HARD = "HARD"  # published; a partial unique index makes these exclusive
    RELEASED = "RELEASED"


class Reservation(BaseModel):
    """A publish lock on one channel/product for one batch date.

    Exclusivity of HARD locks is enforced by a partial unique index in the
    schema, not by application logic - a second concurrent republish of the same
    product to the same channel fails at the database, which is what makes
    conflicting publication impossible rather than merely unlikely.
    """

    id: str
    resource_id: str  # "CH-MKT-A:PRD-01"
    bucket_date: date
    qty: float
    status: ReservationStatus
    incident_id: str
    scenario_id: str
    expires_at: datetime | None = None


class CommittedAction(BaseModel):
    id: str
    incident_id: str
    scenario_id: str
    action_id: str
    idempotency_key: str
    committed_at: datetime
    result: dict[str, object] = Field(default_factory=dict)
    rolled_back: bool = False


class AuditEntry(BaseModel):
    """One line of the append-only ledger behind the Review & Audit tab."""

    id: str
    ts: datetime
    actor: str  # user id or graph node name
    action: str
    entity_type: str
    entity_id: str
    detail: dict[str, object] = Field(default_factory=dict)
    provenance: Provenance


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


class DocChunk(BaseModel):
    id: str
    doc_id: str
    doc_type: Literal["STANDARD", "CHANNEL", "POLICY", "POSTMORTEM", "COMMS"]
    title: str
    text: str
    ordinal: int
    metadata: dict[str, object] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk: DocChunk
    score: float


# ---------------------------------------------------------------------------
# Gateway / model config
# ---------------------------------------------------------------------------


class ModelInfo(BaseModel):
    id: str
    tier: Literal["fast", "reasoning", "embedding"] = "fast"


class LlmUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    cached: bool = False


class LlmConfig(BaseModel):
    default_model: str
    embed_model: str
    gateway_url: str
    cache_enabled: bool
    available_models: list[ModelInfo] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Replay control
# ---------------------------------------------------------------------------


class ReplayAction(StrEnum):
    START = "START"
    PAUSE = "PAUSE"
    STEP = "STEP"
    SPEED = "SPEED"
    JUMP = "JUMP"
    RESET = "RESET"


class ReplayCommand(BaseModel):
    action: ReplayAction
    speed: float | None = None  # multiplier, e.g. 10.0
    to_seq: int | None = None   # for JUMP
    steps: int = 1              # for STEP


class ReplayState(BaseModel):
    running: bool
    speed: float
    cursor_seq: int
    total_events: int
    sim_clock: datetime | None = None
