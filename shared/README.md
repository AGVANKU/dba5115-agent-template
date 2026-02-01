# Shared Utilities

Cross-cutting utilities used by hooks, queues, and agents.

## Files

| File | Purpose |
|------|---------|
| `util_gmail.py` | Gmail API client, email fetching/sending/parsing |
| `util_service_bus.py` | Service Bus queue management and message publishing |
| `util_response.py` | HTTP response helper for Azure Functions |
| `util_resources.py` | Azure credential helper (ClientSecretCredential) |
| `util_token_tracking.py` | LLM token usage tracking to SQL Server |
| `__init__.py` | Re-exports commonly used functions |

## Gmail API (`util_gmail.py`)

- **`get_gmail_service()`**: Cached, thread-safe Gmail API client
- **`get_unread_message_ids()`**: Fetch unread message IDs with time filtering
- **`fetch_message_raw()`**: Fetch raw RFC822 message
- **`parse_email_message()`**: Parse into structured format (subject, body, attachments)
- **`mark_as_read()`**: Remove UNREAD label
- **`send_email()`**: Send email via Gmail API (supports HTML, attachments, CC)

All Gmail API calls have retry logic with exponential backoff.

## Service Bus (`util_service_bus.py`)

- **`ensure_queue_exists()`**: Create queue if it doesn't exist (cached)
- **`publish_to_service_bus()`**: Publish message with retry logic

## Token Tracking (`util_token_tracking.py`)

- **`ensure_token_usage_table()`**: Create table on startup
- **`track_token_usage()`**: Fail-safe recording of token usage per agent invocation

Falls back to local JSONL file logging if database is unavailable.
