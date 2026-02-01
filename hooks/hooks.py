"""
Hooks Blueprint - Simple pull-based Gmail endpoint.

This layer:
- Provides authenticated pull endpoint for Gmail inbox checking
- Publishes messages to Service Bus queues for async processing

The hooks layer is the entry point for external events into the platform.
Agents layer consumes the Service Bus queues.
"""

import azure.functions as func
import logging
from datetime import datetime

from shared import json_response, publish_to_service_bus

bp = func.Blueprint()


# =============================================================================
# GMAIL PULL ENDPOINT
# =============================================================================

@bp.timer_trigger(schedule="0 */2 * * * *", arg_name="timer", run_on_startup=False)
def gmail_timer_pull(timer: func.TimerRequest) -> None:
    """
    Timer trigger for periodic Gmail inbox checking.
    
    Runs every 2 minutes. Only fetches emails received since last trigger
    to avoid re-processing emails that are still being handled by agents.
    """
    logging.info("Gmail timer trigger fired")
    
    if timer.past_due:
        logging.warning("Timer is past due - running anyway")
    
    # Create trigger message with interval info
    message = {
        "source": "gmail_timer_trigger",
        "type": "check_inbox",
        "triggered_at": datetime.utcnow().isoformat(),
        "interval_minutes": 2  # Must match timer schedule (0 */2 * * * *)
    }
    
    # Publish to Service Bus
    queue_name = "hook-gmail"
    result = publish_to_service_bus(queue_name, message, ensure_queue=False)
    
    logging.info(f"Timer trigger queued: {result.get('status')}")


@bp.route(route="hooks/gmail_pull", methods=["POST", "GET"], auth_level=func.AuthLevel.FUNCTION)
def gmail_pull_handler(req: func.HttpRequest) -> func.HttpResponse:
    """
    Pull-based Gmail endpoint - triggers inbox check with email filtering.
    
    POST/GET /api/hooks/gmail_pull
    Requires: x-functions-key header for authentication
    
    Security:
    - Authentication required (FUNCTION level)
    - Filter email determined by NUS_EMAIL environment variable
    - Cannot be overridden via query parameters
    
    This queues a trigger message to check inbox:
    1. Queues ONE trigger message saying "check inbox"
    2. Orchestrator fetches unread emails filtered by NUS_EMAIL env variable
    
    Simple alternative to hooks push for student deployments.
    
    Returns:
        {
            "status": "success" | "error",
            "queued": bool
        }
    """
    logging.info("Gmail pull requested (authenticated)")
    
    # Create trigger message (orchestrator will use NUS_EMAIL env)
    message = {
        "source": "gmail_pull",
        "type": "check_inbox",
        "triggered_at": datetime.utcnow().isoformat(),
    }
    
    # Publish to Service Bus
    queue_name = "hook-gmail"
    result = publish_to_service_bus(queue_name, message, ensure_queue=True)
    
    return json_response({
        "status": result.get("status"),
        "queue": queue_name,
        "queued": result.get("status") == "success"
    }, 200)

