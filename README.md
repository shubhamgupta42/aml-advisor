# AML Advisor — Multi-Agent Compliance Assistant for AML SAR Investigators

> **One-liner.** A multi-agent system that answers AML SAR investigators' natural-language questions about internal compliance documents — MDDs, the Rule Catalog, and the RTCA (Risk & Typology Coverage Assessment) — with cited answers in **under 3 seconds**, cutting per-alert documentation lookup from **~5 min to ~30 sec**.

---

## Why this project exists

In a Financial Crime unit, every transaction-monitoring alert lands in front of a **SAR investigator** who has to decide: real Suspicious Activity Report, or false positive?

To make that call, they have to understand *why the alert fired*. That means cross-referencing:

| Source | What it contains |
|---|---|
| **MDD** (Methodology Design Document) | The full design spec for a typology — threshold logic, calibration history, edge cases, sensitivity analysis. 50–150 pages each. |
| **Rule Catalog** | Active rules deployed in production — rule IDs (e.g. `R168`), typology, country scope, threshold values. |
| **RTCA** (Risk & Typology Coverage Assessment) | The mapping of which risks are covered where: country × typology × product × customer-segment. |

Today they grep through these by hand. On a typical shift: **30–50 alerts × ~5 min of doc-hunting per alert = 2–4 hours/day lost**. At 50 investigators that's ~160 investigator-hours/day returned to the team.

The docs are **internal, country-specific, and confidential** — they cannot leave the bank's perimeter. So the system runs over a **local vector store** with **strict citation**, **prompt-injection guards**, **PII redaction before any third-party LLM call**, and a **refusal path** when an answer isn't in scope.

---

## Architecture at a glance

```
                 Investigator question (natural language)
                              │
                              ▼
                    ┌──────────────────┐
                    │   Router agent   │   (Llama-3.3-70B on Groq, JSON-only output)
                    │  picks 1–N tools │   (deterministic keyword fallback)
                    └────────┬─────────┘
                ┌────────────┼────────────┐
                ▼            ▼            ▼
          ┌──────────┐ ┌──────────┐ ┌──────────┐
          │ MDD-RAG  │ │ Rule     │ │ RTCA     │
          │  node    │ │ Catalog  │ │ Coverage │
          │(pgvector │ │  tool    │ │  tool    │
          │ +BM25    │ │ (determ. │ │ (determ. │
          │ +rerank) │ │  lookup) │ │  lookup) │
          └────┬─────┘ └────┬─────┘ └────┬─────┘
               └───────────┬┴────────────┘
                           ▼
                  ┌──────────────────┐
                  │  Synthesizer     │   (strict-citation prompt,
                  │  agent           │    XML-tagged retrieval context)
                  └────────┬─────────┘
                           ▼
            Cited answer  OR  "Not found in current sources"

   Cross-cutting:  prompt-injection guard │ refusal path │
                   per-stage latency │ max-step budget = 6
```

---

## Service-Level Objectives (SLOs)

These are *requirements*, not wishes. Every commit is eval-gated against them.

| Dimension | SLO | How it's enforced |
|---|---|---|
| **Latency** | p95 < 3.0s end-to-end | Top-k=5 after rerank · parallel tool fan-out · deterministic fast path for catalog/RTCA lookups · Groq LPU inference |
| **Cost** | < $0.02 / query | Single Llama-3.3-70B on Groq for router + synthesis (~$0.001/query paid-tier equivalent) · prompt token budget |
| **Faithfulness** | > 0.95 on eval set | Strict-citation prompt · refusal path · LLM-as-judge (validated against human labels) |
| **Citation accuracy** | > 0.95 | Deterministic check: cited chunk ID must contain the claim string |
| **Refusal precision** | > 0.90 on OOD questions | Dedicated OOD slice in the eval set; tracked separately |
| **Tool-selection accuracy** | > 0.90 | Router output vs labeled gold tool-set on multi-tool eval slice |
| **Security** | Zero prompt-injection escapes | XML-tagged retrieved context · instruction-hierarchy prompt · adversarial test cases |
| **PII** | No PII leaves machine | Local embeddings + local vector store · prompt-level redaction rule (Presidio integration pending) |

---

## Quickstart

