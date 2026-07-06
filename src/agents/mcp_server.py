"""MCP server exposing Rule Catalog + RTCA tools.

Run with: `python -m src.agents.mcp_server`  (stdio transport).

Why MCP:
- MCP is a *protocol*, not a framework. The same server can be consumed by Claude
  Desktop, Cursor, my LangGraph agent, or any future MCP client — without rewriting
  the integration each time.
- In a bank, the Rule Catalog would be backed by a system-of-record. Exposing it
  via MCP means there's ONE secure, schema-defined endpoint instead of every team
  writing their own LangChain wrapper. That's the "enterprise tool registry"
  pattern enterprises increasingly standardise on.
- Each tool publishes a JSON schema for its inputs, so the calling agent gets
  structured validation for free — no more "the LLM hallucinated an argument name".
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.agents import rule_catalog_tool as rc
from src.agents import rtca_tool as rt


server = Server("aml-advisor-tools")


# ── Tool schemas ───────────────────────────────────────────────────────────────


TOOLS: list[Tool] = [
    Tool(
        name="rule_catalog.get_rule",
        description="Return the full rule entry by rule_id (e.g. 'R168', 'R174', 'R181', 'LR-IN-NRE-014').",
        inputSchema={
            "type": "object",
            "properties": {"rule_id": {"type": "string"}},
            "required": ["rule_id"],
        },
    ),
    Tool(
        name="rule_catalog.get_parameter",
        description=(
            "Resolve a single parameter value for a rule, applying country override if provided. "
            "Examples: get_parameter('R181','pass_through_window_hours','IN') → 72. "
            "Returns a JSON-pointer source you must cite verbatim."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "rule_id": {"type": "string"},
                "parameter": {"type": "string"},
                "country": {"type": ["string", "null"], "description": "ISO-2 country code, optional."},
            },
            "required": ["rule_id", "parameter"],
        },
    ),
    Tool(
        name="rule_catalog.get_corridor_threshold",
        description="R174-only: corridor-specific threshold for an (origin_tier, dest_tier) pair.",
        inputSchema={
            "type": "object",
            "properties": {
                "rule_id": {"type": "string", "default": "R174"},
                "origin_tier": {"type": "integer"},
                "dest_tier": {"type": "integer"},
            },
            "required": ["rule_id", "origin_tier", "dest_tier"],
        },
    ),
    Tool(
        name="rule_catalog.list_rules_by_country",
        description="All ACTIVE rules deployed in the given country.",
        inputSchema={
            "type": "object",
            "properties": {"country": {"type": "string"}},
            "required": ["country"],
        },
    ),
    Tool(
        name="rule_catalog.list_local_indicators",
        description="All scope=LOCAL rules, optionally filtered by country.",
        inputSchema={
            "type": "object",
            "properties": {"country": {"type": ["string", "null"]}},
        },
    ),
    Tool(
        name="rtca.get_coverage",
        description="Coverage row(s) for a (country, typology) pair: controlling rule, in/out-of-scope segments, gap status.",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {"type": "string"},
                "typology": {"type": "string"},
            },
            "required": ["country", "typology"],
        },
    ),
    Tool(
        name="rtca.is_segment_in_scope",
        description="Is `customer_segment` in-scope for the controlling rule of (country, typology)?",
        inputSchema={
            "type": "object",
            "properties": {
                "country": {"type": "string"},
                "typology": {"type": "string"},
                "customer_segment": {"type": "string"},
            },
            "required": ["country", "typology", "customer_segment"],
        },
    ),
    Tool(
        name="rtca.list_gaps",
        description="Coverage gaps (gap_status != COVERED), optionally for one country.",
        inputSchema={
            "type": "object",
            "properties": {"country": {"type": ["string", "null"]}},
        },
    ),
    Tool(
        name="rtca.get_country_tier",
        description="Risk tier (1=lowest, 4=highest) of a country in RTCA.",
        inputSchema={
            "type": "object",
            "properties": {"country": {"type": "string"}},
            "required": ["country"],
        },
    ),
    Tool(
        name="rtca.list_rule_deployment",
        description="Which (country, typology) cells does this rule control? Returns all rows where controlling_rule_id matches.",
        inputSchema={
            "type": "object",
            "properties": {"rule_id": {"type": "string"}},
            "required": ["rule_id"],
        },
    ),
]


# ── Dispatch ───────────────────────────────────────────────────────────────────


def _result_to_text(result_dict: dict) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(result_dict, indent=2, default=str))]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    if name == "rule_catalog.get_rule":
        out = rc.get_rule(args["rule_id"]).to_dict()
    elif name == "rule_catalog.get_parameter":
        out = rc.get_parameter(args["rule_id"], args["parameter"], country=args.get("country")).to_dict()
    elif name == "rule_catalog.get_corridor_threshold":
        out = rc.get_corridor_threshold(args["rule_id"], args["origin_tier"], args["dest_tier"]).to_dict()
    elif name == "rule_catalog.list_rules_by_country":
        out = rc.list_rules_by_country(args["country"]).to_dict()
    elif name == "rule_catalog.list_local_indicators":
        out = rc.list_local_indicators(args.get("country")).to_dict()
    elif name == "rtca.get_coverage":
        out = rt.get_coverage(args["country"], args["typology"]).to_dict()
    elif name == "rtca.is_segment_in_scope":
        out = rt.is_segment_in_scope(args["country"], args["typology"], args["customer_segment"]).to_dict()
    elif name == "rtca.list_gaps":
        out = rt.list_gaps(args.get("country")).to_dict()
    elif name == "rtca.get_country_tier":
        out = rt.get_country_tier(args["country"]).to_dict()
    elif name == "rtca.list_rule_deployment":
        out = rt.list_rule_deployment(args["rule_id"]).to_dict()
    else:
        out = {"found": False, "source": "", "note": f"Unknown tool: {name}"}
    return _result_to_text(out)


async def amain() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
