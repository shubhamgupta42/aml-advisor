"""Hybrid retriever: BM25 lexical + dense vector, fused via reciprocal-rank fusion,
then reranked with a cross-encoder.

Why hybrid:
- Dense vectors capture meaning ("structuring" ~ "round-denomination cash deposits")
  but can miss exact-ID lookups ("R168", "MDD-002 §4.2"), where lexical wins.
- BM25 captures exact tokens (rule IDs, section refs) but misses paraphrase.
- We run both, fuse with RRF (k=60), then take top-N for reranking.

Why a cross-encoder reranker (answer to Q7):
- Bi-encoders (the embedder) score query and passage independently — cheap, but
  no token-level interaction.
- Cross-encoders read query+passage together, producing a relevance score that's
  far closer to a human relevance judgment. We pay the cost on only the top-N
  (default 20), not on the whole corpus.
- bge-reranker-base typically lifts MRR@5 by 10-25 points over hybrid-alone.

Design note: we don't trust any single retriever. The eval harness measures
Hit@k and MRR at three stages — vector-only, hybrid (RRF), hybrid+rerank — so
we can show the contribution of each component, not just the final number.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Sequence

from .chunker import Chunk, chunk_directories
from .vector_store import vector_search


RRF_K = 60
DEFAULT_RERANKER = "BAAI/bge-reranker-base"
MDD_DIR_DEFAULT = "./data/mdds"
REG_DIR_DEFAULT = "./data/regulatory"


@dataclass
class RetrievalHit:
    chunk_id: str
    text: str
    section_ref: str
    doc_id: str
    rule_id: str
    score: float
    score_vector: float = 0.0
    score_bm25: float = 0.0
    score_rerank: float = 0.0
    jurisdiction: str = ""
    source_type: str = ""

    def to_citation(self) -> str:
        return self.section_ref


def _corpus_dirs(mdd_dir: str | None) -> list[str]:
    """Return the list of source directories to load for BM25 / corpus caches."""
    m = mdd_dir or os.environ.get("MDD_DIR", MDD_DIR_DEFAULT)
    r = os.environ.get("REG_DIR", REG_DIR_DEFAULT)
    return [m, r]


@lru_cache(maxsize=1)
def _load_corpus(dirs_key: str) -> list[Chunk]:
    dirs = dirs_key.split("|")
    return chunk_directories(dirs)


@lru_cache(maxsize=1)
def _load_bm25(dirs_key: str):
    """Build a BM25 index over the in-memory chunk corpus (MDDs + regulatory)."""
    from rank_bm25 import BM25Okapi

    chunks = _load_corpus(dirs_key)
    tokenized = [_tokenize(c.text) for c in chunks]
    return BM25Okapi(tokenized), chunks


@lru_cache(maxsize=1)
def _load_reranker(model_name: str):
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name)


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenize, keep alphanumerics, preserve rule-ID-style tokens."""
    return re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower())


def bm25_search(
    query: str,
    k: int = 10,
    mdd_dir: str | None = None,
    where: dict | None = None,
) -> list[dict]:
    dirs = _corpus_dirs(mdd_dir)
    bm25, chunks = _load_bm25("|".join(dirs))

    scores = bm25.get_scores(_tokenize(query))
    order = scores.argsort()[::-1]

    hits: list[dict] = []
    for i in order:
        c = chunks[i]
        # Apply metadata filter (matches Chroma `where` semantics for equality).
        if where:
            skip = False
            for key, val in where.items():
                if c.metadata.get(key) != val:
                    skip = True
                    break
            if skip:
                continue
        hits.append(
            {
                "chunk_id": c.chunk_id,
                "text": c.text,
                "metadata": c.metadata,
                "score_bm25": float(scores[i]),
            }
        )
        if len(hits) >= k:
            break
    return hits


