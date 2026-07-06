"""Embedding model wrapper.

Why bge-small-en-v1.5:
- 384-dim, ~33M params, runs on CPU in ~5ms/chunk.
- Strong MTEB scores for retrieval (beats text-embedding-ada-002 on most retrieval tasks).
- Open-weight — no API call, no per-query cost, deterministic.

Design note: this is the answer to Q6 (why vector DB if we have other DBs):
embeddings turn fuzzy semantic similarity into k-NN lookup. The Rule Catalog
and RTCA are NOT in this store — they're structured JSON queried via deterministic
tools, because for them "what's the threshold for R168 in India" is a key lookup,
not a similarity search. Right tool for the right job.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Sequence

import numpy as np


DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _load_model(model_name: str):
    """Lazy-load the sentence-transformer (cached after first call)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def embed_passages(
    texts: Sequence[str],
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 32,
) -> np.ndarray:
    """Embed document chunks. Returns (N, D) float32 array."""
    model = _load_model(model_name)
    return np.asarray(
        model.encode(
            list(texts),
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        ),
        dtype=np.float32,
    )


def embed_query(query: str, model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """Embed a single query. BGE models recommend a query-specific prefix."""
    model = _load_model(model_name)
    prefixed = QUERY_PREFIX + query
    return np.asarray(
        model.encode(
            [prefixed],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )[0],
        dtype=np.float32,
    )
