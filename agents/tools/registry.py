"""
Tool Registry - Agent to Tool Mapping

Loads tool definitions from tools/definitions/*.json at import time.
JSON schema files with a "name" key are agent tools - single source of truth.
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agents.tools.executors import ALL_TOOL_EXECUTORS

_SCHEMAS_DIR = Path(__file__).resolve().parent / "definitions"


# =============================================================================
# SCHEMA LOADING
# =============================================================================

def _clean_schema_properties(properties: dict) -> dict:
    """Clean schema properties for OpenAI function-calling compatibility."""
    clean_props = {}
    for name, spec in properties.items():
        clean = {"type": spec["type"], "description": spec.get("description", "")}
        if "enum" in spec:
            clean["enum"] = spec["enum"]
        if spec["type"] == "object" and "properties" in spec:
            clean["properties"] = _clean_schema_properties(spec["properties"])
            if "required" in spec:
                clean["required"] = spec["required"]
        if spec["type"] == "array" and "items" in spec:
            items = spec["items"]
            clean_items = {"type": items.get("type", "object")}
            if "properties" in items:
                clean_items["properties"] = _clean_schema_properties(items["properties"])
                if "required" in items:
                    clean_items["required"] = items["required"]
            clean["items"] = clean_items
        clean_props[name] = clean
    return clean_props


def _load_tool_definition(schema: dict) -> dict:
    """Build an OpenAI function-calling definition from a schema file."""
    name = schema["name"]
    description = schema.get("description", "")

    if "parameters" in schema:
        params = schema["parameters"]
        if "properties" in params:
            params["properties"] = _clean_schema_properties(params["properties"])
        return {"name": name, "description": description, "parameters": params}

    properties = _clean_schema_properties(schema.get("properties", {}))
    required = list(schema.get("required", []))

    agent_overrides = schema.get("agent", {})
    if "override_required" in agent_overrides:
        required = agent_overrides["override_required"]

    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


def _load_all_tool_definitions() -> dict[str, dict]:
    """Load tool definitions from all tools/definitions/*.json files that have a 'name' key."""
    definitions = {}
    for schema_file in sorted(_SCHEMAS_DIR.glob("*.json")):
        try:
            with open(schema_file, "r", encoding="utf-8") as f:
                schema = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logging.error(f"Failed to load schema {schema_file}: {e}")
            continue

        if "name" not in schema:
            continue

        tool_def = _load_tool_definition(schema)
        definitions[tool_def["name"]] = tool_def

    logging.info(f"Loaded {len(definitions)} tool definitions from schemas")
    return definitions


ALL_TOOL_DEFINITIONS = _load_all_tool_definitions()


# =============================================================================
# AGENT TO TOOL MAPPING
# =============================================================================

AGENT_TOOL_MAPPING = {
    "email_triage": [],  # No tools needed - email is pre-fetched before agent runs
    "notification_content": [
        "determine_recipient",
        "send_email_notification",
    ],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _resolve_agent_id(session, agent_name: str) -> int | None:
    """Resolve agent name to AgentDefinition.id."""
    from agents.utility.util_datamodel import AgentDefinition
    row = (
        session.query(AgentDefinition)
        .filter(AgentDefinition.name == agent_name, AgentDefinition.is_active == True)
        .first()
    )
    return row.id if row else None


def get_tool_executors(agent_name: str) -> dict[str, Callable]:
    """Get filtered tool executors for a specific agent.

    Tries DB lookup first, falls back to static AGENT_TOOL_MAPPING.
    """
    try:
        from agents.utility.util_database import get_session, ensure_table
        from agents.utility.util_datamodel import AgentDefinition, AgentToolMapping

        ensure_table(AgentDefinition)
        ensure_table(AgentToolMapping)
        with get_session() as session:
            agent_id = _resolve_agent_id(session, agent_name)
            if agent_id is not None:
                rows = (
                    session.query(AgentToolMapping)
                    .filter(AgentToolMapping.agent_id == agent_id, AgentToolMapping.is_active == True)
                    .all()
                )
                if rows:
                    executors = {}
                    for r in rows:
                        exec_name = r.executor_name or r.tool_name
                        if exec_name in ALL_TOOL_EXECUTORS:
                            executors[r.tool_name] = ALL_TOOL_EXECUTORS[exec_name]
                    logging.info(f"Loaded {len(executors)} tool executors for agent '{agent_name}' from DB")
                    return executors
    except Exception as e:
        logging.warning(f"DB lookup failed for tool executors '{agent_name}', using fallback: {e}")

    # Fallback to static mapping
    tool_names = AGENT_TOOL_MAPPING.get(agent_name, [])

    if not tool_names:
        logging.warning(f"No tools mapped for agent: {agent_name}")
        return {}

    executors = {
        name: ALL_TOOL_EXECUTORS[name]
        for name in tool_names
        if name in ALL_TOOL_EXECUTORS
    }

    logging.info(f"Loaded {len(executors)} tool executors for agent '{agent_name}'")
    return executors


def get_tool_definitions(agent_name: str) -> list[dict[str, Any]]:
    """Get filtered tool definitions for a specific agent.

    Tries DB+Blob lookup first, falls back to static mapping.
    """
    try:
        from agents.utility.util_database import get_session, ensure_table
        from agents.utility.util_datamodel import AgentDefinition, AgentToolMapping
        from agents.utility.util_blob import get_blob_text

        ensure_table(AgentDefinition)
        ensure_table(AgentToolMapping)
        with get_session() as session:
            agent_id = _resolve_agent_id(session, agent_name)
            if agent_id is not None:
                rows = (
                    session.query(AgentToolMapping)
                    .filter(AgentToolMapping.agent_id == agent_id, AgentToolMapping.is_active == True)
                    .all()
                )
                if rows:
                    definitions = []
                    for r in rows:
                        try:
                            schema = json.loads(get_blob_text(r.blob_path))
                            tool_def = _load_tool_definition(schema)
                            definitions.append({"type": "function", "function": tool_def})
                        except Exception as exc:
                            logging.warning(f"Failed to load blob tool def {r.blob_path}: {exc}")
                    return definitions
    except Exception as e:
        logging.warning(f"DB/Blob lookup failed for tool definitions '{agent_name}', using fallback: {e}")

    # Fallback to static mapping
    tool_names = AGENT_TOOL_MAPPING.get(agent_name, [])

    if not tool_names:
        return []

    definitions = [
        {"type": "function", "function": ALL_TOOL_DEFINITIONS[name]}
        for name in tool_names
        if name in ALL_TOOL_DEFINITIONS
    ]

    return definitions
