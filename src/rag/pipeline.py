"""End-to-end RAG pipeline: question → retrieve → generate.

This is the MDD-only path. In the full system the router sends some questions
here and others to the Rule Catalog and RTCA tools, with a synthesizer
combining the results. The retrieval-only eval harness exercises this path
in isolation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import time

from .generator import generate_answer
from .prompt import GenerationResult
from .retriever import RetrievalHit, retrieve


@dataclass
class PipelineResult:
    question: str
    answer: str
    cited_refs: list[str]
    hits: list[dict]
    latency_ms: int
    usage: dict
    model: str


def answer_question(
    question: str,
    top_k: int = 5,
    use_rerank: bool = True,
    where: dict | None = None,
) -> PipelineResult:
    t0 = time.perf_counter()
    hits: list[RetrievalHit] = retrieve(
        question, top_k=top_k, use_rerank=use_rerank, where=where
    )
    gen: GenerationResult = generate_answer(question, hits)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    return PipelineResult(
        question=question,
        answer=gen.answer,
        cited_refs=gen.cited_refs,
        hits=[
            {
                "chunk_id": h.chunk_id,
                "section_ref": h.section_ref,
                "score": h.score,
                "score_vector": h.score_vector,
                "score_bm25": h.score_bm25,
                "score_rerank": h.score_rerank,
            }
            for h in hits
        ],
        latency_ms=latency_ms,
        usage=gen.usage,
        model=gen.model,
    )


def result_to_dict(r: PipelineResult) -> dict:
    return asdict(r)
