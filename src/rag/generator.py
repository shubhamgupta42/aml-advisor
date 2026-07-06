"""Answer-synthesis layer. Thin wrapper over llm_client + prompt builder.

The actual provider (Groq / Anthropic) is decided by LLM_PROVIDER env var —
see src/rag/llm_client.py. This file deals only with the AML-Advisor-specific bits:
extracting citations from the answer, attaching them to the result object.
"""
from __future__ import annotations

from typing import Sequence

from .llm_client import chat
from .prompt import (
    GenerationResult,
    SYSTEM_PROMPT,
    build_user_message,
    extract_citations,
)
from .retriever import RetrievalHit


def generate_answer(
    question: str,
    hits: Sequence[RetrievalHit],
    model: str | None = None,
) -> GenerationResult:
    """Call the configured LLM with system prompt + retrieved context + question."""
    user_message = build_user_message(question, hits)
    resp = chat(SYSTEM_PROMPT, user_message, model=model)

    return GenerationResult(
        answer=resp.text,
        cited_refs=extract_citations(resp.text),
        raw_response=resp.text,
        usage=resp.usage,
        model=f"{resp.provider}:{resp.model}",
    )
