# Runtime

The agent execution engine using Azure Durable Functions.

## Files

| File | Purpose |
|------|---------|
| `orchestrator_agent_workflow.py` | Durable orchestrator: run agent -> track tokens -> route |
| `activity_agent_workflow.py` | Activity: load agent, create thread, execute, parse response |
| `util_agents.py` | Azure AI agent management: create/update/find agents, tool loading |
| `util_classes.py` | Dataclasses: ManagedAgent, LoadedTools, AgentResponse, etc. |

## Orchestrator Lifecycle

```
1. orchestrate_agent_workflow (orchestrator)
   |
   2. call_activity("run_agent_workflow")
   |   -> get_agent(agent_type)          # Create/update Azure AI agent
   |   -> create_thread()                # New conversation thread
   |   -> create_message(payload)        # Send input as user message
   |   -> get_agent_response()           # Poll until complete, execute tools
   |   -> _determine_next_action()       # Extract routing from response
   |
   3. track_token_usage()                # Save to SQL
   |
   4. If next_action exists:
      call_activity("queue_message")     # Publish to Service Bus
```

## Tool Execution Loop

Inside `get_agent_response()`:
1. Create a run on the thread
2. Poll for status changes
3. If `requires_action`: execute tool calls via local Python executors
4. Submit tool outputs back to the agent
5. Repeat until `completed` or `failed`
6. Fetch final agent message from thread

Max 20 tool call rounds to prevent infinite loops.

## Key Classes (util_classes.py)

- **ManagedAgent**: Agent client + agent object + local tool executors
- **LoadedTools**: Tool definitions + executors (combinable with `+`)
- **AgentResponse**: Status, responses, usage, next_action routing
- **NextAction**: Target queue + payload for orchestrator routing
