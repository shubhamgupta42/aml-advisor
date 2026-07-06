"""Publish a canonical latency table for AML Advisor.

Three docs currently quote three different latency numbers (DESIGN_DEFENSE 755ms,
LINKEDIN_QA 11.5s p95, agent-eval 30s p95) — all correct for what they measure,
none directly comparable. This script measures every scope in one run against
the same eval set, so a single markdown table can replace all three.

Scopes measured:
    retrieval_only  — src.rag.retriever.retrieve() with rerank (no LLM)
    router          — LLM call that picks tools (from graph.latency_ms)
    mdd_rag         — RAG pipeline: retrieve + generate answer (from graph)
    rule_catalog    — deterministic JSON tool
    rtca            — deterministic JSON tool
    synthesizer     — LLM call that combines tool outputs into final answer
    graph_total     — full /ask end-to-end

Design note: offline eval and online eval are
two distinct histograms, not one number (aeval/.../telemetry/metrics.py:126–148,
`agent_evaluation_offline_run_latency_histogram` vs `..._online_...`). And
`orchestration_deployment_latency_histogram` is a third scope — the model
round-trip only. Three histograms, three labels, no ambiguity.

Usage:
    python scripts/publish_latency.py --limit 20
    python scripts/publish_latency.py --limit 50 --out eval_runs/latency.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics as stats
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.agents.graph import ask as run_agent  # noqa: E402
from src.rag.llm_client import default_model  # noqa: E402
from src.rag.retriever import retrieve  # noqa: E402


EVAL_SET = ROOT / "data" / "ground_truth" / "eval_set.json"
OUT_DIR = ROOT / "eval_runs"

# Scopes captured from graph.latency_ms (populated per-node in src/agents/graph.py)
GRAPH_SCOPES = ("router", "mdd_rag", "rule_catalog", "rtca", "synthesizer")


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "nogit"


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def _stats(values: list[int]) -> dict:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "p50": round(stats.median(values), 1),
        "p95": round(_pct(values, 0.95), 1),
        "p99": round(_pct(values, 0.99), 1),
        "mean": round(stats.mean(values), 1),
        "max": max(values),
    }


def _markdown_table(rows: list[tuple[str, dict]]) -> str:
    lines = [
        "| scope           |   n | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) |  max (ms) |",
        "|-----------------|----:|---------:|---------:|---------:|----------:|----------:|",
    ]
    for name, s in rows:
        if s["n"] == 0:
            lines.append(f"| {name:<15} |   0 |        — |        — |        — |         — |         — |")
        else:
            lines.append(
                f"| {name:<15} | {s['n']:>3} | {s['p50']:>8.0f} | {s['p95']:>8.0f} | "
                f"{s['p99']:>8.0f} | {s['mean']:>9.0f} | {s['max']:>9} |"
            )
    return "\n".join(lines)


def _run(limit: int, out_path: Path) -> dict:
    items = json.loads(EVAL_SET.read_text())["items"]
    picked = items[:limit] if limit > 0 else items
    n = len(picked)

    print(f"[latency] running {n} questions from {EVAL_SET.name}")
    print(f"[latency] generator: {default_model()}\n")

    # Per-scope buckets
    buckets: dict[str, list[int]] = {s: [] for s in GRAPH_SCOPES}
    buckets["retrieval_only"] = []
    buckets["graph_total"] = []

    errors = 0
    t_start = time.perf_counter()

    for i, q in enumerate(picked, 1):
        qid = q.get("id", f"Q{i:03d}")
        question = q["question"]

        # 1. Retrieval-only path (no LLM, no router) — this is the "755ms" number's scope
        try:
            t0 = time.perf_counter()
            _ = retrieve(question, top_k=5, use_rerank=True)
            buckets["retrieval_only"].append(int((time.perf_counter() - t0) * 1000))
        except Exception as e:
            errors += 1
            print(f"  [{i}/{n}] {qid}  retrieval FAILED: {e}", flush=True)

        # 2. Full graph — populates per-node latencies
        try:
            t0 = time.perf_counter()
            result = run_agent(question, max_steps=6)
            total_ms = int((time.perf_counter() - t0) * 1000)
            buckets["graph_total"].append(total_ms)
            for scope in GRAPH_SCOPES:
                v = (result.latency_ms or {}).get(scope)
                if isinstance(v, int):
                    buckets[scope].append(v)
            print(f"  [{i}/{n}] {qid}  total={total_ms}ms  "
                  f"router={result.latency_ms.get('router','-')}  "
                  f"mdd={result.latency_ms.get('mdd_rag','-')}  "
                  f"synth={result.latency_ms.get('synthesizer','-')}", flush=True)
        except Exception as e:
            errors += 1
            print(f"  [{i}/{n}] {qid}  agent FAILED: {e}", flush=True)

    wallclock_s = round(time.perf_counter() - t_start, 1)

    ordered = [
        ("retrieval_only", _stats(buckets["retrieval_only"])),
        ("router",         _stats(buckets["router"])),
        ("mdd_rag",        _stats(buckets["mdd_rag"])),
        ("rule_catalog",   _stats(buckets["rule_catalog"])),
        ("rtca",           _stats(buckets["rtca"])),
        ("synthesizer",    _stats(buckets["synthesizer"])),
        ("graph_total",    _stats(buckets["graph_total"])),
    ]

    md = _markdown_table(ordered)
    print("\n" + md + "\n")

    summary = {
        "timestamp_utc": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "commit": _git_commit(),
        "n_questions": n,
        "errors": errors,
        "wallclock_s": wallclock_s,
        "gen_model": default_model(),
        "eval_set": str(EVAL_SET.relative_to(ROOT)),
        "note": (
            "Latency measured across seven scopes on the same question set in one run. "
            "retrieval_only excludes LLM; graph_total is /ask end-to-end. "
            "Warm run (embeddings + pgvector connection primed). Reranker enabled."
        ),
        "scopes": {name: s for name, s in ordered},
        "markdown_table": md,
    }
    out_path.write_text(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20,
                    help="Number of eval questions to time (default 20).")
    ap.add_argument("--out", default=str(OUT_DIR / "latency_latest.json"))
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    summary = _run(args.limit, Path(args.out))
    print(f"[latency] written to {args.out}")
    print(f"[latency] wallclock {summary['wallclock_s']}s, errors {summary['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
