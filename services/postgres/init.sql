-- Initialize pgvector extension for Mneme
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Mneme schema (from aletheia-mneme/migrations/001_init.sql)
CREATE TABLE IF NOT EXISTS namespaces (
  id                          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  email                       TEXT,
  owner                       TEXT,
  name                        TEXT,
  tier                        TEXT NOT NULL DEFAULT 'free',
  stripe_customer_id          TEXT,
  stripe_subscription_id      TEXT,
  request_count_current_month INTEGER DEFAULT 0,
  created_at                  TIMESTAMP DEFAULT NOW(),
  is_active                   BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS api_keys (
  id           TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  namespace_id TEXT NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
  key_hash     TEXT NOT NULL UNIQUE,
  key_prefix   TEXT NOT NULL,
  created_at   TIMESTAMP DEFAULT NOW(),
  revoked_at   TIMESTAMP,
  last_used    TIMESTAMP,
  expires_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memories (
  id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  namespace_id    TEXT NOT NULL REFERENCES namespaces(id),
  key             TEXT NOT NULL,
  value           TEXT NOT NULL,
  category        TEXT NOT NULL DEFAULT 'general',
  source          TEXT DEFAULT 'user',
  confidence      FLOAT DEFAULT 1.0,
  content_hash    TEXT,
  embedding_model TEXT DEFAULT 'text-embedding-3-small',
  version         INTEGER DEFAULT 1,
  last_updated    TIMESTAMP DEFAULT NOW(),
  last_accessed   TIMESTAMP DEFAULT NOW(),
  access_count    INTEGER DEFAULT 0,
  expires_at      TIMESTAMP,
  is_deleted      BOOLEAN DEFAULT FALSE,
  -- CRS-specific columns
  crs_embedding   vector(384),
  r_ratio         DOUBLE PRECISION,
  shi             DOUBLE PRECISION,
  UNIQUE(namespace_id, key)
);

CREATE TABLE IF NOT EXISTS memory_history (
  id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  memory_id   TEXT NOT NULL REFERENCES memories(id),
  old_value   TEXT NOT NULL,
  old_version INTEGER,
  changed_at  TIMESTAMP DEFAULT NOW(),
  changed_by  TEXT DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS memory_relationships (
  id           TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  namespace_id TEXT NOT NULL,
  from_key     TEXT NOT NULL,
  to_key       TEXT NOT NULL,
  rel_type     TEXT NOT NULL,
  created_at   TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sync_log (
  id             TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  namespace_id   TEXT NOT NULL,
  direction      TEXT NOT NULL,
  memory_count   INTEGER,
  target_url     TEXT,
  status         TEXT,
  helios_receipt TEXT,
  created_at     TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS processed_events (
  id TEXT PRIMARY KEY,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Seed CRS namespace
INSERT INTO namespaces (id, owner, name, tier, created_at)
VALUES ('ns_crs', 'crs', 'CRS Personal', 'personal', NOW())
ON CONFLICT (id) DO NOTHING;
