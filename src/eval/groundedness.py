"""Groundedness / faithfulness eval — LLM-as-judge.

Why this exists:
- Hit@k tells us whether retrieval FOUND the right doc.
- Citation accuracy tells us whether the cited section_ref EXISTS in the retrieved set.
- Neither tells us: **does the answer actually match what the chunk says?**
  A model can cite the correct chunk and still paraphrase it wrong — that's a
  hallucination hiding behind a real citation. In AML this is a regulator finding.

Groundedness answers: for every atomic claim in the answer, is it supported by
the retrieved context? This is the Ragas-style "faithfulness" metric, done with
a self-hosted judge so we don't ship data to a third-party service.

The judge is a separate LLM call with temperature=0 and a strict rubric:
    SUPPORTED   — claim entailed by cited chunks
    CONTRADICTED — claim contradicts cited chunks
    UNSUPPORTED — claim not addressed by cited chunks (halluc risk)

Score = fraction of claims marked SUPPORTED.

Caveats we document, not hide:
1. LLM judges have known bias — verbose = confident. We mitigate with strict rubric.
2. Judge should be a DIFFERENT model from the generator (Claude judging Llama)
   when possible; we support that via LLM_JUDGE_PROVIDER env var.
3. Cross-validate against ≥20 human labels before trusting unattended. Report
   Cohen's kappa in the run summary — target ≥ 0.8.

Reference: Ragas paper (Es et al. 2023), Faithfulness section.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from src.rag.llm_client import chat, default_model


JUDGE_SYSTEM = """You are a strict evaluator of AI-generated compliance answers.

Your job: decide whether each factual claim in the ANSWER is grounded in the CONTEXT provided.

For each claim, output one of:
- SUPPORTED: the claim is directly stated or clearly entailed by the context.
- CONTRADICTED: the claim conflicts with the context.
- UNSUPPORTED: the claim is not addressed by the context (neither confirmed nor denied).

Rules:
1. Judge only the ANSWER's factual claims, not stylistic phrasing.
2. Do not use outside knowledge. If the context does not state it, it is UNSUPPORTED — even if you believe it is true in the real world.
3. Numbers, thresholds, jurisdictions, and rule IDs must match exactly. "72 hours" vs "72" is fine, "72" vs "48" is CONTRADICTED.
4. Return ONLY a JSON object. No prose. Schema:
   {"claims": [{"text": "...", "verdict": "SUPPORTED|CONTRADICTED|UNSUPPORTED", "reason": "..."}]}
"""


@dataclass
class GroundednessResult:
    n_claims: int
    n_supported: int
    n_contradicted: int
    n_unsupported: int
    faithfulness: float  # supported / total
    claims: list[dict] = field(default_factory=list)
    judge_model: str = ""
    raw: str = ""


def _extract_atomic_claims(answer: str) -> list[str]:
    """Split an answer into atomic factual claims.

    Simple sentence splitter — the judge model does the semantic work.
    We strip citation brackets from claims to keep the judge focused on the
    factual content, not the citation format.
    """
    # Remove citation markers before claim extraction
    cleaned = re.sub(r"\[[^\]]+\]", "", answer)
    # Split on sentence boundaries. Keep it dumb; the judge handles nuance.
    parts = re.split(r"(?<=[.!?])\s+", cleaned.strip())
    return [p.strip() for p in parts if len(p.strip()) > 3]


def _render_context(retrieved_texts: list[str], retrieved_refs: list[str]) -> str:
    """XML-tag the retrieved chunks so the judge cannot be prompt-injected."""
    out = []
    for ref, text in zip(retrieved_refs, retrieved_texts):
        safe = text.replace("</chunk>", "&lt;/chunk&gt;")
        out.append(f'<chunk section_ref="{ref}">\n{safe}\n</chunk>')
    return "\n".join(out)


def _parse_judge_output(raw: str) -> list[dict]:
    """Strip code fences and parse the judge's JSON. Return [] on any failure."""
    txt = raw.strip()
    txt = re.sub(r"^```(?:json)?\s*", "", txt)
    txt = re.sub(r"\s*```$", "", txt)
    try:
        data = json.loads(txt)
        claims = data.get("claims", []) if isinstance(data, dict) else []
        return [c for c in claims if isinstance(c, dict) and "verdict" in c]
    except json.JSONDecodeError:
        return []


def judge_groundedness(
    answer: str,
    retrieved_texts: list[str],
    retrieved_refs: list[str],
    judge_provider: Optional[str] = None,
    judge_model: Optional[str] = None,
) -> GroundednessResult:
    """Score whether each factual claim in `answer` is supported by retrieved context.

    Parameters
    ----------
    answer : str
        The agent's generated answer.
    retrieved_texts : list[str]
        Full text of the top-k chunks that were passed to the generator.
    retrieved_refs : list[str]
        Parallel list of section refs (for XML tagging in the judge prompt).
    judge_provider : str | None
        Overrides LLM_JUDGE_PROVIDER env; defaults to same provider as generator.
        For strongest evidence, use a DIFFERENT provider from the generator.
    judge_model : str | None
        Overrides LLM_JUDGE_MODEL env.
    """
    if not answer.strip() or not retrieved_texts:
        return GroundednessResult(0, 0, 0, 0, 0.0, [], "", "")

    provider = judge_provider or os.environ.get("LLM_JUDGE_PROVIDER") or None
    model = judge_model or os.environ.get("LLM_JUDGE_MODEL") or None
    if provider and not model:
        model = default_model(provider)  # type: ignore[arg-type]

    claims = _extract_atomic_claims(answer)
    if not claims:
        return GroundednessResult(0, 0, 0, 0, 0.0, [], model or "", "")

    context_block = _render_context(retrieved_texts, retrieved_refs)
    user_msg = (
        f"<context>\n{context_block}\n</context>\n\n"
        f"<answer>\n{answer}\n</answer>\n\n"
        "Extract every factual claim from the ANSWER and classify each against the CONTEXT. "
        "Return the JSON only."
    )

    resp = chat(
        system_prompt=JUDGE_SYSTEM,
        user_message=user_msg,
        provider=provider,  # type: ignore[arg-type]
        model=model,
        max_tokens=1200,
        temperature=0.0,
    )

    parsed = _parse_judge_output(resp.text)

    n = len(parsed)
    n_sup = sum(1 for c in parsed if c.get("verdict") == "SUPPORTED")
    n_con = sum(1 for c in parsed if c.get("verdict") == "CONTRADICTED")
    n_uns = sum(1 for c in parsed if c.get("verdict") == "UNSUPPORTED")
    faithfulness = (n_sup / n) if n else 0.0

    return GroundednessResult(
        n_claims=n,
        n_supported=n_sup,
        n_contradicted=n_con,
        n_unsupported=n_uns,
        faithfulness=faithfulness,
        claims=parsed,
        judge_model=resp.model,
        raw=resp.text,
    )
