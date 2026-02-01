import os
import time
import json
import logging
from pathlib import Path

# Suppress verbose Azure SDK logs
logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.identity").setLevel(logging.WARNING)
logging.getLogger("uamqp").setLevel(logging.WARNING)
logging.getLogger("uamqp.connection").setLevel(logging.ERROR)
logging.getLogger("uamqp.session").setLevel(logging.ERROR)
logging.getLogger("uamqp.link").setLevel(logging.ERROR)
logging.getLogger("uamqp.mgmt_operation").setLevel(logging.ERROR)

from azure.ai.agents import AgentsClient
from azure.ai.agents.models import MessageRole, AzureAISearchTool, AzureAISearchQueryType
from azure.identity import ClientSecretCredential
from azure.ai.agents.models import ListSortOrder, Agent
from azure.core.exceptions import ServiceResponseTimeoutError, HttpResponseError

from agents.instructions.prompts_registry import get_prompt
from shared.util_resources import get_credential
from agents.runtime.util_classes import ManagedAgent, LoadedTools, TokenUsage, AgentResponse
from agents.tools.registry import get_tool_definitions, get_tool_executors

tenant_id = os.getenv("AZURE_TENANT_ID")
client_id = os.getenv("AZURE_CLIENT_ID")
client_secret = os.getenv("AZURE_CLIENT_SECRET")
model="gpt-4o-mini"  # Agent runtime model (separate from deployed models)
agent_endpoint = os.getenv("AZURE_AI_ENDPOINT")

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF = 5  # seconds

