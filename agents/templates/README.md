# Email Templates

Jinja2 HTML templates for notification emails.

## Structure

```
templates/
  email_notification.html     # Master template (header, footer, layout)
  sections/                   # Reusable content blocks
    executive_summary.html
    status_box.html
    resource_list.html
    next_steps.html
    alert.html
    code_block.html
```

## How It Works

The `send_email_notification` tool executor:
1. Receives an array of `sections` from the AI agent
2. Renders each section using its corresponding template
3. Injects rendered sections into the master `email_notification.html`
4. Sends the final HTML via Gmail API

## Section Types

| Section | Purpose | Key Fields |
|---------|---------|------------|
| `executive_summary` | Opening paragraph | `content` |
| `status_box` | Status highlight with metrics | `status`, `title`, `metrics`, `message` |
| `resource_list` | List of resources/endpoints | `title`, `items[]` |
| `next_steps` | Ordered action items | `title`, `items[]` |
| `alert` | Important notice | `alert_type`, `title`, `message` |
| `code_block` | Code or configuration | `title`, `code` |

## Adding a New Section Type

1. Create `sections/my_section.html` with Jinja2 template syntax
2. Add the section type name to the list in `agents/tools/executors.py` (the `send_email_notification` function)
3. Document it in the notification agent's system prompt
