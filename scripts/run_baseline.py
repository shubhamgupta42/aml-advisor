"""Baseline RAG eval: run all MDD-answerable questions in eval_set.json,
score retrieval and generation, write results + summary to eval_runs/.

Usage:
    python scripts/run_baseline.py                # full run, with rerank
    python scripts/run_baseline.py --no-rerank    # ablation: retrieval only
    python scripts/run_baseline.py --retrieval-only   # skip the LLM call
    python scripts/run_baseline.py --limit 5      # smoke test

Run it with and without the reranker (--no-rerank) to quantify the ablation:
the delta on Hit@1 / MRR is the measured contribution of the cross-encoder.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env if present (looks in repo root)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.rag.retriever import retrieve  # noqa: E402
from src.eval import (  # noqa: E402
    estimate_cost_usd,
    latency_percentiles,
    score_citation_accuracy,
    score_refusal,
    score_retrieval,
)

# Which eval categories we expect this Day-1 RAG baseline to handle.
# Rule-catalog-only / rtca-only / multi-tool need the Day-2 agent layer.
MDD_ANSWERABLE_TYPES = {"mdd_only"}
REFUSAL_TYPES = {"ood_refusal"}


def load_eval_set(path: Path) -> list[dict]:
    return json.loads(path.read_text())["items"]


def run(args: argparse.Namespace) -> int:
    eval_path = ROOT / "data" / "ground_truth" / "eval_set.json"
    items = load_eval_set(eval_path)

    if args.types:
        wanted = set(args.types.split(","))
    else:
        wanted = MDD_ANSWERABLE_TYPES | REFUSAL_TYPES
    items = [it for it in items if it["question_type"] in wanted]
    if args.limit:
        items = items[: args.limit]

    print(f"[baseline] Evaluating {len(items)} questions  "
          f"(rerank={not args.no_rerank}, retrieval_only={args.retrieval_only})")

    out_dir = ROOT / "eval_runs"
    out_dir.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    tag = "rerank" if not args.no_rerank else "norerank"
    if args.retrieval_only:
        tag += "_retrievalonly"
    run_path = out_dir / f"baseline_{run_id}_{tag}.jsonl"
    summary_path = out_dir / f"baseline_{run_id}_{tag}_summary.json"

    all_hits: list[list[dict]] = []
    rows: list[dict] = []
    latencies: list[int] = []
    total_cost = 0.0

    for i, it in enumerate(items, 1):
        q = it["question"]
        t0 = time.perf_counter()
        hits = retrieve(q, top_k=5, use_rerank=not args.no_rerank)
        retrieval_ms = int((time.perf_counter() - t0) * 1000)

        hit_dicts = [
            {
                "chunk_id": h.chunk_id,
                "section_ref": h.section_ref,
                "score": h.score,
                "score_vector": h.score_vector,
                "score_bm25": h.score_bm25,
                "score_rerank": h.score_rerank,
            }
            for h in hits
        ]
        all_hits.append(hit_dicts)

        row: dict = {
            "id": it["id"],
            "question_type": it["question_type"],
            "question": q,
            "gold_source": it.get("gold_source"),
            "expected_refusal": it.get("expected_refusal", False),
            "retrieved_refs": [h.section_ref for h in hits],
            "retrieval_ms": retrieval_ms,
        }

        if not args.retrieval_only:
            from src.rag.generator import generate_answer

            t1 = time.perf_counter()
            gen = generate_answer(q, hits)
            gen_ms = int((time.perf_counter() - t1) * 1000)
            total_ms = retrieval_ms + gen_ms
            latencies.append(total_ms)
            cost = estimate_cost_usd(gen.usage, gen.model)
            total_cost += cost

            row.update(
                {
                    "answer": gen.answer,
                    "cited_refs": gen.cited_refs,
                    "model": gen.model,
                    "usage": gen.usage,
                    "cost_usd": round(cost, 6),
                    "gen_ms": gen_ms,
                    "total_ms": total_ms,
                    "citation_accuracy": score_citation_accuracy(
                        gen.answer, [h.section_ref for h in hits]
                    ),
                    "refused": score_refusal(gen.answer),
                }
            )
            tag_print = "REF" if row["refused"] else "ANS"
            print(
                f"  [{i:>2}/{len(items)}] {it['id']} {it['question_type']:<14} "
                f"{tag_print}  ret={retrieval_ms}ms gen={gen_ms}ms "
                f"cite={row['citation_accuracy']:.2f}  ${cost:.4f}"
            )
        else:
            latencies.append(retrieval_ms)
            print(f"  [{i:>2}/{len(items)}] {it['id']} {it['question_type']:<14} ret={retrieval_ms}ms")

        rows.append(row)

    # Write per-question results (JSONL)
    with run_path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    # Compute aggregate metrics
    retrieval_score = score_retrieval(items, all_hits)
    lat = latency_percentiles(latencies)

    # Generation-side aggregates (only when we actually called the LLM)
    gen_rows = [r for r in rows if "answer" in r]
    answerable = [r for r in gen_rows if not r["expected_refusal"]]
    refusal_rows = [r for r in gen_rows if r["expected_refusal"]]

    citation_acc = (
        sum(r["citation_accuracy"] for r in answerable) / len(answerable)
        if answerable else None
    )
    refusal_precision = (
        sum(1 for r in refusal_rows if r["refused"]) / len(refusal_rows)
        if refusal_rows else None
    )
    answerable_refused = sum(1 for r in answerable if r["refused"])

    summary = {
        "run_id": run_id,
        "tag": tag,
        "n_questions": len(items),
        "use_rerank": not args.no_rerank,
        "retrieval_only": args.retrieval_only,
        "retrieval": {
            "hit_at_1": round(retrieval_score.hit_at_1, 3),
            "hit_at_3": round(retrieval_score.hit_at_3, 3),
            "hit_at_5": round(retrieval_score.hit_at_5, 3),
            "mrr": round(retrieval_score.mrr, 3),
        },
        "generation": {
            "citation_accuracy_mean": (
                round(citation_acc, 3) if citation_acc is not None else None
            ),
            "refusal_precision": (
                round(refusal_precision, 3) if refusal_precision is not None else None
            ),
            "answerable_incorrectly_refused": answerable_refused,
            "n_answerable": len(answerable),
            "n_refusal_expected": len(refusal_rows),
        },
        "latency_ms": lat,
        "cost_usd_total": round(total_cost, 4),
        "cost_usd_per_query": round(total_cost / max(len(gen_rows), 1), 6),
    }
    summary_path.write_text(json.dumps(summary, indent=2))

    print("\n" + "=" * 80)
    print(f"[baseline] {tag.upper()}  n={len(items)}")
    print(f"  Retrieval:  Hit@1={summary['retrieval']['hit_at_1']:.2f}  "
          f"Hit@3={summary['retrieval']['hit_at_3']:.2f}  "
          f"Hit@5={summary['retrieval']['hit_at_5']:.2f}  "
          f"MRR={summary['retrieval']['mrr']:.2f}")
    if not args.retrieval_only:
        print(f"  Generation: citation_acc={summary['generation']['citation_accuracy_mean']}  "
              f"refusal_precision={summary['generation']['refusal_precision']}  "
              f"wrongly_refused={answerable_refused}/{len(answerable)}")
    print(f"  Latency:    p50={lat['p50']}ms  p95={lat['p95']}ms  p99={lat['p99']}ms")
    if not args.retrieval_only:
        print(f"  Cost:       ${summary['cost_usd_total']:.4f} total  "
              f"(${summary['cost_usd_per_query']:.4f}/q)")
    print(f"\n[baseline] Results: {run_path}")
    print(f"[baseline] Summary: {summary_path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-rerank", action="store_true",
                    help="Disable the cross-encoder reranker (ablation)")
    ap.add_argument("--retrieval-only", action="store_true",
                    help="Score retrieval only; skip the LLM call")
    ap.add_argument("--limit", type=int, default=0,
                    help="Run only the first N items (smoke test)")
    ap.add_argument("--types", type=str, default="",
                    help="Comma-separated question_types to include")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
