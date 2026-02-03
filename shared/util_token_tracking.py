"""
Token tracking utility for LLM usage analytics.

Provides fail-safe token usage tracking that never disrupts the main workflow.
"""

import logging
from datetime import datetime
from typing import Optional

from agents.utility.util_datamodel import LLMTokenUsage
from agents.utility.util_database import SessionLocal


def ensure_token_usage_table() -> None:
    """Ensure the LLMTokenUsage table exists. Called on app startup."""
    try:
        from agents.utility.util_database import ensure_table
        ensure_table(LLMTokenUsage)
        logging.info("LLMTokenUsage table verified/created")
    except Exception as e:
        logging.warning(f"Could not ensure LLMTokenUsage table: {e}")


def track_token_usage(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    started_at: datetime,
    agent_id: Optional[int] = None,
    agent_type: Optional[str] = None,
    student_config_id: Optional[int] = None,
    student_id: Optional[str] = None,
    agent_operation: Optional[str] = None,
    inference_rounds: Optional[int] = None,
    description: Optional[str] = None,
    completed_at: Optional[datetime] = None
) -> dict:
    """
    Track LLM token usage for analytics. Fail-safe - never raises exceptions.

    Args:
        model_name: The LLM model used (e.g., "gpt-4o-mini")
        input_tokens: Number of input/prompt tokens
        output_tokens: Number of output/completion tokens
        agent_type: Type of agent (e.g., "email_triage", "notification_content")
        started_at: When the agent execution started
        student_config_id: Ignored in template (no StudentConfig table)
        student_id: Ignored in template (no StudentConfig table)
        agent_operation: Operation type (e.g., "triage")
        inference_rounds: Number of LLM inference rounds
        description: Human-readable description
        completed_at: When the agent execution completed (defaults to now)

    Returns:
        {"success": bool, "id": int (if success), "error": str (if failed)}
    """
    try:
        if not model_name:
            return {"success": False, "error": "model_name is required"}
        if not agent_id and not agent_type:
            return {"success": False, "error": "agent_id or agent_type is required"}

        if input_tokens < 0 or output_tokens < 0:
            return {"success": False, "error": "Token counts cannot be negative"}

        if completed_at is None:
            completed_at = datetime.utcnow()

        if description and len(description) > 500:
            description = description[:497] + "..."

        if SessionLocal is None:
            logging.warning("SessionLocal is None - database not configured. Token usage NOT saved.")
            return {"success": False, "error": "Database not configured"}

        session = SessionLocal()
        try:
            record = LLMTokenUsage(
                agent_id=agent_id,
                agent_type=agent_type,
                agent_operation=agent_operation,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                inference_rounds=inference_rounds or 0,
                description=description,
                started_at=started_at,
                completed_at=completed_at
            )

            session.add(record)
            session.commit()

            record_id = record.id
            session.close()

            logging.info(
                f"Token tracking saved: agent={agent_type}, model={model_name}, "
                f"tokens={input_tokens + output_tokens}, id={record_id}"
            )

            return {"success": True, "id": record_id}

        except Exception as e:
            session.rollback()
            session.close()
            raise e

    except Exception as e:
        error_msg = f"Failed to track token usage: {e}"
        logging.warning(error_msg)

        # Fallback: Log to file for manual recovery
        try:
            import json
            from pathlib import Path

            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)

            fallback_file = log_dir / "token_usage_fallback.jsonl"
            with open(fallback_file, "a") as f:
                f.write(json.dumps({
                    "timestamp": datetime.utcnow().isoformat(),
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                    "agent_operation": agent_operation,
                    "model_name": model_name,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "inference_rounds": inference_rounds,
                    "description": description,
                    "started_at": started_at.isoformat() if started_at else None,
                    "completed_at": completed_at.isoformat() if completed_at else None,
                    "error": str(e)
                }) + "\n")
        except Exception as fallback_error:
            logging.warning(f"Fallback logging also failed: {fallback_error}")

        return {"success": False, "error": error_msg}
