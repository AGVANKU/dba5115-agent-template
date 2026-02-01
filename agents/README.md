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

### 1. Create system prompt
```
agents/instructions/my_agent.system.md
```
Write the agent's personality, rules, and expected JSON output format.

### 2. Register prompt
In `agents/instructions/prompts_registry.py`:
```python
PROMPTS = {
    ...
    "my_agent": "agents/instructions/my_agent.system.md",
}
```

### 3. Define tools (if needed)
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

### 4. Implement executor (if needed)
In `agents/tools/executors.py`:
```python
def my_tool(param1, **_):
    # Your logic here
    return {"status": "success", "result": "..."}
```

### 5. Map tools to agent
In `agents/tools/registry.py`:
```python
AGENT_TOOL_MAPPING = {
    ...
    "my_agent": ["my_tool"],
}
```

### 6. Route to your agent
Update `email_triage.system.md` to include your agent type in classification, or have another agent's `next_action` route to `my_agent`.

## Agent Lifecycle

1. Orchestrator calls `run_agent_workflow` activity
2. Activity loads agent via `get_agent()` (creates/updates in Azure AI)
3. Creates thread, sends payload as user message
4. Polls for response, executes tool calls if needed
5. Parses response, extracts `next_action` for routing
6. Orchestrator tracks tokens, queues next agent if needed
