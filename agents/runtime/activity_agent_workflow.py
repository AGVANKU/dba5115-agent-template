"""
Unified Agent Workflow Activity - Standardized agent execution.

Single activity that can run any agent type with consistent:
- Input handling (AgentWorkflowInput)
- Agent execution (get_agent → create_thread → create_message → get_agent_response)
- Output with routing (AgentResponse with next_action)
"""

import json
import logging
import os
from dataclasses import asdict

# Suppress verbose AMQP connection state logs
logging.getLogger("uamqp").setLevel(logging.WARNING)
logging.getLogger("uamqp.connection").setLevel(logging.ERROR)
logging.getLogger("uamqp.session").setLevel(logging.ERROR)
logging.getLogger("uamqp.link").setLevel(logging.ERROR)

from queues.queues import bp
from agents.runtime.util_classes import AgentResponse, AgentWorkflowInput, NextAction
from agents.runtime.util_agents import get_agent, create_thread, create_message, get_agent_response
from shared import publish_to_service_bus


SERVICE_BUS_CONNECTION_STRING = os.environ.get("SERVICE_BUS_CONNECTION_STRING")

# Queue names
QUEUE_AGENT_WORKFLOW = "agent-workflow"


@bp.activity_trigger(input_name="workflowInput")
def run_agent_workflow(workflowInput: dict) -> dict:
    """
    Universal agent execution activity.
    
    Standardizes:
    - Agent loading (get_agent)
    - Thread creation (create_thread)
    - Message creation (create_message)
    - Response retrieval (get_agent_response)
    - Routing decision (next_action)
    
    Input (AgentWorkflowInput):
    - agent_type: Which agent to run ("email_triage", "student_sp_config", etc.)
    - payload: All input data for the agent (email, student info, etc.)
    
    Output: dict representation of AgentResponse object
    - status, responses, thread_id, usage, etc.
    - agent_type: Which agent produced this
    - next_action: What the orchestrator should queue next
    
    Note: Returns dict via asdict() for Durable Functions serialization
    """
    # Parse input
    input_data = AgentWorkflowInput(
        agent_type=workflowInput.get("agent_type"),
        payload=workflowInput.get("payload", {})
    )
    
    agent_type = input_data.agent_type
    logging.info(f"Running agent workflow: {agent_type}")

    try:
        # Load agent
        agent = get_agent(agent_type)

        # Create thread first so we can inject thread_id into agent input
        thread = create_thread(agent.agent_client)

        # Use payload as-is for agent input
        agent_input = input_data.payload.copy() if isinstance(input_data.payload, dict) else {}

        # Add thread_id for agents that need to call update functions
        agent_input["agent_thread_id"] = thread.id
        
        create_message(
            agent.agent_client,
            thread_id=thread.id,
            content=json.dumps(agent_input),
            role="user"
        )
        
        # Execute agent
        agent_response = get_agent_response(
            agent.agent_client,
            agent.agent.id,
            thread.id,
            agent.tool_executors
        )
        
        if not agent_response:
            logging.error(f"No response from agent: {agent_type}")
            return asdict(AgentResponse(
                status="error",
                responses=[],
                reason=f"No response from agent: {agent_type}",
                agent_type=agent_type
            ))

        # Extract metadata from agent response for analytics
        first_resp = agent_response.responses[0] if agent_response.responses else {}
        if isinstance(first_resp, dict):
            agent_response.metadata = first_resp.get("metadata")

        # Enrich response with workflow metadata
        agent_response.agent_type = agent_type
        agent_response.model_name = agent.agent.model  # Capture actual model used
        agent_response.next_action = _determine_next_action(
            agent_type=agent_type,
            response=agent_response
        )
        
        logging.info(
            f"Agent workflow completed: {agent_type} | status={agent_response.status} | "
            f"responses={len(agent_response.responses)} | next={agent_response.next_action.target_queue if agent_response.next_action else 'none'}"
        )
        
        return asdict(agent_response)
    
    except Exception as e:
        logging.exception(f"Agent workflow failed: {agent_type}")
        return asdict(AgentResponse(
            status="error",
            responses=[],
            reason=str(e),
            agent_type=agent_type
        ))


