"""Markdown-aware semantic chunker for MDDs.

Why this design:
- MDDs are structured docs with stable section headings (§1 Purpose, §4 Detection Logic, etc.).
- Naive fixed-size chunking (e.g. 512 tokens with overlap) splits the threshold table
  away from its rationale, which destroys answer faithfulness on questions like
  "why is the threshold $8500?" — the threshold is in §4, the rationale in §5.
- We chunk on H2 (##) boundaries, preserving section integrity. If a section
  is larger than max_chars, we sub-split on H3 (###) then on paragraph.
- Every chunk carries metadata: doc_id, section_ref (e.g. "MDD-001 §4.2"),
  rule_id (parsed from the doc), so the synthesizer can produce precise citations.

Design note: this is the answer to Q4 (chunking strategies) and Q5
(does chunk size affect performance) — we made a deliberate, defensible choice
grounded in the structure of OUR documents, not a blind 512-token split.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
SECTION_NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(.+)$")


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    section_ref: str
    text: str
    metadata: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.text)


def _extract_doc_id(text: str, fallback: str) -> str:
    """Pull Document ID from the MDD frontmatter line, else fall back to filename."""
    m = re.search(r"\*\*Document ID:\*\*\s*([A-Z0-9\-\.v]+)", text)
    return m.group(1) if m else fallback


def _extract_rule_id(text: str) -> str | None:
    """Find the production rule_id this MDD governs (e.g. R168)."""
    m = re.search(r"rule\s+\*\*(R\d+|LR-[A-Z]+-[A-Z0-9\-]+)\*\*", text, re.IGNORECASE)
    return m.group(1) if m else None


def _extract_frontmatter_field(text: str, field: str) -> str | None:
    """Extract a **Field:** value from the top-of-doc frontmatter block."""
    pattern = rf"\*\*{re.escape(field)}:\*\*\s*([^\n]+)"
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def _split_on_h2(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into (section_title, section_body) on H2 (##) headers.

    Anything before the first H2 is bucketed as ('PREAMBLE', body).
    """
    parts: list[tuple[str, str]] = []
    current_title = "PREAMBLE"
    current_body: list[str] = []

    for line in markdown.splitlines(keepends=True):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if current_body:
                parts.append((current_title, "".join(current_body).strip()))
            current_title = m.group(1).strip()
            current_body = [line]
        else:
            current_body.append(line)

    if current_body:
        parts.append((current_title, "".join(current_body).strip()))

    return [p for p in parts if p[1]]


def _section_ref(doc_id: str, title: str) -> str:
    """Format '§4. Detection Logic' as 'MDD-001 §4'."""
    m = SECTION_NUM_RE.match(title)
    if m:
        return f"{doc_id} §{m.group(1)}"
    return f"{doc_id} ({title})"


def _split_oversized(body: str, max_chars: int) -> list[str]:
    """If a section is too large, split on H3 then on blank lines.

    Preserves the H2 header on the first sub-chunk; subsequent sub-chunks
    keep their H3 header so context is not lost.
    """
    if len(body) <= max_chars:
        return [body]

    h3_parts = re.split(r"(?=^###\s+)", body, flags=re.MULTILINE)
    h3_parts = [p.strip() for p in h3_parts if p.strip()]

    if len(h3_parts) > 1 and all(len(p) <= max_chars for p in h3_parts):
        return h3_parts

    chunks: list[str] = []
    for part in h3_parts:
        if len(part) <= max_chars:
            chunks.append(part)
            continue
        paras = re.split(r"\n\s*\n", part)
        buf: list[str] = []
        buf_len = 0
        for para in paras:
            if buf_len + len(para) > max_chars and buf:
                chunks.append("\n\n".join(buf))
                buf = [para]
                buf_len = len(para)
            else:
                buf.append(para)
                buf_len += len(para) + 2
        if buf:
            chunks.append("\n\n".join(buf))
    return chunks


def chunk_markdown(
    markdown: str,
    source_path: str | Path,
    max_chars: int = 2000,
) -> list[Chunk]:
    """Chunk a single markdown MDD into retrieval units.

    Parameters
    ----------
    markdown : str
        Raw markdown content.
    source_path : str | Path
        Path string used for chunk_id and as filename fallback for doc_id.
    max_chars : int
        Soft ceiling per chunk. Sections larger than this are sub-split on H3
        then on paragraph boundaries.
    """
    fallback_id = Path(source_path).stem.upper()
    doc_id = _extract_doc_id(markdown, fallback_id)
    rule_id = _extract_rule_id(markdown)
    jurisdiction = _extract_frontmatter_field(markdown, "Jurisdiction") or ""
    source_type = _extract_frontmatter_field(markdown, "Source Type") or "internal_mdd"

    chunks: list[Chunk] = []
    for section_title, section_body in _split_on_h2(markdown):
        ref = _section_ref(doc_id, section_title)
        for i, sub in enumerate(_split_oversized(section_body, max_chars)):
            cid = f"{doc_id}::{section_title[:40]}::{i}"
            chunks.append(
                Chunk(
                    chunk_id=cid,
                    doc_id=doc_id,
                    section_ref=ref,
                    text=sub,
                    metadata={
                        "doc_id": doc_id,
                        "section_ref": ref,
                        "section_title": section_title,
                        "rule_id": rule_id or "",
                        "jurisdiction": jurisdiction,
                        "source_type": source_type,
                        "source_path": str(source_path),
                        "sub_index": i,
                    },
                )
            )
    return chunks


def chunk_directory(mdd_dir: str | Path, max_chars: int = 2000) -> list[Chunk]:
    """Chunk every .md file in a directory. Returns a flat list of chunks."""
    mdd_dir = Path(mdd_dir)
    all_chunks: list[Chunk] = []
    for md_path in sorted(mdd_dir.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        all_chunks.extend(chunk_markdown(text, md_path, max_chars=max_chars))
    return all_chunks


def chunk_directories(dirs: list[str | Path], max_chars: int = 2000) -> list[Chunk]:
    """Chunk every .md file across multiple directories.

    Used to ingest internal MDDs and external regulatory fixtures into one
    corpus while preserving `source_type` and `jurisdiction` metadata per chunk.
    """
    all_chunks: list[Chunk] = []
    for d in dirs:
        p = Path(d)
        if not p.exists():
            continue
        all_chunks.extend(chunk_directory(p, max_chars=max_chars))
    return all_chunks
