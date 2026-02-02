"""
Agents Blueprint - AI agent orchestration layer with Durable Functions.

Structure:
- agents.py                               → Blueprint + Service Bus triggers (this file)
- orchestrators/orchestrator_agent_workflow.py   → Single generic orchestrator for all agent types
- app/activity_agent_workflow.py          → Activities: run_agent_workflow, queue_message

Each module imports `bp` and registers its decorated functions.
"""

import json
import logging
import azure.functions as func
import azure.durable_functions as df

from shared import ensure_queue_exists, get_gmail_service, get_unread_message_ids, fetch_message_raw, parse_email_message, mark_as_read


# =============================================================================
# BLUEPRINT - Created first, then modules import it and register decorators
# =============================================================================

bp = df.Blueprint()


# =============================================================================
# SERVICE BUS QUEUE INITIALIZATION
# =============================================================================

REQUIRED_QUEUES = ["hook-gmail", "agent-workflow"]
for queue_name in REQUIRED_QUEUES:
    ensure_queue_exists(queue_name)


# =============================================================================
# SERVICE BUS TRIGGERS
# =============================================================================

@bp.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="hook-gmail",
    connection="SERVICE_BUS_CONNECTION_STRING"
)
@bp.durable_client_input(client_name="client")
async def gmail_queue_consumer(msg: func.ServiceBusMessage, client: df.DurableOrchestrationClient):
    """
    Process Gmail queue trigger - fetch unread emails and start orchestrations.

    The hook only queues a lightweight trigger. This consumer:
    1. Fetches unread email IDs from Gmail API
    2. Starts an orchestration for each email (with deduplication)
    """
    try:
        body = json.loads(msg.get_body().decode('utf-8'))
        if body.get("type") != "check_inbox":
            logging.warning(f"Unknown queue message format: {body}")
            return

        service = get_gmail_service()
        message_ids = get_unread_message_ids(service, trigger_body=body)

        source = body.get("source", "unknown")
        logging.info(f"Found {len(message_ids)} unread email(s) (source={source})")

        started = 0
        for msg_id in message_ids:
            # Pre-fetch email so triage agent receives full content (no tool calls needed)
            try:
                msg_data = fetch_message_raw(service, msg_id)
                parsed = parse_email_message(msg_data)
                parsed["message_id"] = msg_id
                logging.info(f"Pre-fetched email {msg_id}: {parsed.get('subject', 'no subject')}")
                mark_as_read(service, msg_id)
                logging.info(f"Marked email {msg_id} as read")
            except Exception as e:
                logging.error(f"Failed to pre-fetch email {msg_id}: {e}")
                parsed = None

            body = {"agent_type": "email_triage", "source": "gmail", "message_id": msg_id}
            if parsed:
                body["email"] = parsed

            result = await _start_orchestration(
                client,
                instance_id=f"gmail-{msg_id}",
                body=body
            )
            if result:
                started += 1

        logging.info(f"Orchestrations: {started} started, {len(message_ids) - started} skipped")

    except Exception as e:
        logging.exception(f"Failed to process gmail queue message: {e}")
        raise


@bp.service_bus_queue_trigger(
    arg_name="msg",
    queue_name="agent-workflow",
    connection="SERVICE_BUS_CONNECTION_STRING"
)
@bp.durable_client_input(client_name="client")
async def agent_workflow_queue_consumer(msg: func.ServiceBusMessage, client: df.DurableOrchestrationClient):
    """
    Process agent workflow queue - single entry point for all agent workflows.

    Receives workflow requests (from triage, action agents, or notification routing)
    and starts orchestrate_agent_workflow for each.
    """
    try:
        body = json.loads(msg.get_body().decode('utf-8'))
        agent_type = body.get("agent_type")

        # Resolve message_id for dedup instance ID
        # Include timestamp to avoid collisions with stuck orchestrations
        import time
        ts = int(time.time() * 1000)
        message_id = body.get("message_id")
        if not message_id or message_id == "unknown":
            student_config_id = body.get("student_config_id")
            if student_config_id:
                message_id = f"student{student_config_id}-{ts}"
            else:
                message_id = f"ts{ts}"
        else:
            message_id = f"{message_id}-{ts}"

        await _start_orchestration(
            client,
            instance_id=f"agent-{agent_type}-{message_id}",
            body=body
        )

    except Exception as e:
        logging.exception(f"Failed to process workflow queue message: {e}")
        raise


# =============================================================================
# SHARED HELPER
# =============================================================================

async def _start_orchestration(client: df.DurableOrchestrationClient, instance_id: str, body: dict) -> bool:
    """Start orchestrate_agent_workflow with dedup. Returns True if started, False if skipped."""
    status = await client.get_status(instance_id)
    if status and status.runtime_status in [
        df.OrchestrationRuntimeStatus.Running,
        df.OrchestrationRuntimeStatus.Pending,
    ]:
        logging.info(f"Orchestration {instance_id} already running, skipping")
        return False

    # Purge completed/failed/terminated instances so the ID can be reused
    if status and status.runtime_status in [
        df.OrchestrationRuntimeStatus.Completed,
        df.OrchestrationRuntimeStatus.Failed,
        df.OrchestrationRuntimeStatus.Terminated,
    ]:
        await client.purge_instance_history(instance_id)
        logging.info(f"Purged old orchestration {instance_id} (was {status.runtime_status})")

    try:
        await client.start_new(
            "orchestrate_agent_workflow",
            instance_id=instance_id,
            client_input=body
        )
        logging.info(f"Started orchestration: {instance_id}")
        return True
    except Exception as e:
        if "already exists" in str(e).lower():
            logging.info(f"Orchestration {instance_id} already exists (race condition), skipping")
            return False
        raise


# =============================================================================
# IMPORT MODULES - Their decorators register on bp when imported
# =============================================================================

from agents.runtime import orchestrator_agent_workflow               # registers orchestrate_agent_workflow
from agents.runtime import activity_agent_workflow            # registers run_agent_workflow, queue_message
