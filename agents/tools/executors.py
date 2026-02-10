"""
Consolidated Tool Executors - Single Source of Truth

All agent tool executor functions are defined here.
Use get_tool_executors(agent_name) to get the filtered set for a specific agent.
"""

import logging
import os
import time
import types
from typing import Any


# =============================================================================
# NON-HTTP FUNCTIONS
# =============================================================================

def determine_recipient(agent_type, status=None, student_email=None, confidence=None, **_):
    from agents.utility.util_notifications import determine_recipient as _determine

    payload = {"status": status, "confidence": confidence or 0}
    context = {"student_email": student_email}

    try:
        return _determine(agent_type=agent_type, payload=payload, context=context)
    except Exception as e:
        logging.error(f"determine_recipient error: {e}")
        return {"skip": False, "recipient": os.getenv("NUS_EMAIL", ""), "recipient_type": "admin", "error": str(e)}


def send_email_notification(recipient, recipient_type, agent_type, subject,
                            sections, cc=None, student_email=None,
                            attachment_content=None, course_code="DBA5115",
                            message_id="N/A", student_config_id=None, **_):
    """Render sections into HTML and send the email in one step."""
    from pathlib import Path
    from jinja2 import Template
    from datetime import datetime
    from shared import get_gmail_service, send_email

    # Render HTML from sections
    template_dir = Path(__file__).resolve().parent.parent / "templates"
    section_templates = {}
    for st in ["executive_summary", "status_box", "resource_list", "next_steps", "alert", "code_block", "bullet_list"]:
        tp = template_dir / "sections" / f"{st}.html"
        if tp.exists():
            with open(tp, 'r', encoding='utf-8') as f:
                section_templates[st] = Template(f.read())

    body_html = ""
    for section in (sections or []):
        st = section.get("type")
        if st not in section_templates:
            continue
        try:
            body_html += section_templates[st].render(**section) + "\n"
        except Exception as e:
            logging.error(f"Failed to render section {st}: {e}")

    full_html = body_html or "<p>No content available</p>"
    main_template_path = template_dir / "email_notification.html"
    if main_template_path.exists():
        try:
            with open(main_template_path, 'r', encoding='utf-8') as f:
                template = Template(f.read())
            full_html = template.render(
                subject=subject, course_code=course_code, body_html=body_html,
                metadata={"message_id": message_id, "student_config_id": student_config_id},
                current_year=datetime.now().year
            )
        except Exception as e:
            logging.error(f"Failed to render email template: {e}")

    # Send email
    try:
        attachments = None
        if attachment_content:
            safe_email = (student_email or "unknown").replace("@", "_at_").replace(".", "_")
            attachments = [{"filename": f"{agent_type}_{safe_email}.txt", "content": attachment_content}]

        service = get_gmail_service()
        reply_to = os.getenv("NUS_EMAIL")

        for attempt in range(3):
            try:
                send_email(service, recipient, subject, full_html,
                           attachments=attachments, cc=cc, reply_to=reply_to)
                break
            except Exception as e:
                if attempt == 2:
                    raise
                time.sleep((2 ** attempt) * 2)

        return {"status": "success", "recipient": recipient, "cc": cc, "subject": subject}
    except Exception as e:
        logging.error(f"Failed to send email to {recipient}: {e}")
        return {"status": "error", "recipient": recipient, "reason": str(e)}


# =============================================================================
# EXPORTS
# =============================================================================

ALL_TOOL_EXECUTORS = {
    name: obj
    for name, obj in globals().items()
    if isinstance(obj, types.FunctionType) and not name.startswith("_")
}
