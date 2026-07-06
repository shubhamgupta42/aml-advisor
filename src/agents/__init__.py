"""Structured-data agents: deterministic tools over Rule Catalog and RTCA.

Why these are NOT in the vector store:
- The Rule Catalog and RTCA are KEY-VALUE / RELATIONAL data, not prose.
  "What's R181's pass-through window in India?" is a JSON path lookup
  (rules[id=R181].country_overrides.IN.pass_through_window_hours).
- Running it through embeddings + cosine similarity is wasteful, slow, and
  introduces a faithfulness risk — the LLM might paraphrase the number wrong.
- Right tool for the right job: prose → vector, structured → tool.
- This also makes auditability concrete: every Rule Catalog answer is one
  deterministic function call with a JSON pointer, not a probability distribution.
"""