def _rrf_fuse(
    vector_hits: list[dict], bm25_hits: list[dict], k: int = RRF_K
) -> list[dict]:
    """Reciprocal-rank fusion. Returns hits sorted by fused score, descending."""
    fused: dict[str, dict] = {}

    for rank, h in enumerate(vector_hits):
        cid = h["chunk_id"]
        entry = fused.setdefault(cid, {**h, "score_fused": 0.0, "score_bm25": 0.0})
        entry["score_fused"] += 1.0 / (k + rank + 1)
        entry["score_vector"] = h.get("score_vector", 0.0)

    for rank, h in enumerate(bm25_hits):
        cid = h["chunk_id"]
        if cid in fused:
            fused[cid]["score_fused"] += 1.0 / (k + rank + 1)
            fused[cid]["score_bm25"] = h.get("score_bm25", 0.0)
        else:
            fused[cid] = {
                **h,
                "score_fused": 1.0 / (k + rank + 1),
                "score_vector": 0.0,
            }

    return sorted(fused.values(), key=lambda x: x["score_fused"], reverse=True)


def _rerank(query: str, hits: list[dict], top_k: int, model_name: str) -> list[dict]:
    """Score (query, passage) pairs with a cross-encoder; return top_k."""
    if not hits:
        return []
    model = _load_reranker(model_name)
    pairs = [(query, h["text"]) for h in hits]
    scores = model.predict(pairs, show_progress_bar=False)
    for h, s in zip(hits, scores):
        h["score_rerank"] = float(s)
    return sorted(hits, key=lambda x: x["score_rerank"], reverse=True)[:top_k]


def retrieve(
    query: str,
    top_k: int = 5,
    fusion_k: int = 20,
    use_rerank: bool = True,
    mdd_dir: str | None = None,
    reranker_model: str = DEFAULT_RERANKER,
    where: dict | None = None,
) -> list[RetrievalHit]:
    """Full pipeline: hybrid retrieval + (optional) cross-encoder rerank.

    Parameters
    ----------
    top_k : int
        Final number of hits to return (post-rerank).
    fusion_k : int
        How many candidates to pull from each retriever before fusion / rerank.
        Larger gives the reranker more to work with at the cost of latency.
    use_rerank : bool
        Set False to ablate the reranker — used by the eval harness.
    where : dict | None
        Metadata equality filter, e.g. {"jurisdiction": "IN"}. Applied to both
        the vector search (native Chroma filter) and the BM25 scan. Falls back
        to unfiltered retrieval if the filter would return zero hits.
    """
    v_hits = vector_search(query, k=fusion_k, where=where)
    b_hits = bm25_search(query, k=fusion_k, mdd_dir=mdd_dir, where=where)

    # Fallback: if the filter is too strict (e.g. an OOD country), do unfiltered
    # so we can still refuse from context rather than empty out silently.
    if where and not v_hits and not b_hits:
        v_hits = vector_search(query, k=fusion_k)
        b_hits = bm25_search(query, k=fusion_k, mdd_dir=mdd_dir)

    fused = _rrf_fuse(v_hits, b_hits)[:fusion_k]

    if use_rerank:
        final = _rerank(query, fused, top_k=top_k, model_name=reranker_model)
    else:
        final = fused[:top_k]

    out: list[RetrievalHit] = []
    for h in final:
        meta = h["metadata"]
        score = h.get("score_rerank") if use_rerank else h.get("score_fused", 0.0)
        out.append(
            RetrievalHit(
                chunk_id=h["chunk_id"],
                text=h["text"],
                section_ref=meta.get("section_ref", ""),
                doc_id=meta.get("doc_id", ""),
                rule_id=meta.get("rule_id", ""),
                score=float(score or 0.0),
                score_vector=float(h.get("score_vector", 0.0)),
                score_bm25=float(h.get("score_bm25", 0.0)),
                score_rerank=float(h.get("score_rerank", 0.0)),
                jurisdiction=meta.get("jurisdiction", "") or "",
                source_type=meta.get("source_type", "") or "",
            )
        )
    return out
