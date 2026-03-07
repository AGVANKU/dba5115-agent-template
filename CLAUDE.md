# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Azure Functions (Python v2) multi-agent platform that processes Gmail inbox emails through AI agents. Uses Azure Durable Functions for orchestration, Azure AI Agents SDK for LLM interaction, and Azure Service Bus for async messaging.

## Development Commands

```bash
# Local setup
cp local.settings.json.example local.settings.json
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run locally (requires Azure Functions Core Tools)
func start

# Run with Docker (includes Azurite for local storage emulation)
docker-compose up --build

# Trigger a Gmail inbox check manually
curl -X POST http://localhost:7071/api/hooks/gmail_pull

# Seed default agent config into DB + Blob
curl -X POST http://localhost:7071/api/config/seed

# Health check
curl http://localhost:7071/api/health
```

## Architecture

The app has three layers connected via Azure Service Bus queues:

1. **Hooks** (`hooks/hooks.py`) — Timer (2min) + HTTP endpoint publish `check_inbox` messages to `hook-gmail` queue
2. **Queues** (`queues/queues.py`) — Service Bus consumers fetch emails and start Durable Functions orchestrations. Two queues: `hook-gmail` (email ingestion) and `agent-workflow` (agent-to-agent routing)
3. **Agent Runtime** (`agents/runtime/`) — Generic orchestrator + activity that can run any agent type identically

### Request Flow

```
Hook → Service Bus (hook-gmail) → gmail_queue_consumer → Durable orchestration
  → run_agent_workflow activity → Azure AI Agent → parse response
  → if next_action: Service Bus (agent-workflow) → new orchestration
```

### Blueprint Registration

`function_app.py` creates a `DFApp` and registers three blueprints: `hooks_bp`, `queues_bp`, `config_bp`. The queues blueprint (`queues/queues.py`) creates the `df.Blueprint()` that the orchestrator and activity modules import and register decorators on.

**Import order matters**: `queues.py` defines `bp`, then at the bottom imports `orchestrator_agent_workflow` and `activity_agent_workflow` which register their decorators on that same `bp`.

## Agent Configuration (DB-driven)

Agent config is stored across three SQL tables (with Azure Blob Storage for content):

- **AgentDefinition** — name, description, model, knowledge_source (single source of truth)
- **AgentPromptRegistry** — links agent_id to a blob path containing the `.system.md` prompt
- **AgentToolMapping** — links agent_id to tool definitions (blob) and executor function names

CRUD API under `/api/config/` manages these. On startup, `seed_defaults()` auto-creates tables and seeds from filesystem files if tables are empty.

## Adding a New Agent

1. Create agent definition via API (`POST /api/config/agents`)
2. Write instructions in `agents/instructions/<name>.system.md`
3. Register prompt via API (`POST /api/config/prompts`)
4. (Optional) Add tool JSON schema in `agents/tools/definitions/<tool>.json`
5. Add executor function in `agents/tools/executors.py` — function name must match `tool_name`/`executor_name`
6. Map tool to agent via API (`POST /api/config/tools`)
7. Update routing: triage agent's instructions or `registry.py:AGENT_TOOL_MAPPING`

**Critical naming convention**: The `name` in the tool JSON, the `tool_name` in the API/DB, and the Python function name in `executors.py` must all match.

## Tool Resolution

Tools resolve with DB-first, static-fallback pattern (see `agents/tools/registry.py`):
- `get_tool_definitions()` and `get_tool_executors()` try DB/Blob lookup first
- Fall back to `AGENT_TOOL_MAPPING` dict and `ALL_TOOL_DEFINITIONS` (loaded from `definitions/*.json` at import time)
- `ALL_TOOL_EXECUTORS` is auto-built from all non-underscore functions in `executors.py`

## Key Patterns

- **Agent responses must be JSON** with optional `next_action.target_queue` and `next_action.payload` for routing to the next agent
- **Prompt loading** (`agents/instructions/prompts_registry.py`): DB/Blob first, filesystem `.system.md` fallback
- **Token tracking**: Every agent invocation logs usage to `LLMTokenUsage` SQL table
- **Retry with backoff**: Azure AI SDK calls use `_retry_with_backoff()` in `util_agents.py` (3 attempts, exponential)
- **Database**: SQL Server via SQLAlchemy + pyodbc. Models use raw `__create_sql__` for table creation (not `Base.metadata.create_all`)

## External Dependencies

- **Azure AI Agents SDK** (`azure-ai-agents`) — LLM agent runtime
- **Azure Service Bus** — async queue messaging
- **Azure Blob Storage** — prompt/tool definition storage
- **Azure SQL Server** — agent config, token tracking
- **Gmail API** — email ingestion and sending (OAuth2 with refresh token)
- **Azurite** — local Azure Storage emulator (used in Docker)
