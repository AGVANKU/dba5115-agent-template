"""
Generic Orchestrator - Single orchestrator for all agent types.

Flow:
1. Parse input: extract agent_type, message_id
2. Call run_agent_workflow(agent_type, payload)
3. Track token usage (generic, using agent-returned metadata)
4. If next_action exists -> queue_message to target_queue
5. Return summary
"""

import logging
from datetime import datetime
import azure.durable_functions as df

from queues.queues import bp
from agents.runtime.util_classes import AgentResponse
from shared.util_token_tracking import track_token_usage


@bp.orchestration_trigger(context_name="context")
def orchestrate_agent_workflow(context: df.DurableOrchestrationContext):
    """
    Generic orchestrator - runs any agent type identically.

    No agent-specific logic. Every agent is treated the same:
    receive -> run agent -> track tokens -> route.
    """
    input_data = context.get_input()
    agent_type = input_data.get("agent_type")
    message_id = input_data.get("message_id", "unknown")

    if not context.is_replaying:
        logging.info(f"Generic orchestrator: agent={agent_type}, message={message_id}")

    # Run agent workflow
    workflow_start = datetime.utcnow()
    result_dict = yield context.call_activity("run_agent_workflow", {
        "agent_type": agent_type,
        "payload": input_data
    })
    result = AgentResponse.from_dict(result_dict)

    # Track tokens using agent-provided metadata
    if not context.is_replaying:
        metadata = result.metadata or {}
        track_token_usage(
            student_config_id=input_data.get("student_config_id"),
            student_id=input_data.get("StudentId") or input_data.get("student_id"),
            agent_type=agent_type,
            agent_operation=metadata.get("operation_detail") or input_data.get("operation"),
            model_name=result.model_name or "gpt-4.1-mini",
            input_tokens=result.usage.prompt_tokens if result.usage else 0,
            output_tokens=result.usage.completion_tokens if result.usage else 0,
            inference_rounds=result.inference_rounds or 0,
            description=metadata.get("description") or f"{agent_type} workflow",
            started_at=workflow_start,
            completed_at=datetime.utcnow()
        )

    # Route based on agent's decision
    next_action = result.next_action
    if next_action:
        if not context.is_replaying:
            logging.info(f"Generic orchestrator queuing to: {next_action.target_queue}")

        yield context.call_activity("queue_message", {
            "queue": next_action.target_queue,
            "payload": next_action.payload
        })

    return {
        "status": "completed",
        "agent_type": agent_type,
        "message_id": message_id,
        "next_queue": next_action.target_queue if next_action else None,
        "total_tokens": result.usage.total_tokens if result.usage else 0,
    }
