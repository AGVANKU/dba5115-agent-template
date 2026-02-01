"""
DBA5115 Multi-Agent Platform

Main Function App entry point that registers all blueprints:

1. HOOKS - Ingest layer for external events (Gmail)
   Routes: /api/hooks/*
   Publishes events to Service Bus for async processing

2. AGENTS - AI agent orchestration layer
   Consumes Service Bus, manages agents, orchestrates workflows
"""

import json
import logging
import azure.functions as func
import azure.durable_functions as df

# Import blueprints from each layer
from hooks.hooks import bp as hooks_bp
from queues.queues import bp as queues_bp

# Initialize database tables on startup
try:
    from shared.util_token_tracking import ensure_token_usage_table
    ensure_token_usage_table()
except Exception as e:
    logging.warning(f"Could not initialize token usage table: {e}")

# Create main app with Durable Functions support
app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

# Register all blueprints (order: hooks -> agents)
app.register_functions(hooks_bp)
app.register_functions(queues_bp)


# =============================================================================
# HEALTH CHECK (root level)
# =============================================================================

@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Root health check endpoint."""
    return func.HttpResponse(
        json.dumps({
            "status": "healthy",
            "app": "dba5115-agent-template",
            "layers": ["hooks", "agents"]
        }),
        mimetype="application/json"
    )
