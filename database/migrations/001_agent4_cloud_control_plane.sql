-- Agent 4 cloud control-plane bootstrap.
-- Additive only: no destructive DDL/DML and no local database is touched.
-- The embedding dimension matches config/selection_cloud.yaml (4096).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS cloud;

CREATE TABLE IF NOT EXISTS cloud.schema_migrations (
    version text PRIMARY KEY,
    checksum_sha256 char(64) NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cloud.tenants (
    tenant_id text PRIMARY KEY,
    display_name text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'archived')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cloud.tenant_members (
    tenant_id text NOT NULL REFERENCES cloud.tenants (tenant_id),
    user_id text NOT NULL,
    role text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id, role)
);

CREATE TABLE IF NOT EXISTS cloud.metric_catalog (
    metric_id text NOT NULL,
    catalog_version text NOT NULL,
    definition jsonb NOT NULL,
    status text NOT NULL CHECK (status IN ('approved', 'draft', 'blocked')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (metric_id, catalog_version)
);

CREATE TABLE IF NOT EXISTS cloud.access_policies (
    tenant_id text NOT NULL REFERENCES cloud.tenants (tenant_id),
    policy_version text NOT NULL,
    policy_hash text NOT NULL,
    policy jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, policy_version)
);

CREATE TABLE IF NOT EXISTS cloud.warehouse_artifacts (
    artifact_id uuid PRIMARY KEY,
    tenant_id text NOT NULL REFERENCES cloud.tenants (tenant_id),
    object_key text NOT NULL,
    sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    schema_version text NOT NULL,
    source_revision text NOT NULL,
    generated_at timestamptz NOT NULL,
    provider_version text,
    immutable boolean NOT NULL DEFAULT true CHECK (immutable),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, sha256)
);

CREATE TABLE IF NOT EXISTS cloud.query_audits (
    audit_id uuid PRIMARY KEY,
    request_id text NOT NULL UNIQUE,
    trace_id text NOT NULL,
    tenant_id text NOT NULL REFERENCES cloud.tenants (tenant_id),
    user_id text NOT NULL,
    policy_hash text NOT NULL,
    status text NOT NULL,
    metric_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    latency_ms numeric(12, 3),
    error_code text,
    data_watermark text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS query_audits_tenant_created_idx
    ON cloud.query_audits (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS cloud.provider_call_summaries (
    call_id uuid PRIMARY KEY,
    request_id text NOT NULL,
    tenant_id text NOT NULL REFERENCES cloud.tenants (tenant_id),
    provider text NOT NULL,
    model text NOT NULL,
    stage text NOT NULL,
    status text NOT NULL,
    latency_ms numeric(12, 3),
    retryable boolean NOT NULL DEFAULT false,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS provider_calls_request_idx
    ON cloud.provider_call_summaries (request_id, created_at);

CREATE TABLE IF NOT EXISTS cloud.clarification_sessions (
    session_id text PRIMARY KEY,
    tenant_id text NOT NULL REFERENCES cloud.tenants (tenant_id),
    user_id text NOT NULL,
    policy_hash text NOT NULL,
    state jsonb NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS clarification_sessions_expiry_idx
    ON cloud.clarification_sessions (tenant_id, expires_at);

CREATE TABLE IF NOT EXISTS cloud.retrieval_documents (
    document_id uuid PRIMARY KEY,
    tenant_id text NOT NULL REFERENCES cloud.tenants (tenant_id),
    corpus_id text NOT NULL,
    source_object_key text,
    content_sha256 char(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    visibility text NOT NULL,
    model_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, corpus_id, content_sha256, model_version)
);

CREATE TABLE IF NOT EXISTS cloud.retrieval_chunks (
    chunk_id uuid PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES cloud.retrieval_documents (document_id),
    tenant_id text NOT NULL REFERENCES cloud.tenants (tenant_id),
    content_text text,
    content_object_key text,
    content_sha256 char(64) NOT NULL CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

-- Do not populate this table with the full legal corpus on Neon Free.
-- Tenant/corpus/model columns are mandatory so vector search cannot bypass policy scope.
CREATE TABLE IF NOT EXISTS cloud.retrieval_embeddings (
    chunk_id uuid PRIMARY KEY REFERENCES cloud.retrieval_chunks (chunk_id),
    tenant_id text NOT NULL REFERENCES cloud.tenants (tenant_id),
    corpus_id text NOT NULL,
    embedding vector(4096) NOT NULL,
    model_id text NOT NULL,
    model_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS retrieval_embeddings_scope_idx
    ON cloud.retrieval_embeddings (tenant_id, corpus_id, model_id, model_version);
