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
  released_at   TEXT                      -- when the replayer made it visible
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
