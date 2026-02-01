# Hooks Layer

Entry points for external events into the platform.

## Endpoints

| Trigger | Route | Schedule | Purpose |
|---------|-------|----------|---------|
| Timer | `gmail_timer_pull` | Every 2 minutes | Periodic inbox check |
| HTTP | `POST /api/hooks/gmail_pull` | On-demand | Manual inbox check |

## How It Works

1. Both triggers create a lightweight `{"type": "check_inbox"}` message
2. The message is published to the `hook-gmail` Service Bus queue
3. The queues layer consumes the message and fetches actual emails

The hooks layer does **not** fetch emails directly - it only signals the queues layer.

## Adding a New Hook

1. Add a new function in `hooks.py` with a `@bp.timer_trigger` or `@bp.route` decorator
2. Publish a message to an appropriate Service Bus queue
3. Add a consumer in `queues/queues.py` to process the queue
