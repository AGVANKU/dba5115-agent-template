# Instructions (System Prompts)

Each agent has a `.system.md` file that defines its personality and behavior.

## Files

| File | Agent | Description |
|------|-------|-------------|
| `email_triage.system.md` | email_triage | Classifies emails into 3 categories |
| `notification_content.system.md` | notification_content | Generates and sends email notifications |
| `prompts_registry.py` | - | Maps agent names to prompt file paths |

## Prompt Registry

The registry (`prompts_registry.py`) maps agent type strings to file paths:

```python
PROMPTS = {
    "email_triage": "agents/instructions/email_triage.system.md",
    "notification_content": "agents/instructions/notification_content.system.md",
}
```

When adding a new agent, add its entry here.

## Writing System Prompts

### Required Elements

1. **Output format**: Agents must return valid JSON (no markdown code blocks)
2. **Tool usage instructions**: If the agent has tools, describe the workflow
3. **Response schema**: Define the exact JSON structure expected

### Best Practices

- Be explicit about what the agent should and should not do
- Include examples of expected output
- Define confidence levels if applicable
- Specify how to handle edge cases
