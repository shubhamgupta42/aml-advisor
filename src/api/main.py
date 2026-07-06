"""FastAPI surface for AML Advisor.

Endpoints:
  GET  /healthz         — liveness probe
  GET  /version         — corpus + agent metadata
  POST /ask             — run the multi-agent graph on a question
  POST /retrieve        — RAG-only: return ranked chunks (for the debug UI)

Why a thin HTTP layer:
- The agent is library-callable (`from src.agents.graph import ask`); this just
  exposes it over HTTP so a Streamlit UI, a curl, or any client can hit it.
- Same JSON shape as the in-process call so the eval harness and the UI go
  through the same path.
- No business logic here — the API does request validation + auth + observability.
  All AML logic lives behind it, which is what we'd want for a real bank deployment.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.agents.graph import ask as run_agent
from src.rag.retriever import retrieve

app = FastAPI(
    title="AML Advisor",
    description="Multi-agent AML compliance assistant — MDD RAG + Rule Catalog + RTCA via LangGraph.",
    version="0.2.0",
)

# CORS open for local dev (Streamlit, curl). Tighten before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ────────────────────────────────────────────────────────────────────


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    max_steps: int = Field(default=6, ge=1, le=12)


class AskResponse(BaseModel):
    question: str
    answer: str
    citations: list[str]
    plan: dict
    tool_outputs: dict
    step_count: int
    latency_ms: dict
    total_latency_ms: int
    errors: list[str]


class RetrieveRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    use_rerank: bool = True


class RetrieveResponse(BaseModel):
    question: str
    hits: list[dict]
    latency_ms: int


# ── Endpoints ──────────────────────────────────────────────────────────────────


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict:
    """Surface enough metadata for an investigator to know what they're reading."""
    from src.agents.rule_catalog_tool import catalog_version
    from src.agents.rtca_tool import rtca_version
    rc_ver = catalog_version().value
    rt_ver = rtca_version().value
    return {
        "agent_version": "0.2.0",
        "rule_catalog": rc_ver,
        "rtca": rt_ver,
        "corpus": {"mdds": ["MDD-001", "MDD-002", "MDD-003"]},
    }


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    t0 = time.perf_counter()
    try:
        result = run_agent(req.question, max_steps=req.max_steps)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent failed: {e}") from e
    total_ms = int((time.perf_counter() - t0) * 1000)
    return AskResponse(
        question=result.question,
        answer=result.answer,
        citations=result.citations,
        plan=result.plan,
        tool_outputs=_serialize_tool_outputs(result.tool_outputs),
        step_count=result.step_count,
        latency_ms=result.latency_ms,
        total_latency_ms=total_ms,
        errors=result.errors,
    )


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve_endpoint(req: RetrieveRequest) -> RetrieveResponse:
    """RAG-only path — useful for the debug pane in the Streamlit UI."""
    t0 = time.perf_counter()
    try:
        hits = retrieve(req.question, top_k=req.top_k, use_rerank=req.use_rerank)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {e}") from e
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return RetrieveResponse(
        question=req.question,
        hits=[
            {
                "section_ref": h.section_ref,
                "doc_id": h.doc_id,
                "rule_id": h.rule_id,
                "score": h.score,
                "score_bm25": h.score_bm25,
                "score_vector": h.score_vector,
                "score_rerank": h.score_rerank,
                "text": h.text[:500],
            }
            for h in hits
        ],
        latency_ms=latency_ms,
    )


def _serialize_tool_outputs(outputs: dict) -> dict:
    """tool_outputs may contain non-JSON-serializable bits (e.g. retrieval scores
    as numpy floats); coerce to plain Python."""
    import json

    def _coerce(o: Any) -> Any:
        try:
            json.dumps(o)
            return o
        except TypeError:
            if hasattr(o, "tolist"):
                return o.tolist()
            if hasattr(o, "item"):
                return o.item()
            return str(o)

    def walk(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):
            return [walk(v) for v in x]
        return _coerce(x)

    return walk(outputs)
