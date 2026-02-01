# DBA5115 Agent Template

A starter Azure Functions app with a multi-agent architecture for processing Gmail inbox emails through AI agents.

## Architecture

```
Gmail Inbox
    |
    v
[Hooks Layer]          Timer (every 2 min) + HTTP endpoint
    |                  Publishes "check_inbox" to Service Bus
    v
[Queues Layer]         gmail_queue_consumer: fetches emails, starts orchestrations
    |                  agent_workflow_queue_consumer: routes agent-to-agent workflows
    v
[Agent Runtime]        Durable Functions orchestrator + activity
    |                  Creates Azure AI agent, sends email content, collects response
    v
[Agents]
    email_triage       Classifies emails: actionable / informational / out_of_scope
    |                  Routes actionable + informational -> notification_content
    v
    notification_content   Determines recipient -> sends email notification to admin
```

## Included Agents

| Agent | Tools | Purpose |
|-------|-------|---------|
| `email_triage` | None | Classifies incoming emails into 3 categories |
| `notification_content` | `determine_recipient`, `send_email_notification` | Sends triage results to admin via email |

## Quick Start

1. **Clone and configure**
   ```bash
   git clone https://github.com/AGVANKU/dba5115-agent-template.git
   cd dba5115-agent-template
   cp local.settings.json.example local.settings.json
   cp .env.example .env
   # Fill in your credentials in both files
   ```

2. **Run with Docker**
   ```bash
   docker-compose up --build
   ```

3. **Or run locally**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   func start
   ```

4. **Trigger a Gmail check**
   ```bash
   curl -X POST http://localhost:7071/api/hooks/gmail_pull
   ```

## How to Add a New Agent

### Step 1: Write instructions
Create `agents/instructions/my_agent.system.md` with the agent's system prompt.

### Step 2: Register the prompt
Add an entry to `agents/instructions/prompts_registry.py`:
```python
PROMPTS = {
    ...
    "my_agent": "agents/instructions/my_agent.system.md",
}
```

### Step 3: Define tools (optional)
If your agent needs tools:
- Create JSON schema files in `agents/tools/definitions/` (one per tool)
- Add executor functions in `agents/tools/executors.py`

### Step 4: Map tools to agent
Add the mapping in `agents/tools/registry.py`:
```python
AGENT_TOOL_MAPPING = {
    ...
    "my_agent": ["my_tool_1", "my_tool_2"],
}
```

### Step 5: Route to your agent
Update the triage agent's instructions or the notification agent to route to your new agent via `next_action.payload.agent_type`.

## Project Structure

```
function_app.py              # Azure Functions entry point
hooks/                       # Gmail pull triggers (timer + HTTP)
queues/                      # Service Bus consumers + orchestration imports
agents/
  runtime/                   # Orchestrator, activity, agent utilities
  instructions/              # System prompts (.system.md) + registry
  tools/                     # Tool definitions (.json), executors, registry
  utility/                   # Database ORM, notifications, data models
  templates/                 # Jinja2 email templates
shared/                      # Gmail API, Service Bus, token tracking
```

## Environment Variables

See `local.settings.json.example` and `.env.example` for all required variables.

| Variable | Purpose |
|----------|---------|
| `SERVICE_BUS_CONNECTION_STRING` | Azure Service Bus for async messaging |
| `AZURE_TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET` | Azure AI agent runtime auth |
| `AZURE_AI_ENDPOINT` | Azure AI Foundry endpoint |
| `DB_SERVER` / `DB_DATABASE` / `DB_USERNAME` / `DB_PASSWORD` | SQL Server for token tracking |
| `GMAIL_CLIENT_ID` / `CLIENT_SECRET` / `REFRESH_TOKEN` | Gmail API OAuth |
| `NUS_EMAIL` | Admin email address (inbox to monitor + notification recipient) |

## Token Tracking

Every agent invocation records token usage (input/output tokens, model, duration) to the `LLMTokenUsage` SQL table for cost analytics.
