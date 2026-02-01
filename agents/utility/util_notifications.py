"""
Notification Utility Functions

Helper functions for notification routing and recipient determination.
In this template, all notifications route to the admin (NUS_EMAIL).
"""

import os


def determine_recipient(agent_type: str, payload: dict, context: dict) -> dict:
    """
    Determine notification recipient based on agent type and status.

    In this template, all notifications go to the admin email.
    Customize this function to route to different recipients based on
    agent_type, payload status, or context.

    Args:
        agent_type: Type of agent (e.g., "actionable", "informational")
        payload: Basic tracking data (status, confidence, etc.)
        context: Rich content data (student_email, etc.)

    Returns:
        {
          "skip": bool,
          "recipient": str,
          "cc": str or None,
          "recipient_type": "admin"
        }
    """
    admin_email = os.getenv("NUS_EMAIL", "")

    # out_of_scope: no notification
    if agent_type == "out_of_scope":
        return {"skip": True}

    # Default: all notifications go to admin
    return {
        "skip": False,
        "recipient": admin_email,
        "cc": None,
        "recipient_type": "admin"
    }
