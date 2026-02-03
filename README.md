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

### Step 1: Create the agent definition
Register the agent via the API (or let seeding handle it):
```bash
curl -X PUT http://localhost:7071/api/config/agents/my_agent \
  -H "Content-Type: application/json" \
  -d '{"description": "My custom agent", "model": "gpt-4o-mini"}'
```
This creates a row in the `AgentDefinition` table, which is the single source of truth for agent name, description, and model.

### Step 2: Write instructions
Create `agents/instructions/my_agent.system.md` with the agent's system prompt.

### Step 3: Register the prompt
Add a filesystem fallback entry to `agents/instructions/prompts_registry.py`:
```python
PROMPTS = {
    ...
    "my_agent": "agents/instructions/my_agent.system.md",
}
```
Then upload the prompt via the API (links it to the agent definition):
```bash
curl -X PUT http://localhost:7071/api/config/prompts/my_agent \
  -H "Content-Type: application/json" \
  -d '{"content": "You are my agent...", "description": "System prompt for my_agent"}'
```

### Step 4: Define tools (optional)
If your agent needs tools:
- Create JSON schema files in `agents/tools/definitions/` (one per tool)
- Add executor functions in `agents/tools/executors.py`

### Step 5: Map tools to agent
Add the static fallback mapping in `agents/tools/registry.py`:
```python
AGENT_TOOL_MAPPING = {
    ...
    "my_agent": ["my_tool_1", "my_tool_2"],
}
```
Or manage tool mappings via the API:
```bash
curl -X PUT http://localhost:7071/api/config/tools/my_agent/my_tool_1 \
  -H "Content-Type: application/json" \
  -d '{"definition": {...}, "executor_name": "my_tool_1"}'
```

### Step 6: Route to your agent
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

## Agent Configuration API

Agent definitions, prompts, and tool mappings are managed via REST endpoints under `/api/config/`:

| Endpoint | Methods | Description |
|----------|---------|-------------|
| `/api/config/agents` | GET | List all agent definitions |
| `/api/config/agents/{name}` | GET, PUT, DELETE | CRUD for a single agent (includes prompt + tools summary on GET) |
| `/api/config/prompts` | GET | List all prompt registrations |
| `/api/config/prompts/{agent_type}` | GET, PUT, DELETE | CRUD for an agent's prompt |
| `/api/config/tools` | GET | List all tool mappings |
| `/api/config/tools/{agent_type}` | GET | Get tool definitions for an agent |
| `/api/config/tools/{agent_type}/{tool_name}` | PUT, DELETE | CRUD for a single tool mapping |
| `/api/config/seed` | POST | Seed default agents, prompts, and tool mappings |

The `AgentDefinition` table is the single source of truth for each agent's name, description, and model. The `AgentPromptRegistry` and `AgentToolMapping` tables reference it via foreign key (`AgentId`).

## Environment Variables

See `local.settings.json.example` and `.env.example` for all required variables.

| Variable | Purpose |
|----------|---------|
| `DEFAULT_AGENT_MODEL` | Fallback LLM model name for agents (default: `gpt-4o-mini`) |
| `SERVICE_BUS_CONNECTION_STRING` | Azure Service Bus for async messaging |
| `AZURE_TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET` | Azure AI agent runtime auth |
| `AZURE_AI_ENDPOINT` | Azure AI Foundry endpoint |
| `DB_SERVER` / `DB_DATABASE` / `DB_USERNAME` / `DB_PASSWORD` | SQL Server for token tracking |
| `GMAIL_CLIENT_ID` / `CLIENT_SECRET` / `REFRESH_TOKEN` | Gmail API OAuth |
| `GMAIL_FROM_NAME` | Display name for outgoing emails (e.g., "DBA5115 Course Admin") |
| `GMAIL_FROM_EMAIL` | Gmail sending address (must match authenticated account) |
| `NUS_EMAIL` | Admin email address (inbox to monitor + notification recipient) |

## Token Tracking

Every agent invocation records token usage (input/output tokens, model, duration) to the `LLMTokenUsage` SQL table for cost analytics.
