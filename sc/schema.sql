-- Autonomous Product Intelligence Factory - SQLite schema.
--
-- One file, WAL mode, no server. Every table here is inspectable with a
-- sqlite3 shell during a demo, which is a feature: "show me the audit trail"
-- is answerable with a SELECT.
--
-- LangGraph's SqliteSaver manages its own checkpoint tables in this same file;
-- they are deliberately not declared here.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- ---------------------------------------------------------------------------
-- Bitemporal fact store
-- ---------------------------------------------------------------------------
-- Two time axes. valid_from/valid_to say when an assertion is true in the
-- world; recorded_at says when we learned it. A correction inserts a new row
-- naming the row it replaces - we never UPDATE a fact in place, because doing
-- so would destroy the answer to "what did the content team know when they
-- wrote this?", which is the whole question a late supplier correction asks.

CREATE TABLE IF NOT EXISTS facts (
  id             TEXT PRIMARY KEY,
  entity_type    TEXT NOT NULL,
  entity_id      TEXT NOT NULL,
  attr           TEXT NOT NULL,
  value          TEXT NOT NULL,           -- JSON
  valid_from     TEXT NOT NULL,           -- ISO8601
  valid_to       TEXT,                    -- NULL = still true
  recorded_at    TEXT NOT NULL,           -- ISO8601
  supersedes_id  TEXT REFERENCES facts(id),
  provenance     TEXT NOT NULL            -- JSON Provenance
);

-- The as-of query shape: filter entity+attr, then bracket both time axes.
CREATE INDEX IF NOT EXISTS idx_facts_asof
  ON facts (entity_type, entity_id, attr, valid_from, recorded_at);
CREATE INDEX IF NOT EXISTS idx_facts_recorded ON facts (recorded_at);
CREATE INDEX IF NOT EXISTS idx_facts_supersedes ON facts (supersedes_id);

-- ---------------------------------------------------------------------------
-- Event plane
-- ---------------------------------------------------------------------------
-- Replaces Redis Streams. `seq` is the offset; consumers track their position
-- in event_cursors and advance it in the same transaction that writes their
-- output, which is what makes redelivery after a crash safe.

CREATE TABLE IF NOT EXISTS events (
  id            TEXT PRIMARY KEY,
  seq           INTEGER NOT NULL UNIQUE,
  ts            TEXT NOT NULL,            -- simulated wall-clock
  type          TEXT NOT NULL,
  source        TEXT NOT NULL,
  payload       TEXT NOT NULL,            -- JSON
  body          TEXT,                     -- raw prose for COMMS events
  released_at   TEXT,                     -- when the replayer made it visible
  -- TAPE is the recorded flight, replayed on a controllable clock. LIVE is
  -- what arrived through a vendor intake while the process was running, and it
  -- is visible the instant it lands - a submission is not something the
  -- replay transport gets to rewind. Every query that means "the recorded
  -- flight" says `lane = 'TAPE'` rather than inferring it from the sequence,
  -- because a magic number four modules have to agree about is a number they
  -- will eventually disagree about.
  lane          TEXT NOT NULL DEFAULT 'TAPE'   -- TAPE | LIVE
);

CREATE INDEX IF NOT EXISTS idx_events_seq ON events (seq);
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events (type, ts);

