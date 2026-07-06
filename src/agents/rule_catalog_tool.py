"""Rule Catalog tool — deterministic structured lookups, no LLM, no embeddings.

Every public function returns a ToolResult carrying:
  - value:   the answer payload (dict / number / list) for the synthesizer to render
  - source:  a JSON-pointer-style citation like
             "Rule Catalog → R181 → country_overrides.IN.pass_through_window_hours"
  - found:   True if the path resolved, False if not (drives the refusal path)

The synthesizer is required to print `source` verbatim in citations, which makes
this end of the pipeline 100% auditable — no paraphrase risk.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

_DEFAULT_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "rule_catalog.json"
)


@dataclass
class ToolResult:
    found: bool
    value: Any = None
    source: str = ""
    note: str = ""
    extras: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "found": self.found,
            "value": self.value,
            "source": self.source,
            "note": self.note,
            "extras": self.extras,
        }


@lru_cache(maxsize=1)
def _load_catalog(path: str = str(_DEFAULT_PATH)) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_rule(rule_id: str) -> dict | None:
    cat = _load_catalog()
    for r in cat.get("rules", []):
        if r["rule_id"].upper() == rule_id.upper():
            return r
    return None


def get_rule(rule_id: str) -> ToolResult:
    """Full rule entry by ID."""
    r = _find_rule(rule_id)
    if not r:
        return ToolResult(
            found=False,
            source=f"Rule Catalog → {rule_id}",
            note=f"Rule {rule_id} not in catalog (version {_load_catalog().get('version')}).",
        )
    return ToolResult(
        found=True,
        value=r,
        source=f"Rule Catalog → {r['rule_id']}",
    )


def get_parameter(rule_id: str, parameter: str, country: str | None = None) -> ToolResult:
    """Resolve a single parameter for a rule, optionally with country override.

    Resolution order: country_overrides[country][parameter] → parameters[parameter].
    The source pointer records which level actually supplied the value so the
    investigator can see whether they're reading the global or the override value.
    """
    r = _find_rule(rule_id)
    if not r:
        return ToolResult(
            found=False,
            source=f"Rule Catalog → {rule_id}",
            note=f"Rule {rule_id} not in catalog.",
        )

    if country:
        cc = country.upper()
        overrides = r.get("country_overrides", {}).get(cc, {})
        if parameter in overrides:
            return ToolResult(
                found=True,
                value=overrides[parameter],
                source=f"Rule Catalog → {r['rule_id']} → country_overrides.{cc}.{parameter}",
                note=f"Country-specific override for {cc}.",
            )
        if cc not in r.get("countries", []):
            return ToolResult(
                found=False,
                source=f"Rule Catalog → {r['rule_id']}",
                note=f"Rule {r['rule_id']} is not deployed in {cc} (countries: {r.get('countries')}).",
            )

    params = r.get("parameters", {})
    if parameter in params:
        return ToolResult(
            found=True,
            value=params[parameter],
            source=f"Rule Catalog → {r['rule_id']} → parameters.{parameter}",
            note="Global (ECL) parameter — no country override applies."
            if country
            else "",
        )

    return ToolResult(
        found=False,
        source=f"Rule Catalog → {r['rule_id']}",
        note=f"Parameter '{parameter}' not defined on {r['rule_id']}. "
        f"Available: {list(params.keys())}.",
    )


def get_corridor_threshold(rule_id: str, origin_tier: int, dest_tier: int) -> ToolResult:
    """Corridor-specific threshold (R174 only). Falls back to default_threshold_usd."""
    r = _find_rule(rule_id)
    if not r:
        return ToolResult(
            found=False,
            source=f"Rule Catalog → {rule_id}",
            note=f"Rule {rule_id} not in catalog.",
        )

    corridors = r.get("corridor_specific", [])
    for c in corridors:
        if c["origin_tier"] == origin_tier and c["dest_tier"] == dest_tier:
            return ToolResult(
                found=True,
                value=c["threshold_usd"],
                source=(
                    f"Rule Catalog → {r['rule_id']} → corridor_specific"
                    f"[origin_tier={origin_tier}, dest_tier={dest_tier}].threshold_usd"
                ),
            )

    default = r.get("parameters", {}).get("default_threshold_usd")
    if default is not None:
        return ToolResult(
            found=True,
            value=default,
            source=f"Rule Catalog → {r['rule_id']} → parameters.default_threshold_usd",
            note=(
                f"No corridor-specific entry for ({origin_tier}→{dest_tier}); "
                f"using rule default."
            ),
        )

    return ToolResult(
        found=False,
        source=f"Rule Catalog → {r['rule_id']}",
        note=f"No corridor matrix on {r['rule_id']}.",
    )


def list_rules_by_country(country: str) -> ToolResult:
    """All ACTIVE rules deployed in the given country."""
    cc = country.upper()
    cat = _load_catalog()
    matches = [
        {"rule_id": r["rule_id"], "name": r["name"], "scope": r["scope"], "typology": r["typology"]}
        for r in cat.get("rules", [])
        if cc in r.get("countries", []) and r.get("status") == "ACTIVE"
    ]
    return ToolResult(
        found=bool(matches),
        value=matches,
        source=f"Rule Catalog → rules[country contains '{cc}', status=ACTIVE]",
        note=f"{len(matches)} active rule(s) deployed in {cc}." if matches else f"No active rules in {cc}.",
    )


def list_local_indicators(country: str | None = None) -> ToolResult:
    """All scope=LOCAL rules, optionally filtered by country."""
    cat = _load_catalog()
    matches = [
        {"rule_id": r["rule_id"], "name": r["name"], "countries": r["countries"], "mdd_ref": r["mdd_ref"]}
        for r in cat.get("rules", [])
        if r.get("scope") == "LOCAL"
        and (country is None or country.upper() in r.get("countries", []))
    ]
    src = "Rule Catalog → rules[scope=LOCAL"
    if country:
        src += f", country contains '{country.upper()}'"
    src += "]"
    return ToolResult(
        found=bool(matches),
        value=matches,
        source=src,
        note=f"{len(matches)} local indicator(s) found.",
    )


def catalog_version() -> ToolResult:
    cat = _load_catalog()
    return ToolResult(
        found=True,
        value={"version": cat.get("version"), "generated_at": cat.get("generated_at")},
        source="Rule Catalog → version",
    )