def _retry_with_backoff(func, *args, **kwargs):
    """
    Retry a function with exponential backoff on timeout or rate limit errors.
    """
    from azure.core.exceptions import DecodeError
    
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except (ServiceResponseTimeoutError, HttpResponseError, DecodeError) as e:
            last_error = e
            error_str = str(e).lower()
            # Check if it's a timeout or rate limit error
            if "timeout" in error_str or "rate_limit" in error_str or "429" in error_str or "timed out" in error_str:
                wait_time = INITIAL_BACKOFF * (2 ** attempt)
                logging.warning(f"=== RETRY === Attempt {attempt + 1}/{MAX_RETRIES} failed: {type(e).__name__}. Waiting {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise  # Re-raise if it's not a retryable error
    logging.error(f"=== RETRY EXHAUSTED === All {MAX_RETRIES} attempts failed")
    raise last_error


def get_agents_client(endpoint: str = None, credential: ClientSecretCredential = None) -> AgentsClient:
    """
    Initialize and return an AgentsClient for the given endpoint.
    """
    return AgentsClient(
        endpoint=endpoint if endpoint else agent_endpoint,
        credential=get_credential({
            "TenantId": tenant_id,
            "ClientId": client_id,
            "ClientSecret": client_secret
        }) if credential is None else credential
    )


def find_agent_by_name(client: AgentsClient, agent_name: str):
    """
    Find and return an agent by its name.
    """
    agents = client.list_agents()
    for agent in agents:
        if agent.name == agent_name:
            return agent
    return None


def delete_agent(client: AgentsClient, agent_id: str):
    client.delete_agent(agent_id)


def create_thread(client: AgentsClient):
    # _log_api_call("threads_create")
    thread = _retry_with_backoff(client.threads.create)
    return thread


def create_message(client: AgentsClient, thread_id: str, role: str, content: str):
    # _log_api_call("messages_create")
    message = _retry_with_backoff(
        client.messages.create,
        thread_id=thread_id,
        role=role,
        content=content
    )
    return message

def _safe_truncate(obj, max_len=1500):
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return s[:max_len] + ("..." if len(s) > max_len else "")

    
def get_agent_response(
    client: AgentsClient,
    agent_id: str,
    thread_id: str,
    tool_executors: dict[str, callable] | None = None
) -> AgentResponse | None:
    """
    Runs the agent and executes function tool calls when the run requires_action.
    tool_executors maps tool/function name -> python callable that returns JSON-serializable output.
    """
    tool_executors = tool_executors or {}
    
    # _log_api_call("runs_create")
    run = _retry_with_backoff(client.runs.create, agent_id=agent_id, thread_id=thread_id)
    
    # Track tokens PER INFERENCE ROUND (each poll may show accumulated tokens)
    inference_rounds = 0  # How many times the LLM was called
    tool_call_rounds = 0  # How many tool call submissions
    poll_count = 0  # Track how many times we poll
    MAX_TOOL_ITERATIONS = 20  # Prevent infinite loops

    while True:
        poll_count += 1
        logging.info(f"Run status: {run.status} (poll #{poll_count})")
                
        if run.status in ["queued", "in_progress"]:
            time.sleep(2)
            # _log_api_call("runs_get")
            run = _retry_with_backoff(client.runs.get, thread_id=thread_id, run_id=run.id)
            continue

        if run.status == "requires_action":
            tool_call_rounds += 1
            
            # Prevent infinite loops
            if tool_call_rounds > MAX_TOOL_ITERATIONS:
                logging.error(f"Agent exceeded max tool iterations ({MAX_TOOL_ITERATIONS}). Aborting.")
                return AgentResponse(
                    status="error",
                    responses=[],
                    reason=f"Exceeded maximum tool iterations ({MAX_TOOL_ITERATIONS}). Agent may be stuck in a loop.",
                    tool_calls=tool_call_rounds,
                    inference_rounds=inference_rounds,
                    polls=poll_count
                )
            
            ra = run.required_action
            if not ra:
                logging.error("Run requires_action but required_action is empty.")
                return None

            # Common SDK shape: required_action.submit_tool_outputs.tool_calls
            sto = getattr(ra, "submit_tool_outputs", None)
            tool_calls = getattr(sto, "tool_calls", None) if sto else None

            if not tool_calls:
                logging.error(f"Run requires_action but no tool_calls found. required_action={ra}")
                return None

            outputs = []
            has_function_calls = False  # Track if we have any function tool calls
            
            for tc in tool_calls:
                # Check tool call type - native Azure tools (azure_ai_search) execute server-side
                tc_type = getattr(tc, "type", None)
                if tc_type and tc_type != "function":
                    # Native Azure tool (e.g., azure_ai_search) - skip, handled server-side
                    logging.info("TOOL CALL skipped (server-side): type=%s", tc_type)
                    continue
                
                has_function_calls = True
                
                # Common shape: tc.id, tc.function.name, tc.function.arguments (JSON string)
                fn = getattr(tc, "function", None)
                name = getattr(fn, "name", None) if fn else None
                arg_str = getattr(fn, "arguments", "{}") if fn else "{}"

                if not name:
                    outputs.append({"tool_call_id": tc.id, "output": json.dumps({"status": "failed", "error": "missing tool name"})})
                    continue
                
                try:
                    args = json.loads(arg_str) if arg_str else {}
                except (json.JSONDecodeError, ValueError) as parse_err:
                    logging.error(f"Could not parse tool arguments for {name}: {parse_err}")
                    logging.error(f"Raw arg_str ({len(arg_str)} chars): {arg_str[:500]}...")
                    outputs.append({
                        "tool_call_id": tc.id,
                        "output": json.dumps({
                            "status": "failed",
                            "error": f"Invalid JSON arguments: {parse_err}. Please retry with valid JSON."
                        })
                    })
                    continue

                logging.info("TOOL CALL requested: %s args=%s", name, _safe_truncate(args))

                executor = tool_executors.get(name)
                if not executor:
                    outputs.append({
                        "tool_call_id": tc.id,
                        "output": json.dumps({"status": "failed", "error": f"no executor registered for tool '{name}'"})
                    })
                    continue

                try:
                    result = executor(**args)
                    result_str = json.dumps(result)
                    logging.info("TOOL RESULT for %s: %d chars | preview: %s", name, len(result_str), _safe_truncate(result, 500))
                    outputs.append({"tool_call_id": tc.id, "output": result_str})
                except Exception as e:
                    logging.exception(f"Tool execution failed for {name}")
                    outputs.append({"tool_call_id": tc.id, "output": json.dumps({"status": "failed", "error": str(e)})})
            
            # Only submit tool outputs if we have function calls to respond to
            if not has_function_calls:
                time.sleep(2)
                continue

            run = _retry_with_backoff(
                client.runs.submit_tool_outputs,
                thread_id=thread_id,
                run_id=run.id,
                tool_outputs=outputs
            )
            # then loop and poll again
            continue

        if run.status == "completed" or str(run.status).upper().endswith("COMPLETED"):
            break

        if run.status == "failed" or str(run.status).upper().endswith("FAILED"):
            logging.error(f"Run failed: {getattr(run, 'last_error', None)}")
            return AgentResponse(
                status="error",
                responses=[],
                reason=str(getattr(run, 'last_error', 'Run failed')),
                tool_calls=tool_call_rounds,
                inference_rounds=inference_rounds,
                polls=poll_count
            )
        
            
        # unknown terminal state
        logging.error(f"Unexpected run status: {run.status}")
        return None
    
    # Fetch responses (latest agent message)
    responses = []
    messages = client.messages.list(thread_id=thread_id, order=ListSortOrder.DESCENDING)
    for message in messages:
        # role might be MessageRole.AGENT or "assistant" depending on SDK; accept both
        if message.role == MessageRole.AGENT or str(message.role).lower() in ["assistant", "agent"]:
            for part in message.content:
                if part.type == "text":
                    text_val = part.text.value
                    try:
                        responses.append(json.loads(text_val))
                    except json.JSONDecodeError:
                        responses.append({"raw": text_val})
            break
    
    # Count messages in thread to understand context size
    thread_message_count = len(list(client.messages.list(thread_id=thread_id)))
    
    # Final token summary
    final_usage = getattr(run, "usage", None)
    final_prompt = final_usage.prompt_tokens if final_usage else 0
    final_completion = final_usage.completion_tokens if final_usage else 0
    
    logging.info(
        "=== FINAL TOKEN SUMMARY === prompt=%d completion=%d total=%d | inference_rounds=%d tool_rounds=%d | thread_messages=%d",
        final_prompt,
        final_completion,
        final_prompt + final_completion,
        inference_rounds,
        tool_call_rounds,
        thread_message_count,
    )
    
    return AgentResponse(
        status=responses[-1].get("status", "completed") if responses else "completed",
        responses=responses,
        thread_id=thread_id,
        usage=TokenUsage(
            prompt_tokens=final_prompt,
            completion_tokens=final_completion,
            total_tokens=final_prompt + final_completion,
            thread_messages=thread_message_count
        ),
        tool_calls=tool_call_rounds,
        inference_rounds=inference_rounds,
        polls=poll_count
    )


def get_agent(agent_type: str) -> ManagedAgent:
    """
    Get or create an agent.

    Tools are loaded from:
    - agents/tools/tool_registry.py (consolidated approach with automatic fallback)
    - get_knowledge() (Azure AI Search, server-side execution)

    Both are combined using: tools = get_tools_consolidated() + get_knowledge()
    """

    agent_client = get_agents_client()
    instructions = get_prompt(agent_type)

    # Combine function tools with knowledge tools (AI Search)
    tools = get_tools(agent_type)
    agent = find_agent_by_name(agent_client, agent_type)

    if not agent:
        agent = _retry_with_backoff(
            agent_client.create_agent,
            name=agent_type,
            instructions=instructions,
            model=model,
            tools=tools.definitions,
            tool_resources=tools.tool_resources,
            temperature=0)  # Deterministic output
        logging.info("=== AGENT CREATED === New agent '%s' (id=%s)", agent_type, agent.id)
    else:
        agent = _retry_with_backoff(
            agent_client.update_agent,
            agent_id=agent.id,
            instructions=instructions,
            model=model,
            tools=tools.definitions,
            tool_resources=tools.tool_resources,
            temperature=0)  # Deterministic output
        logging.info("=== AGENT UPDATED === Updated agent '%s' (id=%s)", agent_type, agent.id)

    return ManagedAgent(agent_client=agent_client, agent=agent, tool_executors=tools.executors)


def get_tools(agent_type: str) -> LoadedTools:
    """
    Load tools using consolidated approach.

    Args:
        agent_type: The agent type (e.g., 'deployment', 'troubleshooting')

    Returns:
        LoadedTools with definitions and executors

    Example:
        tools = get_tools('deployment')
    """
    definitions = get_tool_definitions(agent_type)
    executors = get_tool_executors(agent_type)

    if definitions and executors:
        logging.info(f"=== TOOLS === Loaded {len(definitions)} tools for '{agent_type}' using CONSOLIDATED approach")
        return LoadedTools(definitions=definitions, executors=executors)
    else:
        logging.warning(f"=== TOOLS === No tools found in consolidated mapping for '{agent_type}'")
        return LoadedTools(definitions=[], executors={})