CREATE TABLE IF NOT EXISTS event_cursors (
  consumer      TEXT PRIMARY KEY,
  last_seq      INTEGER NOT NULL DEFAULT 0,
  updated_at    TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Incidents, scenarios, recommendations
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS incidents (
  id            TEXT PRIMARY KEY,
  thread_id     TEXT NOT NULL,            -- LangGraph thread
  opened_at     TEXT NOT NULL,
  status        TEXT NOT NULL,
  severity      TEXT NOT NULL,
  title         TEXT NOT NULL,
  doc           TEXT NOT NULL             -- JSON Incident
);

CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents (status, opened_at);
CREATE INDEX IF NOT EXISTS idx_incidents_thread ON incidents (thread_id);

CREATE TABLE IF NOT EXISTS scenarios (
  id            TEXT PRIMARY KEY,
  incident_id   TEXT NOT NULL REFERENCES incidents(id),
  name          TEXT NOT NULL,
  score         REAL,
  feasible      INTEGER,
  pareto        INTEGER NOT NULL DEFAULT 0,
  doc           TEXT NOT NULL             -- JSON Scenario (resolution + SimResult)
);

CREATE INDEX IF NOT EXISTS idx_scenarios_incident ON scenarios (incident_id, score);

CREATE TABLE IF NOT EXISTS recommendations (
  id            TEXT PRIMARY KEY,
  incident_id   TEXT NOT NULL REFERENCES incidents(id),
  scenario_id   TEXT NOT NULL REFERENCES scenarios(id),
  created_at    TEXT NOT NULL,
  doc           TEXT NOT NULL             -- JSON Recommendation
);

-- ---------------------------------------------------------------------------
-- Approval and execution
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS approvals (
  id            TEXT PRIMARY KEY,
  incident_id   TEXT NOT NULL REFERENCES incidents(id),
  scenario_id   TEXT NOT NULL REFERENCES scenarios(id),
  decision      TEXT NOT NULL,
  actor         TEXT NOT NULL,
  comment       TEXT NOT NULL DEFAULT '',
  decided_at    TEXT NOT NULL,
  modified_delta TEXT                     -- JSON ChangeSet, when MODIFY
);

CREATE INDEX IF NOT EXISTS idx_approvals_incident ON approvals (incident_id);

-- Publish locks. The mechanism that makes conflicting republishing impossible
-- rather than merely unlikely: a HARD lock is exclusive per (channel:product,
-- batch date) and the database enforces it - a second concurrent publish fails
-- on integrity error, which the tool layer surfaces as a conflict violation.
CREATE TABLE IF NOT EXISTS reservations (
  id            TEXT PRIMARY KEY,
  resource_id   TEXT NOT NULL,            -- "CH-MKT-A:PRD-01"
  bucket_date   TEXT NOT NULL,            -- ISO date
  qty           REAL NOT NULL,
  status        TEXT NOT NULL,            -- SOFT | HARD | RELEASED
  incident_id   TEXT NOT NULL,
  scenario_id   TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  expires_at    TEXT                      -- SOFT holds expire
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_reservation_hard
  ON reservations (resource_id, bucket_date)
  WHERE status = 'HARD';

CREATE INDEX IF NOT EXISTS idx_reservations_lookup
  ON reservations (resource_id, bucket_date, status);

-- Idempotency: every mutating tool call carries a key. A replayed call finds
-- its own prior result here and returns it rather than acting twice.
CREATE TABLE IF NOT EXISTS idempotency_keys (
  key           TEXT PRIMARY KEY,
  tool          TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  result        TEXT NOT NULL             -- JSON of the original result
);

CREATE TABLE IF NOT EXISTS committed_actions (
  id               TEXT PRIMARY KEY,
  incident_id      TEXT NOT NULL,
  scenario_id      TEXT NOT NULL,
  action_id        TEXT NOT NULL,
  idempotency_key  TEXT NOT NULL,
  committed_at     TEXT NOT NULL,
  result           TEXT NOT NULL,         -- JSON
  rolled_back      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_committed_incident
  ON committed_actions (incident_id, committed_at);

-- ---------------------------------------------------------------------------
-- Audit ledger - append only
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit (
  id            TEXT PRIMARY KEY,
  ts            TEXT NOT NULL,
  actor         TEXT NOT NULL,            -- user id or graph node name
  action        TEXT NOT NULL,
  entity_type   TEXT NOT NULL,
  entity_id     TEXT NOT NULL,
  detail        TEXT NOT NULL DEFAULT '{}',
  provenance    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit (ts);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit (entity_type, entity_id);

-- ---------------------------------------------------------------------------
-- LLM call ledger + response cache
-- ---------------------------------------------------------------------------
-- Doubles as the cost/token ledger shown in the audit view and as the
-- record/replay cache that makes rehearsals deterministic, fast and
-- independent of venue wifi.

CREATE TABLE IF NOT EXISTS llm_calls (
  cache_key         TEXT PRIMARY KEY,     -- sha256(model|temperature|messages)
  model             TEXT NOT NULL,
  temperature       REAL NOT NULL,
  request           TEXT NOT NULL,        -- JSON messages
  response          TEXT NOT NULL,
  prompt_tokens     INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd          REAL NOT NULL DEFAULT 0,
  latency_ms        REAL NOT NULL DEFAULT 0,
  created_at        TEXT NOT NULL,
  hits              INTEGER NOT NULL DEFAULT 0,
  run_id            TEXT,
  agent             TEXT
);

CREATE INDEX IF NOT EXISTS idx_llm_run ON llm_calls (run_id, created_at);

-- The same idea, for embeddings. Retrieval embeds the *query*, not the corpus,
-- so it is a live call on the read path rather than a build step - and it was
-- the only model call in the platform that was not cached, which made every
-- readiness check pay a network round trip to ask the same question again.
--
-- Keyed on (model, text) rather than on a temperature: an embedding has no
-- sampling to vary. Stored as JSON rather than a blob because the vectors are
-- small, the row count is bounded by the number of distinct questions this
-- system asks, and a readable cache is one an operator can inspect.

CREATE TABLE IF NOT EXISTS llm_embeddings (
  cache_key   TEXT PRIMARY KEY,           -- sha256(model|text)
  model       TEXT NOT NULL,
  text        TEXT NOT NULL,
  vector      TEXT NOT NULL,              -- JSON array of floats
  created_at  TEXT NOT NULL,
  hits        INTEGER NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- Retrieval corpus (vectors live in a sidecar .npy, keyed by chunk id order)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS doc_chunks (
  id            TEXT PRIMARY KEY,
  doc_id        TEXT NOT NULL,
  doc_type      TEXT NOT NULL,
  title         TEXT NOT NULL,
  text          TEXT NOT NULL,
  ordinal       INTEGER NOT NULL,
  metadata      TEXT NOT NULL DEFAULT '{}',
  row_index     INTEGER NOT NULL          -- row in the embeddings matrix
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON doc_chunks (doc_id, ordinal);
CREATE INDEX IF NOT EXISTS idx_chunks_row ON doc_chunks (row_index);

-- ---------------------------------------------------------------------------
-- Runtime key/value (replay cursor, active model, cache toggle)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS runtime_config (
  key           TEXT PRIMARY KEY,
  value         TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- The external estate
-- ---------------------------------------------------------------------------
-- Two tables, and the split between them is the whole correctness argument.
--
-- `arrivals` is what landed: which system delivered it, in which batch, at
-- which instant, and what was wrong with it. Concurrent and out of order,
-- because ten systems deliver at once and nothing coordinates them.
--
-- Ingestion is *not* driven from here. It still reads the event plane in `seq`
-- order, because the consumer cursor in event_cursors is a single watermark:
-- a system delivering seq 50 before another delivers seq 30 would advance the
-- cursor past 30 and the second batch would be dropped as already seen. So
-- arrival is asynchronous and ingestion is sequenced, and an arrival is a fact
-- about the integration surface rather than an instruction to the record.

CREATE TABLE IF NOT EXISTS arrivals (
  id            TEXT PRIMARY KEY,
  system_id     TEXT NOT NULL,
  batch_id      TEXT NOT NULL,            -- shared across one delivery
  event_id      TEXT NOT NULL,
  seq           INTEGER NOT NULL,         -- the tape position it carries
  arrived_at    TEXT NOT NULL,            -- real wall clock, not simulated
  defects       TEXT NOT NULL DEFAULT '[]'  -- JSON array of Defect names
);

CREATE INDEX IF NOT EXISTS idx_arrivals_system ON arrivals (system_id, seq);
CREATE INDEX IF NOT EXISTS idx_arrivals_batch ON arrivals (batch_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_arrivals_event ON arrivals (event_id);

-- What is connected right now. Persisted rather than held in memory so a
-- connection survives a restart, and so "what was the estate when this ran"
-- is answerable afterwards.
--
-- `discovered_tools` is what the system said it could do at the handshake.
-- `admitted_tools` is the subset an operator has allowed a model to call.
-- They are deliberately different columns: discovery is not admission, and
-- connecting a system must not widen the evidence desk's allowlist by itself.

CREATE TABLE IF NOT EXISTS connections (
  id               TEXT PRIMARY KEY,
  title            TEXT NOT NULL,
  owner            TEXT NOT NULL,
  url              TEXT NOT NULL,
  transport        TEXT NOT NULL,         -- http | sse | stdio
  state            TEXT NOT NULL,         -- connected | degraded | lost
  detail           TEXT NOT NULL DEFAULT '',
  discovered_tools TEXT NOT NULL DEFAULT '[]',
  admitted_tools   TEXT NOT NULL DEFAULT '[]',
  collisions       TEXT NOT NULL DEFAULT '[]',
  connected_at     TEXT NOT NULL,
  last_seen        TEXT
);

-- ---------------------------------------------------------------------------
-- Vendor submissions - the supplier's side of the ledger
-- ---------------------------------------------------------------------------
-- `arrivals` is the retailer's record of what landed. This is the supplier's
-- record of what it sent, and they are not the same question: one submission
-- can carry several events, plus bytes on disk, plus the idempotency key the
-- portal generated.
--
-- It holds only the submission's own facts and JOINS for everything the
-- platform decided. There is deliberately no `status` column and no `verdict`
-- column: a stored verdict that can disagree with the record is the thing this
-- system spends most of its design avoiding.

CREATE TABLE IF NOT EXISTS submissions (
  id              TEXT PRIMARY KEY,       -- SUB-<hex12>
  supplier_id     TEXT NOT NULL,
  system_id       TEXT NOT NULL,          -- the carrier, bound by the mount path
  kind            TEXT NOT NULL,          -- SPEC_CHANGE|DOCUMENT|IMAGE|PRODUCT_DRAFT
  submitted_at    TEXT NOT NULL,          -- simulated clock, like every fact
  wall_at         TEXT NOT NULL,          -- real clock, like arrivals.arrived_at
  event_ids       TEXT NOT NULL DEFAULT '[]',
  entity_ids      TEXT NOT NULL DEFAULT '[]',
  doc_ref         TEXT NOT NULL DEFAULT '',
  files           TEXT NOT NULL DEFAULT '[]',   -- [{path,bytes,sha256,role}]
  note            TEXT NOT NULL DEFAULT '',
  effective_from  TEXT,
  idempotency_key TEXT
);

CREATE INDEX IF NOT EXISTS idx_submissions_supplier
  ON submissions (supplier_id, submitted_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_submissions_idem
  ON submissions (idempotency_key) WHERE idempotency_key IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Obligations - work somebody still owes the world
-- ---------------------------------------------------------------------------
-- A redaction hides a wrong value. On a channel whose artefact cannot be
-- recalled there is nothing to hide: 214,000 catalogues are already printed.
-- The only truthful outcome is an obligation - open, owned and dated - and
-- that is not a fact about content, so it does not belong in the fact store.
-- Conflating the two would make "is it done yet?" a query over provenance
-- strings.

CREATE TABLE IF NOT EXISTS obligations (
  id             TEXT PRIMARY KEY,
  kind           TEXT NOT NULL,           -- ERRATUM | REPRINT
  system_id      TEXT NOT NULL,
  channel_id     TEXT NOT NULL,
  listing_id     TEXT NOT NULL,
  entity_id      TEXT NOT NULL,
  attribute_path TEXT NOT NULL,
  incident_id    TEXT NOT NULL,
  opened_at      TEXT NOT NULL,
  due_by         TEXT,
  status         TEXT NOT NULL,           -- OPEN | DISCHARGED | VOID
  detail         TEXT NOT NULL DEFAULT '{}',
  discharged_by  TEXT,
  discharged_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_obligations_open ON obligations (status, system_id);
CREATE INDEX IF NOT EXISTS idx_obligations_listing ON obligations (listing_id);

-- ---------------------------------------------------------------------------
-- Release decisions - the second gate
-- ---------------------------------------------------------------------------
-- Deliberately NOT a row in `approvals` with a stage column. `commit_plan`
-- reads the newest approval for an incident and tests only that its decision
-- is APPROVE - so a release recorded there would, by itself, satisfy the
-- resolution gate. The feature meant to add a second approval would have
-- removed the first one.

CREATE TABLE IF NOT EXISTS releases (
  id           TEXT PRIMARY KEY,
  incident_id  TEXT NOT NULL,
  scenario_id  TEXT NOT NULL,
  decision     TEXT NOT NULL,             -- APPROVE | REJECT
  actor        TEXT NOT NULL,
  comment      TEXT NOT NULL DEFAULT '',
  decided_at   TEXT NOT NULL,
  redactions   TEXT NOT NULL DEFAULT '[]' -- the listing:path pairs being released
);

CREATE INDEX IF NOT EXISTS idx_releases_incident
  ON releases (incident_id, scenario_id, decided_at);

-- ---------------------------------------------------------------------------
-- Onboarding suggestions - a proposal for a missing value, and its decision
-- ---------------------------------------------------------------------------
-- Almost nothing in this schema stores a judgement; verdicts, stages and
-- readiness are all recomputed on read so they cannot drift from the record.
-- This one is stored, and the reason is narrow: a category manager approves
-- *the exact value they were shown*. The proposal comes from a model reading
-- retrieved passages, so recomputing it on the next read can legitimately
-- produce a different number - and a queue that re-derived its rows would let
-- somebody approve 65 W and write 68 W. What is stored is therefore the
-- proposal, not a conclusion about the product: the verdict beside it is still
-- computed from the facts every time.
--
-- `reasons` is the evidence that produced `confidence` - the cited passage,
-- the sibling and category values that agreed, the past decisions that agreed.
-- It is what the manager reads, and it is why the score is composed from named
-- parts rather than taken from a model's self-report.

CREATE TABLE IF NOT EXISTS onboarding_suggestions (
  id              TEXT PRIMARY KEY,       -- SUG-<hex12>
  submission_id   TEXT NOT NULL,
  entity_id       TEXT NOT NULL,
  attribute_path  TEXT NOT NULL,
  proposed        TEXT NOT NULL,          -- JSON: the value itself
  confidence      REAL NOT NULL,
  reasons         TEXT NOT NULL DEFAULT '[]',   -- JSON evidence rows
  safety_class    INTEGER NOT NULL DEFAULT 0,
  citation        TEXT NOT NULL DEFAULT '{}',   -- JSON, when a passage was read
  created_at      TEXT NOT NULL,          -- simulated clock, like every fact
  route           TEXT NOT NULL,          -- AUTONOMOUS | HUMAN
  threshold       REAL NOT NULL,          -- what it was judged against
  decision        TEXT,                   -- APPROVE | REJECT | RECTIFY
  decided_by      TEXT,
  decided_at      TEXT,
  decided_value   TEXT,                   -- JSON, set on RECTIFY
  comment         TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_suggestions_submission
  ON onboarding_suggestions (submission_id, created_at);
CREATE INDEX IF NOT EXISTS idx_suggestions_open
  ON onboarding_suggestions (decision, route);
-- What `history` reads back as a prior: the values a person has settled on for
-- this attribute before.
CREATE INDEX IF NOT EXISTS idx_suggestions_path
  ON onboarding_suggestions (attribute_path, decision);
-- One live proposal per field per bundle. A second assessment of the same
-- batch must refresh the row rather than stack a second decision beside it.
CREATE UNIQUE INDEX IF NOT EXISTS uq_suggestion_open
  ON onboarding_suggestions (submission_id, entity_id, attribute_path);
