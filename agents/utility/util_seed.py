"""
Auto-seed agent configuration into Azure Blob Storage + SQL.

Uploads default prompts and tool definitions from the repo filesystem,
then inserts default DB rows for AgentDefinition, AgentPromptRegistry,
and AgentToolMapping.
"""

import json
import logging
import os
from pathlib import Path

from .util_blob import ensure_container, upload_blob, list_blobs
from .util_database import ensure_table, get_session


DEFAULT_AGENT_MODEL = os.getenv("DEFAULT_AGENT_MODEL", "gpt-4o-mini")


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "instructions"


def _definitions_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "tools" / "definitions"


def seed_defaults() -> dict:
    """
    Idempotent seed: ensure tables + container, upload defaults if empty,
    insert default DB rows if empty.

    Returns summary dict with counts.
    """
    from .util_datamodel import AgentDefinition, AgentPromptRegistry, AgentToolMapping

    # 1. Ensure SQL tables (AgentDefinition first — FK dependency)
    ensure_table(AgentDefinition)
    ensure_table(AgentPromptRegistry)
    ensure_table(AgentToolMapping)

    # 2. Ensure blob container
    ensure_container()

    blobs_uploaded = 0
    agents_seeded = 0
    prompts_seeded = 0
    tools_seeded = 0

    # 3. Upload prompt files if no blobs under prompts/
    existing_prompt_blobs = list_blobs("prompts/")
    if not existing_prompt_blobs:
        for md_file in sorted(_prompts_dir().glob("*.system.md")):
            blob_path = f"prompts/{md_file.name}"
            upload_blob(blob_path, md_file.read_text(encoding="utf-8"))
            blobs_uploaded += 1

    # 4. Upload tool definition files if no blobs under tools/
    existing_tool_blobs = list_blobs("tools/")
    if not existing_tool_blobs:
        for json_file in sorted(_definitions_dir().glob("*.json")):
            blob_path = f"tools/{json_file.name}"
            json_file_text = json_file.read_text(encoding="utf-8")
            upload_blob(blob_path, json_file_text)
            blobs_uploaded += 1

    # 5. Seed AgentDefinition if empty
    agent_ids: dict[str, int] = {}  # name -> id
    with get_session() as session:
        count = session.query(AgentDefinition).count()
        if count == 0:
            for agent_name, desc in [
                ("email_triage", "Email triage agent — classifies and routes incoming emails"),
                ("notification_content", "Notification content agent — drafts notification messages"),
            ]:
                row = AgentDefinition(
                    name=agent_name,
                    description=desc,
                    model=DEFAULT_AGENT_MODEL,
                    is_active=True,
                )
                session.add(row)
                session.flush()
                agent_ids[agent_name] = row.id
                agents_seeded += 1
        else:
            # Load existing IDs
            for row in session.query(AgentDefinition).all():
                agent_ids[row.name] = row.id

    # 6. Seed AgentPromptRegistry if empty
    with get_session() as session:
        count = session.query(AgentPromptRegistry).count()
        if count == 0:
            from agents.instructions.prompts_registry import PROMPTS

            for agent_name, file_path in PROMPTS.items():
                agent_id = agent_ids.get(agent_name)
                if agent_id is None:
                    logging.warning(f"No AgentDefinition found for '{agent_name}', skipping prompt seed")
                    continue
                filename = Path(file_path).name
                blob_path = f"prompts/{filename}"
                row = AgentPromptRegistry(
                    agent_id=agent_id,
                    blob_path=blob_path,
                    description=f"System prompt for {agent_name}",
                    is_active=True,
                )
                session.add(row)
                prompts_seeded += 1

    # 7. Seed AgentToolMapping if empty
    with get_session() as session:
        count = session.query(AgentToolMapping).count()
        if count == 0:
            from agents.tools.registry import AGENT_TOOL_MAPPING
            from agents.tools.executors import ALL_TOOL_EXECUTORS

            # Build tool_name -> json filename mapping from definitions dir
            tool_name_to_file = {}
            for json_file in _definitions_dir().glob("*.json"):
                try:
                    schema = json.loads(json_file.read_text(encoding="utf-8"))
                    if "name" in schema:
                        tool_name_to_file[schema["name"]] = json_file.name
                except Exception:
                    continue

            for agent_name, tool_names in AGENT_TOOL_MAPPING.items():
                agent_id = agent_ids.get(agent_name)
                if agent_id is None:
                    logging.warning(f"No AgentDefinition found for '{agent_name}', skipping tool seed")
                    continue
                for tool_name in tool_names:
                    json_filename = tool_name_to_file.get(tool_name)
                    if not json_filename:
                        continue
                    executor_name = tool_name if tool_name in ALL_TOOL_EXECUTORS else ""
                    row = AgentToolMapping(
                        agent_id=agent_id,
                        tool_name=tool_name,
                        blob_path=f"tools/{json_filename}",
                        executor_name=executor_name,
                        is_active=True,
                    )
                    session.add(row)
                    tools_seeded += 1

    logging.info(
        f"Seed complete: blobs_uploaded={blobs_uploaded}, agents_seeded={agents_seeded}, "
        f"prompts_seeded={prompts_seeded}, tools_seeded={tools_seeded}"
    )
    return {
        "status": "ok",
        "blobs_uploaded": blobs_uploaded,
        "agents_seeded": agents_seeded,
        "prompts_seeded": prompts_seeded,
        "tools_seeded": tools_seeded,
    }
