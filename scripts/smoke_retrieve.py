"""Smoke test the retrieval pipeline against a handful of eval questions.

Usage (after `python scripts/ingest_mdds.py`):
    python scripts/smoke_retrieve.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.rag.retriever import retrieve  # noqa: E402


SMOKE_QUESTIONS = [
    "What is the lookback period for the Cash Structuring rule?",
    "Why was the N minimum for the structuring rule set to 3 rather than 2?",
    "What is the debit-ratio threshold in MDD-003 and why was it chosen?",
    "What customer segments are carved out of the Rapid Movement rule?",
    "What is the 3x expected-volume multiplier in MDD-002 and where does it come from?",
]


def main() -> int:
    for q in SMOKE_QUESTIONS:
        print("=" * 80)
        print(f"Q: {q}")
        hits = retrieve(q, top_k=3)
        for i, h in enumerate(hits, 1):
            preview = h.text.replace("\n", " ")[:140]
            print(
                f"  [{i}] {h.section_ref:<28}  "
                f"rerank={h.score_rerank:+.2f}  vec={h.score_vector:+.2f}  bm25={h.score_bm25:+.2f}"
            )
            print(f"      {preview}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
