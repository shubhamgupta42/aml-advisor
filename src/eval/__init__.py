"""Evaluation framework for AML Advisor.

Metrics computed on each run:

**Retrieval** (deterministic, computed pre-LLM):
- Hit@k     — fraction of questions where any retrieved chunk's section_ref
              matches the gold_source.
- MRR       — mean reciprocal rank of the first correct hit.

**Generation** (mix of deterministic + LLM-judge):
- Citation accuracy — every [section_ref] in the answer must appear in the
                      retrieved chunks. Deterministic; no LLM needed.
- Faithfulness     — every factual claim grounded in retrieved context.
                     LLM-judge (Claude on a separate call). Cross-validate
                     a subset against human labels for kappa >= 0.8 before
                     trusting unattended.
- Refusal correctness — for OOD questions, did the system refuse?

**System**:
- Latency p50/p95/p99
- Cost per query (from token usage)

Design note: this file is the answer to Q8 (how to evaluate RAG) and Q5
(does chunk size affect performance). The ablations in run_baseline.py
(use_rerank=True/False) directly produce comparable numbers.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass


# Citation-format pattern used in the prompt
CITE_RE = re.compile(r"\[((?:MDD-\d+|REG-[A-Z]+-[A-Z0-9\-]+|LR-[A-Z]+-[A-Z0-9\-]+)[^\]]*)\]")


@dataclass
class RetrievalScore:
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mrr: float


def _normalize_ref(ref: str) -> str:
    """Normalize a section reference to its (doc_family, section) form.

    Examples:
      'MDD-001 §4 (Detection Logic)'   → 'MDD-001 §4'
      'MDD-001-STRUCT-v3.2 §4'         → 'MDD-001 §4'
      'MDD-001-STRUCT-v3.2 (PREAMBLE)' → 'MDD-001 PREAMBLE'

    This makes retrieved chunks (which carry the full versioned doc ID) match
    eval-set gold refs (which use the short doc family like 'MDD-001').
    """
    ref = ref.strip()
    # Drop any trailing parenthetical, but capture PREAMBLE/etc. before doing so
    m_paren = re.search(r"\(([A-Z_]+)\)$", ref)
    paren_tag = m_paren.group(1) if m_paren else None
    ref = re.sub(r"\s*\(.+\)$", "", ref).strip()

    # Collapse versioned doc IDs to the short family form (MDD-001-...-vX.Y → MDD-001)
    ref = re.sub(r"^(MDD-\d+)-[A-Z0-9\-\.v]+", r"\1", ref)

    if paren_tag and "§" not in ref:
        ref = f"{ref} {paren_tag}"
    return ref


def _ref_matches_gold(retrieved_ref: str, gold_source: str) -> bool:
    """True if the retrieved chunk's normalized ref equals any gold sub-ref.

    Gold may be a compound like 'MDD-001 §4 + §7' — we match if the retrieved
    ref equals any individual section in the gold.
    """
    if not gold_source:
        return False
    r = _normalize_ref(retrieved_ref)

    # Split compound gold refs on '+' into individual refs, normalize each
    gold_parts = [_normalize_ref(p) for p in re.split(r"\s*\+\s*", gold_source)]

    # Also expand 'MDD-001 §4 + §7' → ['MDD-001 §4', 'MDD-001 §7']
    expanded: list[str] = []
    last_doc = None
    for part in gold_parts:
        m = re.match(r"^(MDD-\d+|LR-[A-Z\-]+\d+)\s+(§\d+(?:\.\d+)*|[A-Z_]+)$", part)
        if m:
            last_doc = m.group(1)
            expanded.append(part)
        elif part.startswith("§") and last_doc:
            expanded.append(f"{last_doc} {part}")
        else:
            expanded.append(part)

    return any(r == g or g in r for g in expanded)


def score_retrieval(eval_items: list[dict], all_hits: list[list[dict]]) -> RetrievalScore:
    """eval_items[i] has 'gold_source'; all_hits[i] is the ranked chunk list."""
    hits_1, hits_3, hits_5, rrs = [], [], [], []
    for item, hits in zip(eval_items, all_hits):
        gold = item.get("gold_source")
        if not gold:
            continue
        refs = [h.get("section_ref", "") for h in hits]
        first_hit = next(
            (i for i, r in enumerate(refs) if _ref_matches_gold(r, gold)), None
        )
        hits_1.append(1.0 if first_hit == 0 else 0.0)
        hits_3.append(1.0 if first_hit is not None and first_hit < 3 else 0.0)
        hits_5.append(1.0 if first_hit is not None and first_hit < 5 else 0.0)
        rrs.append(1.0 / (first_hit + 1) if first_hit is not None else 0.0)

    n = len(hits_1) or 1
    return RetrievalScore(
        hit_at_1=sum(hits_1) / n,
        hit_at_3=sum(hits_3) / n,
        hit_at_5=sum(hits_5) / n,
        mrr=sum(rrs) / n,
    )


def score_citation_accuracy(answer: str, retrieved_refs: list[str]) -> float:
    """Every [section_ref] in the answer must appear in the retrieved set.

    Strict comparison: §4.2 does NOT match §4 (subsection-level precision matters
    for AML auditing — a §4.2 citation that points to §4 misleads the auditor).
    """
    cited = list(dict.fromkeys(CITE_RE.findall(answer)))
    if not cited:
        return 0.0
    norm_retrieved = {_normalize_ref(r) for r in retrieved_refs}
    matches = sum(1 for c in cited if _normalize_ref(c) in norm_retrieved)
    return matches / len(cited)


def score_refusal(answer: str) -> bool:
    """Did the model emit a refusal? Loose match on the canonical phrase."""
    a = answer.lower()
    return (
        "i don't have that information" in a
        or "not in my current corpus" in a
        or "i don't have access" in a
        or "i won't share" in a
    )


def latency_percentiles(latencies_ms: list[int]) -> dict:
    if not latencies_ms:
        return {"p50": 0, "p95": 0, "p99": 0, "mean": 0}
    sorted_l = sorted(latencies_ms)

    def pct(p: float) -> int:
        idx = int(round((p / 100) * (len(sorted_l) - 1)))
        return sorted_l[idx]

    return {
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "mean": int(statistics.mean(sorted_l)),
    }


def estimate_cost_usd(usage: dict, model: str) -> float:
    """Rough per-call cost. Numbers are illustrative — update from current pricing.

    `model` may be prefixed with the provider, e.g. 'groq:llama-3.3-70b-versatile'.
    Groq's free tier is $0; paid-tier rates are listed for what-if comparison.
    """
    # Strip provider prefix if present
    key = model.split(":", 1)[-1] if ":" in model else model
    rates = {
        "claude-sonnet-4-6": (3.00, 15.00),   # $/M in, $/M out
        "claude-haiku-4-5-20251001": (0.80, 4.00),
        "claude-opus-4-7": (15.00, 75.00),
        # Groq published rates (paid tier — free tier is $0)
        "llama-3.3-70b-versatile": (0.59, 0.79),
        "llama-3.1-8b-instant": (0.05, 0.08),
        "mixtral-8x7b-32768": (0.24, 0.24),
    }
    in_rate, out_rate = rates.get(key, (0.0, 0.0))
    return (
        usage.get("input_tokens", 0) * in_rate / 1_000_000
        + usage.get("output_tokens", 0) * out_rate / 1_000_000
    )
