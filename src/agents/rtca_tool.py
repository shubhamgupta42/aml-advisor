"""RTCA tool — deterministic coverage lookups over rtca_coverage.json.

RTCA = Risk & Typology Coverage Assessment. Tells investigators which
(country, typology, product, customer_segment) combinations are covered
by which controlling rule — and where the gaps are.

Same ToolResult contract as rule_catalog_tool so the synthesizer can render
citations uniformly.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .rule_catalog_tool import ToolResult

_DEFAULT_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "rtca_coverage.json"
)


@lru_cache(maxsize=1)
def _load_rtca(path: str = str(_DEFAULT_PATH)) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _typology_match(entry_typ: str, query_typ: str) -> bool:
    """Loose containment match — RTCA uses 'Rapid Movement / Funnel'
    but a question may say 'Rapid Movement' or 'Funnel'."""
    e = entry_typ.lower()
    q = query_typ.lower()
    return q in e or e in q or any(tok in e for tok in q.split() if len(tok) > 3)


def get_coverage(country: str, typology: str) -> ToolResult:
    """Lookup the coverage row for a (country, typology) pair.

    Returns the controlling rule, in/out-of-scope segments, gap status.
    If multiple rows match (e.g. India has a special NRE/NRO row alongside
    the general one), returns all of them — investigator needs to see both.
    """
    cc = country.upper()
    rtca = _load_rtca()
    matches = [
        row
        for row in rtca.get("coverage_matrix", [])
        if row["country"] == cc and _typology_match(row["typology"], typology)
    ]
    if not matches:
        return ToolResult(
            found=False,
            source=f"RTCA → coverage_matrix[country={cc}, typology~='{typology}']",
            note=(
                f"No RTCA row for ({cc}, {typology}). "
                f"Either the typology name is wrong, or this combination is not assessed "
                f"in RTCA {rtca.get('version')}."
            ),
        )

    return ToolResult(
        found=True,
        value=matches if len(matches) > 1 else matches[0],
        source=f"RTCA → coverage_matrix[country={cc}, typology='{matches[0]['typology']}']",
        note=f"{len(matches)} matching row(s).",
    )


def is_segment_in_scope(country: str, typology: str, customer_segment: str) -> ToolResult:
    """Is `customer_segment` in-scope for the controlling rule of (country, typology)?

    Returns a structured verdict the synthesizer can render directly.
    """
    cov = get_coverage(country, typology)
    if not cov.found:
        return cov

    seg = customer_segment.strip()
    rows = cov.value if isinstance(cov.value, list) else [cov.value]
    verdicts = []
    for row in rows:
        in_scope = seg in (row.get("customer_segments_in_scope") or [])
        carved_out = seg in (row.get("customer_segments_carved_out") or [])
        verdicts.append(
            {
                "controlling_rule_id": row["controlling_rule_id"],
                "in_scope": in_scope,
                "carved_out": carved_out,
                "row_notes": row.get("notes", ""),
                "row_product_scope": row.get("product_scope"),
            }
        )

    return ToolResult(
        found=True,
        value=verdicts if len(verdicts) > 1 else verdicts[0],
        source=(
            f"RTCA → coverage_matrix[country={country.upper()}, "
            f"typology='{rows[0]['typology']}'].customer_segments_*"
        ),
        note=f"Checked segment '{seg}' against {len(rows)} matching coverage row(s).",
    )


def list_gaps(country: str | None = None) -> ToolResult:
    """Coverage gaps (gap_status != COVERED), optionally for a single country."""
    rtca = _load_rtca()
    rows = [
        r
        for r in rtca.get("coverage_matrix", [])
        if r.get("gap_status") != "COVERED"
        and (country is None or r["country"] == country.upper())
    ]
    src = "RTCA → coverage_matrix[gap_status!=COVERED"
    if country:
        src += f", country={country.upper()}"
    src += "]"
    return ToolResult(
        found=bool(rows),
        value=[
            {
                "country": r["country"],
                "typology": r["typology"],
                "gap_status": r["gap_status"],
                "notes": r.get("notes", ""),
            }
            for r in rows
        ],
        source=src,
        note=f"{len(rows)} gap row(s) found." if rows else "No gaps for this scope.",
    )


def get_country_tier(country: str) -> ToolResult:
    cc = country.upper()
    rtca = _load_rtca()
    tiers = rtca.get("country_risk_tiers", {})
    if cc not in tiers:
        return ToolResult(
            found=False,
            source=f"RTCA → country_risk_tiers.{cc}",
            note=f"{cc} not tiered in RTCA {rtca.get('version')}.",
        )
    return ToolResult(
        found=True,
        value=tiers[cc],
        source=f"RTCA → country_risk_tiers.{cc}",
    )


def list_rule_deployment(rule_id: str) -> ToolResult:
    """Which (country, typology) cells does this rule control?"""
    rtca = _load_rtca()
    rows = [
        {"country": r["country"], "typology": r["typology"], "product_scope": r.get("product_scope")}
        for r in rtca.get("coverage_matrix", [])
        if (r.get("controlling_rule_id") or "").upper() == rule_id.upper()
    ]
    return ToolResult(
        found=bool(rows),
        value=rows,
        source=f"RTCA → coverage_matrix[controlling_rule_id={rule_id}]",
        note=f"{rule_id} controls {len(rows)} coverage cell(s)." if rows else f"{rule_id} not referenced as controlling rule in RTCA.",
    )


def rtca_version() -> ToolResult:
    rtca = _load_rtca()
    return ToolResult(
        found=True,
        value={"version": rtca.get("version"), "approved_date": rtca.get("approved_date")},
        source="RTCA → version",
    )
