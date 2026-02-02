"""
CRUD API for agent configuration (prompts + tool mappings).

Blueprint registered in function_app.py.
Routes: /api/config/prompts, /api/config/tools, /api/config/seed
"""

import json
import logging

import azure.functions as func

bp = func.Blueprint()


# =============================================================================
# PROMPTS
# =============================================================================

@bp.route(route="config/prompts", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def list_prompts(req: func.HttpRequest) -> func.HttpResponse:
    from agents.utility.util_database import get_session, ensure_table
    from agents.utility.util_datamodel import AgentPromptRegistry

    try:
        ensure_table(AgentPromptRegistry)
        with get_session() as session:
            rows = session.query(AgentPromptRegistry).all()
            data = [
                {
                    "agent_type": r.agent_type,
                    "blob_path": r.blob_path,
                    "description": r.description,
                    "is_active": r.is_active,
                }
                for r in rows
            ]
        return func.HttpResponse(json.dumps(data), mimetype="application/json")
    except Exception as e:
        logging.exception("list_prompts error")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@bp.route(route="config/prompts/{agent_type}", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def get_prompt_config(req: func.HttpRequest) -> func.HttpResponse:
    agent_type = req.route_params.get("agent_type")
    from agents.utility.util_database import get_session, ensure_table
    from agents.utility.util_datamodel import AgentPromptRegistry
    from agents.utility.util_blob import get_blob_text

    try:
        ensure_table(AgentPromptRegistry)
        with get_session() as session:
            row = (
                session.query(AgentPromptRegistry)
                .filter(AgentPromptRegistry.agent_type == agent_type, AgentPromptRegistry.is_active == True)
                .first()
            )
            if not row:
                return func.HttpResponse(json.dumps({"error": "not found"}), status_code=404, mimetype="application/json")
            content = get_blob_text(row.blob_path)
            return func.HttpResponse(
                json.dumps({"agent_type": row.agent_type, "blob_path": row.blob_path, "content": content}),
                mimetype="application/json",
            )
    except Exception as e:
        logging.exception("get_prompt_config error")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@bp.route(route="config/prompts/{agent_type}", methods=["PUT"], auth_level=func.AuthLevel.FUNCTION)
def put_prompt_config(req: func.HttpRequest) -> func.HttpResponse:
    agent_type = req.route_params.get("agent_type")
    from agents.utility.util_database import get_session, ensure_table
    from agents.utility.util_datamodel import AgentPromptRegistry
    from agents.utility.util_blob import upload_blob

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(json.dumps({"error": "invalid JSON"}), status_code=400, mimetype="application/json")

    content = body.get("content", "")
    description = body.get("description")
    blob_path = f"prompts/{agent_type}.system.md"

    try:
        ensure_table(AgentPromptRegistry)
        upload_blob(blob_path, content)

        with get_session() as session:
            row = session.query(AgentPromptRegistry).filter(AgentPromptRegistry.agent_type == agent_type).first()
            if row:
                row.blob_path = blob_path
                if description is not None:
                    row.description = description
                row.is_active = True
            else:
                row = AgentPromptRegistry(
                    agent_type=agent_type,
                    blob_path=blob_path,
                    description=description or f"System prompt for {agent_type}",
                    is_active=True,
                )
                session.add(row)

        return func.HttpResponse(
            json.dumps({"status": "ok", "agent_type": agent_type, "blob_path": blob_path}),
            mimetype="application/json",
        )
    except Exception as e:
        logging.exception("put_prompt_config error")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@bp.route(route="config/prompts/{agent_type}", methods=["DELETE"], auth_level=func.AuthLevel.FUNCTION)
def delete_prompt_config(req: func.HttpRequest) -> func.HttpResponse:
    agent_type = req.route_params.get("agent_type")
    from agents.utility.util_database import get_session, ensure_table
    from agents.utility.util_datamodel import AgentPromptRegistry
    from agents.utility.util_blob import delete_blob

    try:
        ensure_table(AgentPromptRegistry)
        with get_session() as session:
            row = session.query(AgentPromptRegistry).filter(AgentPromptRegistry.agent_type == agent_type).first()
            if not row:
                return func.HttpResponse(json.dumps({"error": "not found"}), status_code=404, mimetype="application/json")
            try:
                delete_blob(row.blob_path)
            except Exception:
                logging.warning(f"Blob {row.blob_path} not found during delete")
            session.delete(row)
        return func.HttpResponse(json.dumps({"status": "deleted"}), mimetype="application/json")
    except Exception as e:
        logging.exception("delete_prompt_config error")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


# =============================================================================
# TOOL MAPPINGS
# =============================================================================

@bp.route(route="config/tools", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def list_tool_mappings(req: func.HttpRequest) -> func.HttpResponse:
    from agents.utility.util_database import get_session, ensure_table
    from agents.utility.util_datamodel import AgentToolMapping

    try:
        ensure_table(AgentToolMapping)
        with get_session() as session:
            rows = session.query(AgentToolMapping).all()
            data = [
                {
                    "agent_type": r.agent_type,
                    "tool_name": r.tool_name,
                    "blob_path": r.blob_path,
                    "executor_name": r.executor_name,
                    "is_active": r.is_active,
                }
                for r in rows
            ]
        return func.HttpResponse(json.dumps(data), mimetype="application/json")
    except Exception as e:
        logging.exception("list_tool_mappings error")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@bp.route(route="config/tools/{agent_type}", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def get_agent_tools(req: func.HttpRequest) -> func.HttpResponse:
    agent_type = req.route_params.get("agent_type")
    from agents.utility.util_database import get_session, ensure_table
    from agents.utility.util_datamodel import AgentToolMapping
    from agents.utility.util_blob import get_blob_text

    try:
        ensure_table(AgentToolMapping)
        with get_session() as session:
            rows = (
                session.query(AgentToolMapping)
                .filter(AgentToolMapping.agent_type == agent_type, AgentToolMapping.is_active == True)
                .all()
            )
            tools = []
            for r in rows:
                try:
                    definition = json.loads(get_blob_text(r.blob_path))
                except Exception:
                    definition = None
                tools.append({"name": r.tool_name, "definition": definition})
        return func.HttpResponse(
            json.dumps({"agent_type": agent_type, "tools": tools}),
            mimetype="application/json",
        )
    except Exception as e:
        logging.exception("get_agent_tools error")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@bp.route(route="config/tools/{agent_type}/{tool_name}", methods=["PUT"], auth_level=func.AuthLevel.FUNCTION)
def put_tool_mapping(req: func.HttpRequest) -> func.HttpResponse:
    agent_type = req.route_params.get("agent_type")
    tool_name = req.route_params.get("tool_name")
    from agents.utility.util_database import get_session, ensure_table
    from agents.utility.util_datamodel import AgentToolMapping
    from agents.utility.util_blob import upload_blob

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(json.dumps({"error": "invalid JSON"}), status_code=400, mimetype="application/json")

    definition = body.get("definition", {})
    executor_name = body.get("executor_name", tool_name)
    blob_path = f"tools/{tool_name}.json"

    try:
        ensure_table(AgentToolMapping)
        upload_blob(blob_path, json.dumps(definition, indent=2))

        with get_session() as session:
            row = (
                session.query(AgentToolMapping)
                .filter(AgentToolMapping.agent_type == agent_type, AgentToolMapping.tool_name == tool_name)
                .first()
            )
            if row:
                row.blob_path = blob_path
                row.executor_name = executor_name
                row.is_active = True
            else:
                row = AgentToolMapping(
                    agent_type=agent_type,
                    tool_name=tool_name,
                    blob_path=blob_path,
                    executor_name=executor_name,
                    is_active=True,
                )
                session.add(row)

        return func.HttpResponse(json.dumps({"status": "ok"}), mimetype="application/json")
    except Exception as e:
        logging.exception("put_tool_mapping error")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


@bp.route(route="config/tools/{agent_type}/{tool_name}", methods=["DELETE"], auth_level=func.AuthLevel.FUNCTION)
def delete_tool_mapping(req: func.HttpRequest) -> func.HttpResponse:
    agent_type = req.route_params.get("agent_type")
    tool_name = req.route_params.get("tool_name")
    from agents.utility.util_database import get_session, ensure_table
    from agents.utility.util_datamodel import AgentToolMapping
    from agents.utility.util_blob import delete_blob

    try:
        ensure_table(AgentToolMapping)
        with get_session() as session:
            row = (
                session.query(AgentToolMapping)
                .filter(AgentToolMapping.agent_type == agent_type, AgentToolMapping.tool_name == tool_name)
                .first()
            )
            if not row:
                return func.HttpResponse(json.dumps({"error": "not found"}), status_code=404, mimetype="application/json")
            try:
                delete_blob(row.blob_path)
            except Exception:
                logging.warning(f"Blob {row.blob_path} not found during delete")
            session.delete(row)
        return func.HttpResponse(json.dumps({"status": "deleted"}), mimetype="application/json")
    except Exception as e:
        logging.exception("delete_tool_mapping error")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")


# =============================================================================
# SEED
# =============================================================================

@bp.route(route="config/seed", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def seed_config(req: func.HttpRequest) -> func.HttpResponse:
    from agents.utility.util_seed import seed_defaults

    try:
        result = seed_defaults()
        return func.HttpResponse(json.dumps(result), mimetype="application/json")
    except Exception as e:
        logging.exception("seed_config error")
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