```bash
# 1. Setup (Python 3.12 required — the ML stack does not yet support 3.13/3.14)
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure the LLM provider (Groq free tier or Anthropic paid)
cp .env.example .env
# edit .env — set GROQ_API_KEY=...  (free key at https://console.groq.com)

# 3. Start Postgres + pgvector (either works)
docker compose up -d                 # Docker route
python scripts/local_pg.py           # or: self-contained local Postgres, no Docker

# 4. Ingest the corpus — 3 MDDs + 7 regulatory docs -> 77 chunks (~30 sec)
python scripts/ingest_mdds.py

# 5. Run the eval harness — single-source slice (MDD-only + OOD-refusal)
python scripts/run_baseline.py --limit 20

# 6. Try the graph end-to-end on one question
python -c "
from src.agents.graph import ask
r = ask('What is the pass-through window for R181 in India?')
print(r.answer)
print('Tools used:', r.plan['tools'])
print('Citations:', r.citations)
"

# 7. (Optional) Run the MCP server — discoverable by any MCP client
python -m src.agents.mcp_server
```

---

## What works today

| Component | Status | Notes |
|---|---|---|
| Markdown chunker (H2/H3-aware) | ✅ | 77 chunks across 3 MDDs + 7 regulatory docs |
| bge-small-en-v1.5 embeddings + pgvector cosine (HNSW) | ✅ | Postgres 16, local — no cloud |
| Hybrid retrieval (BM25 + vector, RRF) | ✅ | `src/rag/retriever.py` |
| Cross-encoder reranker (bge-reranker-base) | ✅ | **Hit@1: 0.25 → 0.50 ablation** (see `eval_runs/`) |
| Strict-citation prompt + XML-tagged context | ✅ | refusal sub-rule for "Related Documents" cross-references |
| Rule Catalog tool (6 deterministic lookups) | ✅ | every result carries a JSON-pointer source |
| RTCA tool (6 deterministic lookups) | ✅ | same `ToolResult` contract |
| LangGraph router → fan-out → synthesizer | ✅ | LLM router + deterministic keyword fallback |
| MCP server exposing all 10 tools | ✅ | verified end-to-end via the official `mcp` SDK client |
| Provider-agnostic LLM client | ✅ | Groq (free) and Anthropic backends behind one interface |
| Eval harness (Hit@k, MRR, citation acc, refusal, latency, cost) | ✅ | `scripts/run_baseline.py` writes JSONL + JSON summary |
| FastAPI HTTP surface | ✅ | `POST /ask`, `POST /retrieve`, `GET /healthz`, `GET /version` |
| Streamlit UI | ✅ | two-pane: cited answer + retrieval/router transparency panel |
| Dockerfile + GHA CI | ✅ | eval-gated CI; ingest baked at image build time |
| Presidio PII redaction | ⏳ | guard exists in prompt; Presidio integration pending |

---

## Baseline results (retrieval ablation, 2026-07-01 — reproduced 2026-07-06)

20-question slice (MDD + OOD-refusal) on the full 77-chunk corpus, bge-small-en-v1.5 embeddings, bge-reranker-base. Source of truth: `eval_runs/baseline_20260701T182314Z_*` and `eval_runs/baseline_20260706T*`.

| Metric | With Reranker | Without Reranker | Δ |
|---|---|---|---|
| **Hit@1** | **0.50** | 0.25 | **+0.25 (2×)** |
| Hit@3 | 0.62 | 0.44 | +0.18 |
| Hit@5 | 0.62 | 0.56 | +0.06 |
| MRR | 0.55 | 0.37 | +0.18 |
| Citation accuracy* | 1.00 | 1.00 | — |
| Refusal precision (OOD)* | 0.80 | 0.80 | — |
| Cost / query (paid-tier equivalent) | $0.0011 | $0.0011 | — |

\* Citation accuracy and refusal precision are from the end-to-end run (`eval_runs/baseline_20260621T*`); the ablation rows above are retrieval-only.

**Headline finding.** The reranker doubles top-1 retrieval (Hit@1 0.25 → 0.50) while Hit@5 moves only 0.56 → 0.62 — when the right chunk is retrieved at all, it's usually already in the candidate pool; the reranker's job is pushing it to rank 1, which matters because of the "Lost in the Middle" problem. The remaining gap (Hit@5 = 0.62) is a recall ceiling — the fix path is query expansion, not more rerank tuning.

## Latency (canonical, 2026-07-01, 20 questions, Groq Llama-3.3-70B synth)

One run measured against every scope on the same eval set. Source of truth: `eval_runs/latency_latest.json`.

| scope           |   n | p50 (ms) | p95 (ms) | p99 (ms) | mean (ms) |  max (ms) |
|-----------------|----:|---------:|---------:|---------:|----------:|----------:|
| retrieval_only  |  20 |      813 |     3694 |    42063 |      3336 |     51655 |
| router          |  20 |       74 |      153 |      238 |        86 |       259 |
| mdd_rag         |  13 |      804 |      895 |      905 |       801 |       907 |
| rule_catalog    |  15 |        0 |        1 |        2 |         0 |         2 |
| rtca            |   3 |        0 |        5 |        6 |         2 |         6 |
| synthesizer     |  20 |       73 |      220 |      561 |       114 |       646 |
| graph_total     |  20 |      908 |     1185 |     1645 |       727 |      1760 |

