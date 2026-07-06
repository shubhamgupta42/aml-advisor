"""Multi-tool agent eval — runs the full LangGraph agent on the slice of the eval
set that requires Rule Catalog + RTCA + multi-tool reasoning.

Usage:
    python scripts/run_agent_eval.py
    python scripts/run_agent_eval.py --limit 5
    python scripts/run_agent_eval.py --types rule_catalog_only,rtca_only,multi_tool

Metrics:
    - Tool-selection accuracy: required_tools ⊆ plan.tools  (router metric)
    - Tool-selection recall:   |required ∩ planned| / |required|
    - Tool-selection precision:|required ∩ planned| / |planned|
    - Answer non-empty rate
    - Citation count distribution
    - Step count distribution
    - Latency p50/p95/p99
    - Cost estimate (Groq paid rates)

Writes JSONL per-question results + JSON summary to eval_runs/.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.agents.graph import ask  # noqa: E402
from src.eval import estimate_cost_usd, latency_percentiles  # noqa: E402
from src.eval.groundedness import judge_groundedness  # noqa: E402
from src.rag.retriever import retrieve as rag_retrieve  # noqa: E402


AGENT_TYPES = {"rule_catalog_only", "rtca_only", "multi_tool"}

# Map eval-set tool names to graph tool names.
_TOOL_ALIASES = {
    "rule_catalog": "rule_catalog",
    "rtca": "rtca",
    "mdd_rag": "mdd_rag",
    "threshold_calc": "rule_catalog",  # threshold_calc is folded into rule_catalog
}


def _normalize_required(required: list[str]) -> set[str]:
    return {_TOOL_ALIASES.get(t, t) for t in required}


def load_eval_set(path: Path) -> list[dict]:
    return json.loads(path.read_text())["items"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="Smoke-test cap")
    ap.add_argument(
        "--types",
        default="rule_catalog_only,rtca_only,multi_tool",
        help="Comma-separated question_types",
    )
    ap.add_argument("--out-dir", default="eval_runs")
    ap.add_argument(
        "--groundedness",
        action="store_true",
        help="Run LLM-judge groundedness scoring on MDD-RAG answers. Adds latency + cost.",
    )
    args = ap.parse_args()

    types_filter = {t.strip() for t in args.types.split(",")}

    eval_path = ROOT / "data" / "ground_truth" / "eval_set.json"
    items = [q for q in load_eval_set(eval_path) if q["question_type"] in types_filter]
    if args.limit:
        items = items[: args.limit]

    print(f"Running multi-tool agent eval on {len(items)} questions ({sorted(types_filter)})…")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(exist_ok=True)
    jsonl_path = out_dir / f"agent_eval_{timestamp}.jsonl"
    summary_path = out_dir / f"agent_eval_{timestamp}_summary.json"

    per_q = []
    fjsonl = open(jsonl_path, "w", encoding="utf-8")

    for i, item in enumerate(items, 1):
        q = item["question"]
        required = _normalize_required(item.get("required_tools", []))
        print(f"[{i:>2}/{len(items)}] {item['id']} ({item['question_type']}) — {q[:70]}…")

        t0 = time.perf_counter()
        try:
            res = ask(q)
            err = None
        except Exception as e:
            res = None
            err = str(e)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        if res is None:
            row = {
                "id": item["id"],
                "question": q,
                "type": item["question_type"],
                "required_tools": sorted(required),
                "error": err,
                "latency_ms": latency_ms,
            }
        else:
            planned = set(res.plan.get("tools", []))
            inter = required & planned
            ts_accuracy = required.issubset(planned)  # all required were picked
            ts_recall = (len(inter) / len(required)) if required else 1.0
            ts_precision = (len(inter) / len(planned)) if planned else 0.0

            row = {
                "id": item["id"],
                "question": q,
                "type": item["question_type"],
                "required_tools": sorted(required),
                "planned_tools": sorted(planned),
                "ts_accuracy": ts_accuracy,
                "ts_recall": ts_recall,
                "ts_precision": ts_precision,
                "answer_nonempty": bool((res.answer or "").strip()),
                "citation_count": len(res.citations),
                "citations": res.citations,
                "step_count": res.step_count,
                "router_fallback": bool(res.plan.get("_fallback")),
                "answer": res.answer,
                "latency_ms": latency_ms,
                "stage_latency_ms": res.latency_ms,
                "errors": res.errors,
                "gold_answer": item.get("gold_answer", ""),
            }

            if args.groundedness and "mdd_rag" in planned and (res.answer or "").strip():
                # Re-retrieve to get the full chunk text (agent state only stores refs).
                country = res.plan.get("country")
                where = {"jurisdiction": country} if country else None
                try:
                    hits = rag_retrieve(q, top_k=5, where=where)
                    g = judge_groundedness(
                        answer=res.answer,
                        retrieved_texts=[h.text for h in hits],
                        retrieved_refs=[h.section_ref for h in hits],
                    )
                    row["groundedness"] = {
                        "faithfulness": g.faithfulness,
                        "n_claims": g.n_claims,
                        "n_supported": g.n_supported,
                        "n_contradicted": g.n_contradicted,
                        "n_unsupported": g.n_unsupported,
                        "judge_model": g.judge_model,
                    }
                except Exception as e:
                    row["groundedness_error"] = str(e)
        per_q.append(row)
        fjsonl.write(json.dumps(row, default=str) + "\n")
        fjsonl.flush()

    fjsonl.close()

    # ── Summary ────────────────────────────────────────────────────────────────
    completed = [r for r in per_q if "ts_accuracy" in r]
    n = len(completed)

    summary = {
        "timestamp": timestamp,
        "n_questions": len(per_q),
        "n_completed": n,
        "n_errored": len(per_q) - n,
        "types": sorted(types_filter),
    }

    if n > 0:
        summary["tool_selection"] = {
            "accuracy": sum(1 for r in completed if r["ts_accuracy"]) / n,
            "mean_recall": statistics.mean(r["ts_recall"] for r in completed),
            "mean_precision": statistics.mean(r["ts_precision"] for r in completed),
        }
        summary["router_fallback_rate"] = sum(1 for r in completed if r["router_fallback"]) / n
        summary["answer_nonempty_rate"] = sum(1 for r in completed if r["answer_nonempty"]) / n
        summary["mean_citation_count"] = statistics.mean(r["citation_count"] for r in completed)
        summary["step_count_distribution"] = {
            "min": min(r["step_count"] for r in completed),
            "max": max(r["step_count"] for r in completed),
            "mean": statistics.mean(r["step_count"] for r in completed),
        }
        latencies = [r["latency_ms"] for r in completed]
        summary["latency_ms"] = latency_percentiles(latencies)

        grounded_rows = [r for r in completed if "groundedness" in r]
        if grounded_rows:
            faiths = [r["groundedness"]["faithfulness"] for r in grounded_rows]
            summary["groundedness"] = {
                "n_scored": len(grounded_rows),
                "mean_faithfulness": statistics.mean(faiths),
                "min_faithfulness": min(faiths),
                "total_claims": sum(r["groundedness"]["n_claims"] for r in grounded_rows),
                "total_supported": sum(r["groundedness"]["n_supported"] for r in grounded_rows),
                "total_contradicted": sum(r["groundedness"]["n_contradicted"] for r in grounded_rows),
                "total_unsupported": sum(r["groundedness"]["n_unsupported"] for r in grounded_rows),
            }

    summary_path.write_text(json.dumps(summary, indent=2))

    print()
    print("=" * 70)
    print(json.dumps(summary, indent=2))
    print("=" * 70)
    print(f"Wrote per-question results → {jsonl_path}")
    print(f"Wrote summary              → {summary_path}")


if __name__ == "__main__":
    main()
