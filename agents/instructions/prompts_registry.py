# agents/instructions/prompts_registry.py
import logging
from pathlib import Path

PROMPTS = {
    "email_triage": "agents/instructions/email_triage.system.md",
    "notification_content": "agents/instructions/notification_content.system.md",
}


def get_prompt(name: str) -> str:
    """Load prompt from DB+Blob, falling back to filesystem.

    Resolves agent name → AgentDefinition.id → AgentPromptRegistry row.
    """
    try:
        from agents.utility.util_database import get_session, ensure_table
        from agents.utility.util_datamodel import AgentDefinition, AgentPromptRegistry
        from agents.utility.util_blob import get_blob_text

        ensure_table(AgentDefinition)
        ensure_table(AgentPromptRegistry)
        with get_session() as session:
            agent_def = (
                session.query(AgentDefinition)
                .filter(AgentDefinition.name == name, AgentDefinition.is_active == True)
                .first()
            )
            if agent_def:
                row = (
                    session.query(AgentPromptRegistry)
                    .filter(AgentPromptRegistry.agent_id == agent_def.id, AgentPromptRegistry.is_active == True)
                    .first()
                )
                if row:
                    return get_blob_text(row.blob_path)
    except Exception as e:
        logging.warning(f"Blob/DB lookup failed for prompt '{name}', using filesystem fallback: {e}")

    # Filesystem fallback
    return Path(PROMPTS[name]).read_text(encoding="utf-8")