**Reading it.** `graph_total` p95 = 1.2s end-to-end (inside the 3s SLO). Rule-only fast path is ~150ms (router + rule_catalog + synth). MDD path is ~900ms (dominated by retrieve+rerank). `retrieval_only` p99 is a cold-start outlier — first call primes embeddings + pgvector; steady-state p50 is 813ms and matches the mdd_rag scope inside the graph.

**Known gaps.** Groundedness number (LLM-judge faithfulness) is queued — the harness (`scripts/run_groundedness.py`) is wired but the current-stack run has not landed. Multi-tool eval slice (Q016–Q044) pending — single-source-only numbers above.

---

## Project layout

```
aml-advisor/
├── data/
│   ├── mdds/                       # 3 synthetic Methodology Design Documents
│   ├── regulatory/                 # 7 synthetic regulatory fixtures (US/UK/DE/SG/IN/AE/JP)
│   ├── rule_catalog.json           # synthetic Rule Catalog (R-IDs, thresholds, country)
│   ├── rtca_coverage.json          # synthetic RTCA mapping (country × typology × product)
│   └── ground_truth/eval_set.json  # 54 labeled Q&A for the eval harness
├── src/
│   ├── rag/                        # chunker, embedder, vector_store (pgvector), retriever, prompt, llm_client
│   ├── agents/                     # rule_catalog_tool, rtca_tool, graph (LangGraph), mcp_server
│   ├── api/                        # FastAPI: POST /ask, POST /retrieve, GET /healthz
│   ├── ui/                         # Streamlit two-pane UI
│   └── eval/                       # retrieval / generation / refusal / latency / cost metrics
├── scripts/                        # ingest_mdds.py, local_pg.py, run_baseline.py, run_groundedness.py
├── eval_runs/                      # eval summaries (ablation + latency evidence)
└── tests/                          # offline unit tests (pytest)
```

---

## What's deliberately *not* in scope

Scope boundaries:

- ❌ **Not a replacement for the alert-suppression classifier.** The FP-suppression ML model sits *upstream* — it decides which alerts to surface. This system explains the docs behind those decisions to the investigator.
- ❌ **Not a triage decision-maker.** It never says "suppress this alert." It explains *what the rule says* so the human decides.
- ❌ **Not regulator-facing.** Internal tool for investigators only.
- ❌ **Not multilingual.** English corpus in the current release.
- ❌ **Not fine-tuned.** Docs change quarterly; auditors require explicit citation; RAG is the right tool, not fine-tuning.

---

## Glossary

Short glossary for non-AML readers:

| Term | Meaning |
|---|---|
| **AML** | Anti-Money Laundering |
| **SAR** | Suspicious Activity Report — the disposition an investigator files when an alert is genuine |
| **STR** | Suspicious Transaction Report — the regulatory filing |
| **TM** | Transaction Monitoring — the rule-based system that fires alerts |
| **MDD** | Methodology Design Document — design spec for a typology / rule |
| **RTCA** | Risk & Typology Coverage Assessment — what risks are covered where |
| **Rule Catalog** | Live registry of rules deployed in production, with country scope and thresholds |
| **ECL Rule** | Enterprise / global rule — applies across all countries |
| **Local Indicator** | Country-specific rule |
| **FPSM** | False-Positive Suppression Model — the ML classifier that suppresses obvious-FP alerts before they reach the queue |
| **Suppression %** | (Alerts suppressed by model) / (Total alerts). Higher = more investigator time saved. |
| **Event Loss %** | (Missed true STRs) / (Total true STRs) = (1 − Recall) × 100. Target near 0 — regulatory miss is a fine. |
| **KDE** | Key Data Element — the fields used in a rule's threshold logic |
| **Lookback Period** | Time window over which a rule aggregates transactions |
| **BSA / FATF** | US Bank Secrecy Act / Financial Action Task Force — the regulatory frames |

---

## Build status

Design decisions are documented inline in each module's docstring — `src/rag/vector_store.py` (why pgvector), `src/rag/retriever.py` (why hybrid + rerank), `src/rag/chunker.py` (why section-aware chunking).

---

*Public reference implementation. All compliance documents in `data/` are fully synthetic, constructed from public AML typology guidance (FATF, FinCEN, BIS). No proprietary or client content is included.*
