# agents/instructions/prompts_registry.py
from pathlib import Path

PROMPTS = {
    "email_triage": "agents/instructions/email_triage.system.md",
    "notification_content": "agents/instructions/notification_content.system.md",
}

def get_prompt(name: str) -> str:
    return Path(PROMPTS[name]).read_text(encoding="utf-8")
