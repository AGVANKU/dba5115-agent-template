"""
Shared utilities used across hooks, agents, and tools layers.
"""

from shared.util_response import json_response
from shared.util_gmail import (
    get_gmail_service,
    get_unread_message_ids,
    fetch_message_raw,
    parse_email_message,
    mark_as_read,
    send_email,
    send_email_smtp,
)
from shared.util_service_bus import (
    ensure_queue_exists,
    publish_to_service_bus,
)

__all__ = [
    "json_response",
    "get_gmail_service",
    "get_unread_message_ids",
    "fetch_message_raw",
    "parse_email_message",
    "mark_as_read",
    "send_email",
    "send_email_smtp",
    "ensure_queue_exists",
    "publish_to_service_bus",
]
