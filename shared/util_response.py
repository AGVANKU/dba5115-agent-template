"""
Shared HTTP response utilities.
"""

import json
import azure.functions as func


def json_response(data: dict, status_code: int = 200) -> func.HttpResponse:
    """Helper for JSON responses."""
    return func.HttpResponse(
        json.dumps(data),
        status_code=status_code,
        mimetype="application/json"
    )
