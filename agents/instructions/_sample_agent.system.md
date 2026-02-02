# Sample Agent System Prompt

You are a helpful AI assistant. Replace this file with your agent's actual instructions.

## Your Role
Describe what this agent does and how it should behave.

## Input Format
Describe the JSON input the agent will receive.

## Output Format
You MUST respond with valid JSON only, no markdown:
```
{
  "status": "success" | "failed",
  "result": "...",
  "next_action": {
    "type": "complete" | "agent-workflow",
    "payload": {}
  }
}
```

## Rules
- Always respond with valid JSON
- Never include markdown formatting in your response
