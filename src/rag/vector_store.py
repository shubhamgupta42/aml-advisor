"""pgvector-backed vector store.

Why pgvector:

- **Production reality.** Tier-1 banks running AML/KYC workloads pick pgvector on
  Aurora Postgres (or OpenSearch k-NN) — never a managed SaaS vector DB. The
  reasons are hard blockers, not preferences: BaFin / FCA / MAS / RBI data-
  residency rules; TPRM overhead for a new vendor; embedding-inversion attacks
  that make "just embeddings, safe to send anywhere" naive. Managed vector DBs
  like Pinecone are used by AI startups, not by regulated financial institutions.

- **Same engine local ↔ prod.** Postgres 16 in docker-compose is byte-identical to
  Aurora Postgres 16 with the pgvector extension. Nothing about the query
  planner, indexing, or SQL surface differs. That means every optimisation we
  make locally (HNSW `m` / `ef_search` tuning, metadata pre-filter) translates
  directly.

- **Transactional consistency.** In a real bank, when a source MDD gets updated
  or redacted, the chunk row AND its embedding must move together — otherwise
  auditors flag it. In pgvector that's a single transaction. In a separate
  vector DB it's an eventual-consistency problem.

- **No new datastore for the compliance team to review.** Adding a vector
  extension to an existing Postgres cluster is a schema change. Adding a whole
  new datastore (Chroma / Pinecone / Qdrant) triggers a 3–9 month TPRM / InfoSec
  / DPIA cycle.

Trade-offs:
- pgvector caps around 10–50M vectors before latency starts to hurt.
- For 100M+ vectors or > 1000 QPS with sub-50ms p95, move to OpenSearch k-NN
  or self-hosted Qdrant on the bank's Kubernetes.
- pgvector has no BM25 built in — we handle lexical separately (rank_bm25 in
  `retriever.py`). If we ever needed hybrid-in-one-engine, that's the migration
  trigger for OpenSearch.
"""
from __future__ import annotations

import json
import os
from typing import Sequence

from .chunker import Chunk
from .embedder import embed_passages, embed_query


DEFAULT_DSN = "postgresql://aml:aml@localhost:5432/aml_advisor"


def _dsn() -> str:
    return os.environ.get("PG_DSN", DEFAULT_DSN)


def _connect():
    """Lazy import so the module loads even if psycopg isn't installed yet."""
    import psycopg
    from pgvector.psycopg import register_vector

    conn = psycopg.connect(_dsn())
    register_vector(conn)
    return conn


def build_store(
    chunks: Sequence[Chunk],
    persist_dir: str | None = None,  # kept for signature compat; ignored
    reset: bool = True,
) -> None:
    """Embed and upsert all chunks into pgvector.

    Parameters
    ----------
    chunks : sequence of Chunk
        The chunked corpus produced by chunk_directories().
    persist_dir : str | None
        Ignored. Kept in the signature so the ingest script needs no changes.
        Location is controlled by the PG_DSN env var.
    reset : bool
        If True, TRUNCATE the chunks table before upserting. Matches the
        previous Chroma-reset semantics.
    """
    if not chunks:
        return

    texts = [c.text for c in chunks]
    embeddings = embed_passages(texts)  # shape (N, 384), L2-normalised

    with _connect() as conn, conn.cursor() as cur:
        if reset:
            cur.execute("TRUNCATE TABLE chunks")

        rows = []
        for c, emb in zip(chunks, embeddings):
            meta = dict(c.metadata)
            rows.append(
                (
                    c.chunk_id,
                    meta.get("doc_id") or c.doc_id,
                    c.section_ref,
                    meta.get("rule_id"),
                    meta.get("jurisdiction") or None,
                    meta.get("source_type") or "internal_mdd",
                    c.text,
                    json.dumps(meta),
                    emb.tolist(),
                )
            )

        cur.executemany(
            """
            INSERT INTO chunks
                (chunk_id, doc_id, section_ref, rule_id, jurisdiction,
                 source_type, text, metadata, embedding)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::vector)
            ON CONFLICT (chunk_id) DO UPDATE SET
                doc_id       = EXCLUDED.doc_id,
                section_ref  = EXCLUDED.section_ref,
                rule_id      = EXCLUDED.rule_id,
                jurisdiction = EXCLUDED.jurisdiction,
                source_type  = EXCLUDED.source_type,
                text         = EXCLUDED.text,
                metadata     = EXCLUDED.metadata,
                embedding    = EXCLUDED.embedding
            """,
            rows,
        )
        conn.commit()


def _build_where_clause(where: dict | None) -> tuple[str, list]:
    """Translate a {"jurisdiction": "IN"}-style filter into a SQL WHERE clause.

    Uses the dedicated columns (jurisdiction, source_type, rule_id, doc_id) when
    the key matches one; falls back to the JSONB `metadata @> ...` operator so
    arbitrary metadata keys still work.
    """
    if not where:
        return "", []

    columns = {"jurisdiction", "source_type", "rule_id", "doc_id"}
    clauses: list[str] = []
    params: list = []
    jsonb_extras: dict = {}

    for key, val in where.items():
        if key in columns:
            clauses.append(f"{key} = %s")
            params.append(val)
        else:
            jsonb_extras[key] = val

    if jsonb_extras:
        clauses.append("metadata @> %s::jsonb")
        params.append(json.dumps(jsonb_extras))

    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def vector_search(
    query: str,
    k: int = 10,
    persist_dir: str | None = None,  # signature compat; ignored
    where: dict | None = None,
) -> list[dict]:
    """Top-k cosine-similarity search with optional metadata pre-filter.

    Cosine distance is `embedding <=> query` in pgvector; we convert to a
    similarity score (1 - distance) so the fusion step downstream keeps its
    higher-is-better invariant.
    """
    q_vec = embed_query(query)  # shape (384,), L2-normalised

    where_sql, where_params = _build_where_clause(where)

    sql = f"""
        SELECT chunk_id,
               doc_id,
               section_ref,
               rule_id,
               jurisdiction,
               source_type,
               text,
               metadata,
               1 - (embedding <=> %s::vector) AS score
        FROM chunks
        {where_sql}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    params = [q_vec.tolist(), *where_params, q_vec.tolist(), k]

    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    hits: list[dict] = []
    for chunk_id, doc_id, section_ref, rule_id, juris, stype, text, meta, score in rows:
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        meta = dict(meta or {})
        meta.setdefault("doc_id", doc_id)
        meta.setdefault("section_ref", section_ref)
        if rule_id:
            meta.setdefault("rule_id", rule_id)
        if juris:
            meta.setdefault("jurisdiction", juris)
        if stype:
            meta.setdefault("source_type", stype)

        hits.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "metadata": meta,
                "score_vector": float(score),
            }
        )
    return hits
