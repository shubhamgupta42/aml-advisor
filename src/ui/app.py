"""AML Advisor — Streamlit demo UI.

Run with:
    streamlit run src/ui/app.py

Two-pane layout:
- Left: question input, sample questions, the cited answer
- Right: behind-the-scenes — router plan, tool outputs, retrieved chunks, latency

Talks to the FastAPI service at AML_API_URL (default http://127.0.0.1:8765).
If the API is down, falls back to calling the agent in-process — so the demo works
even without a separate API process.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
import streamlit as st

# Streamlit puts src/ui/ on sys.path, not the repo root — add the root so the
# in-process fallback's `from src.agents.graph import ask` resolves.
_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

API_URL = os.environ.get("AML_API_URL", os.environ.get("FPSM_API_URL", "http://127.0.0.1:8765"))
API_TIMEOUT = float(os.environ.get("AML_API_TIMEOUT", os.environ.get("FPSM_API_TIMEOUT", "60")))

SAMPLE_QUESTIONS = [
    "What is the pass-through window for R181 in India?",
    "Is NRE in scope for cross-border layering in India?",
    "I'm reviewing a rapid-movement alert in Japan. What is the controlling rule, and what is its pass-through window?",
    "Why was the structuring threshold band set at $8,500 to $9,999?",
    "What are the current coverage gaps in RTCA?",
    "What is the corridor threshold for tier 1 to tier 4 on R174?",
]


# ── Page setup ─────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AML Advisor — Compliance Research Assistant",
    page_icon="🏦",
    layout="wide",
)

st.title("🏦 AML Advisor")
st.caption(
    "Multi-agent AML compliance assistant for SAR investigators. "
    "Hybrid RAG over MDDs + deterministic Rule Catalog/RTCA tools via MCP."
)


# ── Backend helpers ────────────────────────────────────────────────────────────


def api_alive() -> bool:
    try:
        r = requests.get(f"{API_URL}/healthz", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def call_ask_api(question: str) -> dict:
    r = requests.post(
        f"{API_URL}/ask",
        json={"question": question, "max_steps": 6},
        timeout=API_TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def call_ask_inproc(question: str) -> dict:
    """Fallback when the FastAPI server isn't running."""
    from src.agents.graph import ask as run_agent

    t0 = time.perf_counter()
    res = run_agent(question)
    total_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "question": res.question,
        "answer": res.answer,
        "citations": res.citations,
        "plan": res.plan,
        "tool_outputs": res.tool_outputs,
        "step_count": res.step_count,
        "latency_ms": res.latency_ms,
        "total_latency_ms": total_ms,
        "errors": res.errors,
    }


# ── Sidebar: backend status + sample questions ────────────────────────────────

with st.sidebar:
    st.subheader("Backend")
    alive = api_alive()
    if alive:
        st.success(f"✅ API live at {API_URL}")
    else:
        st.warning(
            f"⚠️ API not reachable at {API_URL}.\n\n"
            "Falling back to in-process calls — slower first call (model warmup)."
        )

    st.subheader("Sample questions")
    for q in SAMPLE_QUESTIONS:
        if st.button(q, key=f"sample-{hash(q)}", use_container_width=True):
            st.session_state["question"] = q

    st.subheader("How it works")
    st.markdown(
        "1. **Router** parses the question into typed slots — "
        "`rule_id`, `country`, `typology`, `parameter`, `segment`.\n"
        "2. Fans out in parallel to one or more of: **MDD-RAG**, "
        "**Rule Catalog tool**, **RTCA tool**.\n"
        "3. **Synthesizer** combines results into a strictly-cited answer.\n\n"
        "Every claim must end with a `[source]` marker drawn from the tool results."
    )


# ── Main: question input + answer ──────────────────────────────────────────────

q = st.text_area(
    "Investigator question",
    value=st.session_state.get("question", SAMPLE_QUESTIONS[0]),
    height=80,
    key="question",
)

col_run, col_clear = st.columns([1, 6])
run = col_run.button("Ask", type="primary", use_container_width=True)
if col_clear.button("Clear"):
    st.session_state.pop("last_result", None)
    st.rerun()

if run and q.strip():
    with st.spinner("Routing → tools → synthesizing…"):
        try:
            result = call_ask_api(q) if alive else call_ask_inproc(q)
            st.session_state["last_result"] = result
        except Exception as e:
            st.error(f"Request failed: {e}")
            st.session_state.pop("last_result", None)


result = st.session_state.get("last_result")
if not result:
    st.info("Enter a question or pick a sample from the sidebar.")
    st.stop()


# ── Result rendering ───────────────────────────────────────────────────────────

left, right = st.columns([3, 2])

with left:
    st.subheader("Answer")
    st.markdown(result["answer"] or "_(empty)_")

    if result.get("citations"):
        st.markdown("**Citations extracted from the answer:**")
        for c in result["citations"]:
            st.code(c, language="text")

    if result.get("errors"):
        st.error("Errors during run: " + "; ".join(result["errors"]))


with right:
    st.subheader("Behind the scenes")
    plan = result.get("plan") or {}

    fallback = "✅ LLM" if not plan.get("_fallback") else "⚠️ deterministic fallback"
    st.metric("Router decision", f"{', '.join(plan.get('tools', []))}", help=fallback)

    st.markdown(f"**Router slots** ({fallback})")
    slots = {k: v for k, v in plan.items() if not k.startswith("_") and k != "tools"}
    st.json(slots, expanded=False)

    st.markdown(f"**Step count**: `{result.get('step_count')}` &nbsp; "
                f"**Total latency**: `{result.get('total_latency_ms')} ms`")
    if result.get("latency_ms"):
        st.markdown("**Per-stage latency (ms)**")
        st.json(result["latency_ms"], expanded=False)

    tool_outputs = result.get("tool_outputs") or {}

    with st.expander("🔍 MDD-RAG result", expanded=False):
        m = tool_outputs.get("mdd_rag")
        if not m:
            st.caption("(not called)")
        else:
            st.markdown(f"Found: `{m.get('found')}` · Model: `{m.get('model','-')}`")
            for h in (m.get("hits") or [])[:5]:
                st.markdown(
                    f"**[{h['section_ref']}]** — score `{h.get('score'):.4f}`"
                )
                st.caption(h["text"][:400] + ("…" if len(h["text"]) > 400 else ""))

    with st.expander("📋 Rule Catalog result", expanded=False):
        r = tool_outputs.get("rule_catalog")
        if not r:
            st.caption("(not called)")
        else:
            st.json(r, expanded=False)

    with st.expander("🌍 RTCA result", expanded=False):
        rt = tool_outputs.get("rtca")
        if not rt:
            st.caption("(not called)")
        else:
            st.json(rt, expanded=False)

    with st.expander("📦 Raw response", expanded=False):
        st.code(json.dumps(result, indent=2, default=str)[:5000], language="json")
