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
curl -X POST http://localhost:7071/api/config/agents \
  -H "Content-Type: application/json" \
  -d '{"name": "my_agent", "description": "My custom agent", "model": "gpt-4o-mini"}'
# Returns: {"status": "created", "id": 3, ...}
```
This is the single source of truth for the agent's name, description, and model. The model can be changed at any time via `PUT /api/config/agents/3`.

### 2. Create system prompt
Create a `.system.md` file for your agent's system prompt. Use the sample template:
```bash
cp agents/instructions/_sample_agent.system.md agents/instructions/my_agent.system.md
# Edit my_agent.system.md with your agent's instructions
```
Write the agent's personality, rules, and expected JSON output format.

### 3. Register prompt
Upload the prompt file via API using the `agent_id` returned in step 1 (the agent must exist first):
```bash
curl -X POST http://localhost:7071/api/config/prompts \
  -F agent_id=3 \
  -F description="System prompt for my_agent" \
  -F file=@agents/instructions/my_agent.system.md
```
Alternatively, post the content directly as JSON:
```bash
curl -X POST http://localhost:7071/api/config/prompts \
  -H "Content-Type: application/json" \
  -d '{"agent_id": 3, "content": "...", "description": "System prompt for my_agent"}'
```

### 4. Define tools (if needed)
Create a `.json` file for each tool definition. Use the sample template:
```bash
cp agents/tools/definitions/_sample_tool.json agents/tools/definitions/my_tool.json
# Edit my_tool.json with your tool's schema
```

### 5. Implement executor (if needed)
In `agents/tools/executors.py`:
```python
def my_tool(param1, **_):
    # Your logic here
    return {"status": "success", "result": "..."}
```

### 6. Map tools to agent
Upload the tool definition file via API using the `agent_id` from step 1 (the agent must exist first):
```bash
curl -X POST http://localhost:7071/api/config/tools \
  -F agent_id=3 \
  -F tool_name=my_tool \
  -F executor_name=my_tool \
  -F file=@agents/tools/definitions/my_tool.json
```
Alternatively, post the definition directly as JSON:
```bash
curl -X POST http://localhost:7071/api/config/tools \
  -H "Content-Type: application/json" \
  -d '{"agent_id": 3, "tool_name": "my_tool", "definition": {...}, "executor_name": "my_tool"}'
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
