# agents/instructions/prompts_registry.py
import logging
from pathlib import Path

PROMPTS = {
    "email_triage": "agents/instructions/email_triage.system.md",
    "notification_content": "agents/instructions/notification_content.system.md",
}


def get_prompt(name: str) -> str:
    """Load prompt from DB+Blob, falling back to filesystem."""
    try:
        from agents.utility.util_database import get_session, ensure_table
        from agents.utility.util_datamodel import AgentPromptRegistry
        from agents.utility.util_blob import get_blob_text

        ensure_table(AgentPromptRegistry)
        with get_session() as session:
            row = (
                session.query(AgentPromptRegistry)
                .filter(AgentPromptRegistry.agent_type == name, AgentPromptRegistry.is_active == True)
                .first()
            )
            if row:
                return get_blob_text(row.blob_path)
    except Exception as e:
        logging.warning(f"Blob/DB lookup failed for prompt '{name}', using filesystem fallback: {e}")

    # Filesystem fallback
    return Path(PROMPTS[name]).read_text(encoding="utf-8")
