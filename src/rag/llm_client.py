"""LLM client abstraction.

Why a provider-agnostic layer:
- AML compliance teams are wary of cloud vendor lock-in — same data in two
  jurisdictions sometimes requires different LLM providers. We picked the LLM
  via env var so the same agent code runs against any of them.
- It makes ablation across models cheap: change one env var, re-run the eval,
  compare. The eval harness produces apples-to-apples numbers regardless of
  which provider was used.
- Default provider is Groq (free tier, Llama-3.3-70B) for dev / portfolio.
  Production deployment would swap to Anthropic Claude or AWS Bedrock; the
  contract here (system prompt + user message → answer + usage) is the same.

Both backends speak the same `chat()` signature; the eval harness doesn't know
which one ran.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal


Provider = Literal["anthropic", "groq"]


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    usage: dict  # {"input_tokens": ..., "output_tokens": ...}


def get_provider() -> Provider:
    """Read provider from env. Defaults to groq for free-tier dev."""
    p = os.environ.get("LLM_PROVIDER", "groq").lower()
    if p not in ("anthropic", "groq"):
        raise ValueError(f"Unknown LLM_PROVIDER: {p}")
    return p  # type: ignore[return-value]


def default_model(provider: Provider | None = None) -> str:
    p = provider or get_provider()
    if p == "anthropic":
        return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    return os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")


def chat(
    system_prompt: str,
    user_message: str,
    *,
    provider: Provider | None = None,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> LLMResponse:
    """Call the configured LLM. Returns plain text + usage."""
    provider = provider or get_provider()
    model = model or default_model(provider)

    if provider == "anthropic":
        return _chat_anthropic(system_prompt, user_message, model, max_tokens, temperature)
    return _chat_groq(system_prompt, user_message, model, max_tokens, temperature)


def _chat_anthropic(
    system: str, user: str, model: str, max_tokens: int, temperature: float
) -> LLMResponse:
    from anthropic import Anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set — see .env.example")

    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(
        b.text for b in resp.content if getattr(b, "type", None) == "text"
    )
    return LLMResponse(
        text=text,
        model=model,
        provider="anthropic",
        usage={
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        },
    )


def _chat_groq(
    system: str, user: str, model: str, max_tokens: int, temperature: float
) -> LLMResponse:
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set — get a free key at https://console.groq.com/keys")

    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    text = resp.choices[0].message.content or ""
    return LLMResponse(
        text=text,
        model=model,
        provider="groq",
        usage={
            "input_tokens": resp.usage.prompt_tokens,
            "output_tokens": resp.usage.completion_tokens,
        },
    )