def _determine_next_action(
    agent_type: str,
    response: AgentResponse
) -> NextAction | None:
    """
    Extract routing decision from agent response (agent-driven routing).
    
    Agents return a 'next_action' field to control workflow routing.
    
    Expected agent response format:
    {
      "status": "success|failed|error",
      "message": "...",
      "result": {...},
      "next_action": {
        "target_queue": "agent-workflow|none",
        "payload": {...}  // All data needed by next agent
      }
    }
    
    If no next_action: workflow stops (orchestrator completes).
    """
    # Parse agent's first response
    first_response = response.responses[0] if response.responses else {}
    
    # If response is wrapped in {'raw': '...'}, extract the raw content
    if isinstance(first_response, dict) and 'raw' in first_response:
        first_response = first_response['raw']
        if agent_type in ["notification_content", "deployment", "troubleshooting"]:
            logging.info(f"Extracted 'raw' field, type: {type(first_response)}")
    
    # If response is a string, try to parse as JSON
    if isinstance(first_response, str):
        try:
            first_response = json.loads(first_response)
            if agent_type in ["notification_content", "deployment", "troubleshooting"]:
                logging.info(f"Successfully parsed JSON, type: {type(first_response)}")
                logging.info(f"Parsed structure keys: {first_response.keys() if isinstance(first_response, dict) else 'not a dict'}")
        except json.JSONDecodeError as e:
            logging.warning(f"Agent {agent_type} returned non-JSON response, cannot extract next_action")
            if agent_type in ["notification_content", "deployment", "troubleshooting"]:
                logging.error(f"JSON parse failed: {e}")
                logging.error(f"Response (first 1000 chars): {first_response[:1000]}")
            return None
    
    # Extract next_action from agent's response
    agent_next_action = first_response.get("next_action") if isinstance(first_response, dict) else None

    if not agent_next_action:
        # Agent chose not to route anywhere (terminal state or orchestrator handles it)
        # For deployment agent: this is expected when provisioning is in progress (orchestrator will queue back)
        # For other agents: this means workflow is complete
        logging.info(f"Agent {agent_type} provided no next_action - workflow stopping (orchestrator may queue back if needed)")
        return None
    
    # Validate next_action structure
    if not isinstance(agent_next_action, dict):
        logging.error(f"Agent {agent_type} returned invalid next_action (not a dict): {type(agent_next_action)}")
        return None
    
    target_queue = agent_next_action.get("target_queue")
    if not target_queue or target_queue == "none":
        logging.info(f"Agent {agent_type} set target_queue to 'none' - workflow complete")
        return None
    
    # Valid routing decision from agent - pass payload through as-is
    payload = agent_next_action.get("payload", {})
    
    logging.info(f"Agent {agent_type} routing to: {target_queue}")
    return NextAction(
        target_queue=target_queue,
        payload=payload
    )


@bp.activity_trigger(input_name="queueInput")
def queue_message(queueInput: dict) -> dict:
    """
    Generic activity to send a message to any Service Bus queue.
    
    Input:
    - queue: Target queue name
    - payload: Message body (dict)
    
    Returns:
    - {"status": "success", "queue": str, "attempts": int} on success
    - {"status": "error", "reason": str, "attempts": int} on failure
    """
    queue_name = queueInput.get("queue")
    payload = queueInput.get("payload", {})
    
    if not queue_name:
        return {"status": "error", "reason": "No queue name provided", "attempts": 0}
    
    # Use shared utility with retry logic (3 attempts)
    return publish_to_service_bus(
        queue_name=queue_name,
        message=payload,
        ensure_queue=False,
        max_retries=3,
        retry_delays=[2, 5, 10]
    )
