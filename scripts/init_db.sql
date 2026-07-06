-- AML Advisor — pgvector schema.
--
-- Run automatically by docker-compose on first container start (mounted into
-- /docker-entrypoint-initdb.d/). Also safe to run manually — every statement is
-- idempotent.
--
-- Design notes:
--
--   * `chunks.embedding` is `vector(384)` because we use bge-small-en-v1.5.
--     Switching to bge-base-en (768) or e5-large-v2 (1024) is a dimension change
--     + re-ingest. In prod we'd version the collection by embedding-model name.
--
--   * HNSW index (Hierarchical Navigable Small World) for approximate nearest
--     neighbour. `m=16, ef_construction=64` are pgvector's recommended defaults —
--     good recall at build cost we can afford on 100K-scale corpora.
--     Alternatives: `ivfflat` (faster build, lower recall) or exact scan (no
--     index — fine at < ~10K rows).
--
--   * `vector_cosine_ops` because our embeddings are L2-normalized (cosine ==
--     dot product on unit vectors). If we switch to un-normalized embeddings,
--     use `vector_l2_ops` instead.
--
--   * `metadata JSONB` + GIN index for jurisdiction / source_type filters.
--     This is the SQL equivalent of Chroma's `where={"jurisdiction": "IN"}`
--     pre-filter, but here it's the DB's job to plan the join with the ANN
--     search — much more optimisable than a Python-side filter.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id     TEXT PRIMARY KEY,
    doc_id       TEXT NOT NULL,
    section_ref  TEXT NOT NULL,
    rule_id      TEXT,
    jurisdiction TEXT,
    source_type  TEXT,
    text         TEXT NOT NULL,
    metadata     JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding    vector(384),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- HNSW index for cosine-similarity ANN search
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- GIN index on metadata for fast filtered lookup (jurisdiction, source_type, etc.)
CREATE INDEX IF NOT EXISTS chunks_metadata_gin
    ON chunks USING gin (metadata);

-- B-tree indexes on the common filter columns (jurisdiction / source_type) —
-- cheaper than the JSONB GIN path when the query is a simple equality.
CREATE INDEX IF NOT EXISTS chunks_jurisdiction_idx ON chunks (jurisdiction);
CREATE INDEX IF NOT EXISTS chunks_source_type_idx  ON chunks (source_type);
