"""One-shot ingest: chunk all MDDs + regulatory fixtures, embed, write to pgvector.

Usage:
    docker compose up -d              # start Postgres if not already running
    python scripts/ingest_mdds.py

Re-runnable — it truncates the chunks table and rebuilds.

Sources ingested into a single collection with metadata `source_type`:
  - data/mdds/         → source_type = "internal_mdd"
  - data/regulatory/   → source_type = "external_regulatory"
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.rag.chunker import chunk_directories  # noqa: E402
from src.rag.vector_store import build_store, _dsn  # noqa: E402


def main() -> int:
    mdd_dir = os.environ.get("MDD_DIR", str(ROOT / "data" / "mdds"))
    reg_dir = os.environ.get("REG_DIR", str(ROOT / "data" / "regulatory"))

    dirs = [mdd_dir, reg_dir]
    print(f"[ingest] Reading from: {dirs}")
    chunks = chunk_directories(dirs)
    print(f"[ingest] Produced {len(chunks)} chunks from {len({c.doc_id for c in chunks})} docs")

    by_type: dict[str, int] = {}
    by_jur: dict[str, int] = {}
    for c in chunks:
        st = c.metadata.get("source_type", "?")
        jur = c.metadata.get("jurisdiction", "") or "-"
        by_type[st] = by_type.get(st, 0) + 1
        by_jur[jur] = by_jur.get(jur, 0) + 1
    print(f"[ingest] By source_type: {by_type}")
    print(f"[ingest] By jurisdiction: {by_jur}")

    if not chunks:
        print("[ingest] No chunks produced — aborting.", file=sys.stderr)
        return 1

    print(f"[ingest] Writing to pgvector at: {_dsn()}")
    build_store(chunks, reset=True)
    print(f"[ingest] Done. {len(chunks)} chunks indexed.")

    print("\n[ingest] Chunk preview:")
    for c in chunks[:5]:
        print(f"  {c.chunk_id}  →  {c.section_ref}  jur={c.metadata.get('jurisdiction') or '-'}  ({len(c.text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
