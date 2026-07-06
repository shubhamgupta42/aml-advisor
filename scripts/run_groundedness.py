"""Publish a headline groundedness number for AML Advisor.

Runs the full agent over the labeled eval set, hands each answer + its retrieved
MDD chunks to the LLM-judge in `src/eval/groundedness.py`, and dumps a JSON
summary with:

    grounded_pct        — fraction of answers with faithfulness >= FAITHFUL_FLOOR
    mean_faithfulness   — average per-answer supported/total
    n                   — items scored
    judge_model, gen_model, commit, timestamp

Framing:
    "Hit@k tells me retrieval found the chunk. Citation accuracy tells me the
     cited ref exists in the retrieved set. Groundedness tells me the *answer
     actually matches the chunk* — a citation next to a paraphrased hallucination
     is the AML failure mode a regulator cares about."

Pattern lifted from SAP `agent-evaluation`:
  - LLMBasedMetric (aeval/.../scorer/llm_based_metric.py) — the LLM-judge base
  - OnlineEvalOrchestrator._aggregate_session_results (services/online_eval) —
    per-sample scores → run-level metric
  - ND prompt-optimizer SCORE_THRESHOLD — publish a number AND a floor

Usage:
    # small run to confirm plumbing
    python scripts/run_groundedness.py --limit 5

    # full run — needs Groq / Anthropic headroom
    python scripts/run_groundedness.py --limit 30

    # different judge from generator (recommended — avoids self-preference bias)
    LLM_JUDGE_PROVIDER=anthropic LLM_JUDGE_MODEL=claude-haiku-4-5-20251001 \\
        python scripts/run_groundedness.py --limit 30
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from src.agents.graph import ask as run_agent  # noqa: E402
from src.eval.groundedness import judge_groundedness  # noqa: E402
from src.rag.llm_client import default_model  # noqa: E402


EVAL_SET = ROOT / "data" / "ground_truth" / "eval_set.json"
OUT_DIR = ROOT / "eval_runs"
FAITHFUL_FLOOR = 0.80  # per-answer supported fraction to count as "grounded"

# Only question types where MDD-RAG is on the answer path — the judge scores
# claims against retrieved chunks, so questions that never call mdd_rag would
# be judged against empty context (score = 0.0, meaningless).
MDD_TYPES = {"mdd_only", "multi_tool"}


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "nogit"


def _run(limit: int, out_path: Path) -> dict:
    items = json.loads(EVAL_SET.read_text())["items"]
    scored_types = [q for q in items if q.get("question_type") in MDD_TYPES]
    picked = scored_types[:limit] if limit > 0 else scored_types

    per_item: list[dict] = []
    n_grounded = 0
    faithful_scores: list[float] = []
    judge_model_seen = ""

    t_start = time.perf_counter()
    for i, q in enumerate(picked, 1):
        qid = q.get("id", f"Q{i:03d}")
        question = q["question"]
        try:
            result = run_agent(question, max_steps=6)
        except Exception as e:
            per_item.append({"id": qid, "error": f"agent: {e}", "faithfulness": 0.0})
            continue

        mdd = (result.tool_outputs or {}).get("mdd_rag") or {}
        hits = mdd.get("hits") or []
        retrieved_texts = [h.get("text", "") for h in hits if h.get("text")]
        retrieved_refs = [h.get("section_ref", "") for h in hits if h.get("text")]

        if not retrieved_texts:
            per_item.append({
                "id": qid, "question_type": q.get("question_type"),
                "faithfulness": 0.0, "n_claims": 0,
                "skipped": "no mdd_rag context (router did not select mdd_rag)",
            })
            faithful_scores.append(0.0)
            continue

        try:
            g = judge_groundedness(
                answer=result.answer,
                retrieved_texts=retrieved_texts,
                retrieved_refs=retrieved_refs,
            )
        except Exception as e:
            per_item.append({"id": qid, "error": f"judge: {e}", "faithfulness": 0.0})
            faithful_scores.append(0.0)
            continue

        if g.judge_model:
            judge_model_seen = g.judge_model

        faithful_scores.append(g.faithfulness)
        if g.faithfulness >= FAITHFUL_FLOOR:
            n_grounded += 1

        per_item.append({
            "id": qid,
            "question_type": q.get("question_type"),
            "n_claims": g.n_claims,
            "n_supported": g.n_supported,
            "n_contradicted": g.n_contradicted,
            "n_unsupported": g.n_unsupported,
            "faithfulness": round(g.faithfulness, 3),
            "grounded": g.faithfulness >= FAITHFUL_FLOOR,
        })

        print(
            f"  [{i}/{len(picked)}] {qid}  faithfulness={g.faithfulness:.2f}  "
            f"({g.n_supported}/{g.n_claims} claims supported)",
            flush=True,
        )

    elapsed_s = time.perf_counter() - t_start
    n = len(picked)
    summary = {
        "timestamp_utc": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "commit": _git_commit(),
        "n_scored": n,
        "faithful_floor": FAITHFUL_FLOOR,
        "grounded_pct": round(n_grounded / n, 3) if n else 0.0,
        "mean_faithfulness": round(mean(faithful_scores), 3) if faithful_scores else 0.0,
        "gen_model": default_model(),
        "judge_model": judge_model_seen or os.environ.get("LLM_JUDGE_MODEL") or default_model(),
        "judge_provider": os.environ.get("LLM_JUDGE_PROVIDER") or "same-as-generator",
        "wallclock_s": round(elapsed_s, 1),
        "eval_set": str(EVAL_SET.relative_to(ROOT)),
        "note": (
            "Scored only mdd_only + multi_tool question types (MDD_RAG on answer path). "
            "grounded_pct = fraction of answers with faithfulness >= floor. "
            "mean_faithfulness = average supported-claim fraction across all scored answers."
        ),
        "per_item": per_item,
    }
    out_path.write_text(json.dumps(summary, indent=2))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=25,
                    help="Max MDD-answerable items to score (default 25).")
    ap.add_argument("--out", default=str(OUT_DIR / "groundedness_latest.json"))
    args = ap.parse_args()

    OUT_DIR.mkdir(exist_ok=True)
    out_path = Path(args.out)

    print(f"[groundedness] scoring up to {args.limit} MDD-answerable items...")
    print(f"[groundedness] eval set: {EVAL_SET}")
    print(f"[groundedness] generator: {default_model()}")
    print(f"[groundedness] judge: {os.environ.get('LLM_JUDGE_MODEL') or default_model()} "
          f"({os.environ.get('LLM_JUDGE_PROVIDER') or 'same-as-gen'})\n")

    summary = _run(args.limit, out_path)

    print("\n──────── SUMMARY ────────")
    print(f"  n_scored          {summary['n_scored']}")
    print(f"  grounded_pct      {summary['grounded_pct']:.1%}  "
          f"(answers with ≥{int(FAITHFUL_FLOOR*100)}% claims supported)")
    print(f"  mean_faithfulness {summary['mean_faithfulness']:.3f}")
    print(f"  gen_model         {summary['gen_model']}")
    print(f"  judge_model       {summary['judge_model']}")
    print(f"  wallclock         {summary['wallclock_s']}s")
    print(f"  written to        {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
