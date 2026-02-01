# Queues Layer

Service Bus consumers that bridge hooks to agent orchestrations.

## Consumers

| Consumer | Queue | Purpose |
|----------|-------|---------|
| `gmail_queue_consumer` | `hook-gmail` | Fetches unread emails, starts orchestrations |
| `agent_workflow_queue_consumer` | `agent-workflow` | Routes agent-to-agent workflows |

## Flow

```
hook-gmail queue
    -> gmail_queue_consumer
    -> Fetches unread emails via Gmail API
    -> Pre-fetches email content (subject, body, attachments)
    -> Marks emails as read
    -> Starts orchestrate_agent_workflow for each email

agent-workflow queue
    -> agent_workflow_queue_consumer
    -> Starts orchestrate_agent_workflow with dedup
```

## Deduplication

Each orchestration gets a unique instance ID (e.g., `gmail-{msg_id}`, `agent-{type}-{msg_id}-{ts}`). If an orchestration with the same ID is already running, the new one is skipped.

## Required Queues

Queues are auto-created on startup: `hook-gmail`, `agent-workflow`.
