# Tools

Agent capabilities defined as JSON schemas with Python executors.

## Structure

```
tools/
  definitions/              # JSON schema files (one per tool)
    determine_recipient.json
    send_email_notification.json
  executors.py              # Python functions that execute tool calls
  registry.py               # Maps agents to their allowed tools
```

## How It Works

1. **Definitions** (`definitions/*.json`): JSON schemas that tell the AI agent what parameters each tool accepts
2. **Executors** (`executors.py`): Python functions that run when the agent calls a tool
3. **Registry** (`registry.py`): Maps each agent to its allowed tools

The registry loads all JSON definitions at import time. When an agent is created, only its mapped tools are provided.

## Adding a New Tool

### 1. Create the definition
`definitions/my_tool.json`:
```json
{
  "name": "my_tool",
  "description": "Brief description for the AI agent",
  "parameters": {
    "type": "object",
    "properties": {
      "input_text": {
        "type": "string",
        "description": "The text to process"
      }
    },
    "required": ["input_text"]
  }
}
```

### 2. Implement the executor
In `executors.py`, add a function with the **same name** as the tool:
```python
def my_tool(input_text, **_):
    # Your logic
    return {"status": "success", "result": "processed"}
```

The `**_` captures any extra parameters the agent might pass.

### 3. Map to an agent
In `registry.py`, add the tool name to the agent's list:
```python
AGENT_TOOL_MAPPING = {
    "my_agent": ["my_tool"],
}
```

## Current Tools

| Tool | Used By | Description |
|------|---------|-------------|
| `determine_recipient` | notification_content | Routes notification to admin |
| `send_email_notification` | notification_content | Renders HTML + sends email via Gmail |
