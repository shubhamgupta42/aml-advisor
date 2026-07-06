"""Offline unit tests — no LLM, no database, no network.

Covers the deterministic core: chunking, rank fusion, citation extraction,
router fallback slot-parsing, and the Rule Catalog lookup contract.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.rag.chunker import chunk_directories  # noqa: E402
from src.rag.prompt import extract_citations  # noqa: E402
from src.rag.retriever import _rrf_fuse  # noqa: E402
from src.agents import rule_catalog_tool as rc  # noqa: E402
from src.agents.graph import _deterministic_route  # noqa: E402


# ── Chunker ────────────────────────────────────────────────────────────────────

def test_chunker_produces_section_chunks_with_metadata():
    chunks = chunk_directories([str(ROOT / "data" / "mdds"), str(ROOT / "data" / "regulatory")])
    assert len(chunks) > 50
    for c in chunks:
        assert c.chunk_id
        assert c.section_ref, f"chunk {c.chunk_id} missing section_ref"
        assert c.metadata.get("doc_id")
        assert c.metadata.get("source_type") in ("internal_mdd", "external_regulatory")


def test_regulatory_chunks_carry_jurisdiction():
    chunks = chunk_directories([str(ROOT / "data" / "regulatory")])
    jurisdictions = {c.metadata.get("jurisdiction") for c in chunks}
    assert {"US", "UK", "IN"} <= jurisdictions


# ── Reciprocal Rank Fusion ─────────────────────────────────────────────────────

def _hit(cid: str, **extra) -> dict:
    return {"chunk_id": cid, "text": cid, "metadata": {}, **extra}


def test_rrf_ranks_double_listed_chunk_first():
    vector_hits = [_hit("a", score_vector=0.9), _hit("b", score_vector=0.8)]
    bm25_hits = [_hit("b", score_bm25=7.0), _hit("c", score_bm25=5.0)]
    fused = _rrf_fuse(vector_hits, bm25_hits)
    assert fused[0]["chunk_id"] == "b"  # appears in both lists → highest fused score
    assert {h["chunk_id"] for h in fused} == {"a", "b", "c"}  # de-duplicated union


def test_rrf_preserves_both_scores_on_merge():
    fused = _rrf_fuse([_hit("x", score_vector=0.7)], [_hit("x", score_bm25=3.0)])
    assert fused[0]["score_vector"] == 0.7
    assert fused[0]["score_bm25"] == 3.0


# ── Citation extraction (deterministic, regex — not LLM) ──────────────────────

def test_extract_citations_finds_mdd_and_reg_refs():
    answer = (
        "The threshold is $8,500 [MDD-001 §4]. Filing is mandatory "
        "[REG-US-BSA-CTR-v1 §1]. See also [MDD-001 §4]."  # duplicate on purpose
    )
    cites = extract_citations(answer)
    assert cites == ["MDD-001 §4", "REG-US-BSA-CTR-v1 §1"]  # ordered, de-duplicated


def test_extract_citations_ignores_plain_brackets():
    assert extract_citations("no refs here [just brackets]") == []


# ── Router deterministic fallback ──────────────────────────────────────────────

def test_fallback_router_extracts_rule_country_parameter():
    plan = _deterministic_route("What is the pass-through window for R181 in India?")
    assert plan["rule_id"] == "R181"
    assert plan["country"] == "IN"
    assert plan["parameter"] == "pass_through_window_hours"
    assert "rule_catalog" in plan["tools"]
    assert plan["_fallback"] is True


def test_fallback_router_defaults_to_mdd_rag_on_prose_question():
    plan = _deterministic_route("Why does structuring use round denominations?")
    assert "mdd_rag" in plan["tools"]


# ── Rule Catalog tool contract ─────────────────────────────────────────────────

def test_get_parameter_resolves_country_override():
    r = rc.get_parameter("R181", "pass_through_window_hours", country="IN")
    assert r.found is True
    assert "country_overrides.IN" in r.source  # citation points at the override


def test_get_parameter_refuses_unknown_parameter():
    r = rc.get_parameter("R168", "no_such_parameter")
    assert r.found is False  # deterministic refusal, never a guessed value
