# Agents Layer

AI agent orchestration - the core of the platform.

## Structure

```
agents/
  runtime/          # Orchestrator + activity (execution engine)
  instructions/     # System prompts for each agent
  tools/            # Tool definitions + executors + registry
  utility/          # Database, ORM models, notifications
  templates/        # Email HTML templates
```

## Included Agents

| Agent | Has Tools | Description |
|-------|-----------|-------------|
| `email_triage` | No | Classifies emails into actionable/informational/out_of_scope |
| `notification_content` | Yes | Sends triage results to admin via email |

## Adding a New Agent (Step by Step)

### 1. Create the agent definition
Register the agent in the `AgentDefinition` table via the API:
```bash
curl -X PUT http://localhost:7071/api/config/agents/my_agent \
  -H "Content-Type: application/json" \
  -d '{"description": "My custom agent", "model": "gpt-4o-mini"}'
```
This is the single source of truth for the agent's name, description, and model. The model can be changed at any time without redeploying code.

### 2. Create system prompt
```
agents/instructions/my_agent.system.md
```
Write the agent's personality, rules, and expected JSON output format.

### 3. Register prompt
Add a filesystem fallback entry in `agents/instructions/prompts_registry.py`:
```python
PROMPTS = {
    ...
    "my_agent": "agents/instructions/my_agent.system.md",
}
```
Then upload the prompt via API to link it to the agent definition:
```bash
curl -X PUT http://localhost:7071/api/config/prompts/my_agent \
  -H "Content-Type: application/json" \
  -d '{"content": "...", "description": "System prompt for my_agent"}'
```

### 4. Define tools (if needed)
Create `agents/tools/definitions/my_tool.json`:
```json
{
  "name": "my_tool",
  "description": "What this tool does",
  "parameters": {
    "type": "object",
    "properties": {
      "param1": { "type": "string", "description": "..." }
    },
    "required": ["param1"]
  }
}
```

### 5. Implement executor (if needed)
In `agents/tools/executors.py`:
```python
def my_tool(param1, **_):
    # Your logic here
    return {"status": "success", "result": "..."}
```

### 6. Map tools to agent
Add a static fallback in `agents/tools/registry.py`:
```python
AGENT_TOOL_MAPPING = {
    ...
    "my_agent": ["my_tool"],
}
```
Or manage via API:
```bash
curl -X PUT http://localhost:7071/api/config/tools/my_agent/my_tool \
  -H "Content-Type: application/json" \
  -d '{"definition": {...}, "executor_name": "my_tool"}'
```

### 7. Route to your agent
Update `email_triage.system.md` to include your agent type in classification, or have another agent's `next_action` route to `my_agent`.

## Agent Lifecycle

1. Orchestrator calls `run_agent_workflow` activity
2. Activity loads agent via `get_agent()` (creates/updates in Azure AI)
3. Creates thread, sends payload as user message
4. Polls for response, executes tool calls if needed
5. Parses response, extracts `next_action` for routing
6. Orchestrator tracks tokens, queues next agent if needed
