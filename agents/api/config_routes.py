"""
CRUD API for agent configuration (agents, prompts, tool mappings).

Blueprint registered in function_app.py.

Design:
- POST for creation (data in body), PUT for updates (id in URL, data in body)
- Prompts and tool mappings reference agent_id — the agent must already exist
- GET/DELETE use resource id in the URL path
"""

import json
import logging

import azure.functions as func

bp = func.Blueprint()


def _ensure_tables():
    from agents.utility.util_database import ensure_table
    from agents.utility.util_datamodel import AgentDefinition, AgentPromptRegistry, AgentToolMapping
    ensure_table(AgentDefinition)
    ensure_table(AgentPromptRegistry)
    ensure_table(AgentToolMapping)


def _get_agent_by_id(session, agent_id: int):
    from agents.utility.util_datamodel import AgentDefinition
    return session.query(AgentDefinition).filter(AgentDefinition.id == agent_id).first()


def _json_response(data, status_code=200):
    return func.HttpResponse(json.dumps(data), status_code=status_code, mimetype="application/json")


def _error(msg, status_code=400):
    return _json_response({"error": msg}, status_code)


def _parse_json_body(req):
    try:
        return req.get_json(), None
    except ValueError:
        return None, _error("Invalid JSON body")


# =============================================================================
# AGENT DEFINITIONS
# =============================================================================

@bp.route(route="config/agents", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def list_agents(req: func.HttpRequest) -> func.HttpResponse:
    """List all agent definitions."""
    from agents.utility.util_database import get_session
    try:
        _ensure_tables()
        with get_session() as session:
            from agents.utility.util_datamodel import AgentDefinition
            rows = session.query(AgentDefinition).all()
            data = [{"id": r.id, "name": r.name, "description": r.description, "model": r.model, "is_active": r.is_active} for r in rows]
        return _json_response(data)
    except Exception as e:
        logging.exception("list_agents error")
        return _error(str(e), 500)


@bp.route(route="config/agents/{id}", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def get_agent(req: func.HttpRequest) -> func.HttpResponse:
    """Get a single agent definition by id, including prompt and tools summary."""
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentPromptRegistry, AgentToolMapping
    try:
        agent_id = int(req.route_params["id"])
    except (ValueError, KeyError):
        return _error("Invalid agent id")

    try:
        _ensure_tables()
        with get_session() as session:
            agent = _get_agent_by_id(session, agent_id)
            if not agent:
                return _error("Agent not found", 404)

            prompt_row = session.query(AgentPromptRegistry).filter(
                AgentPromptRegistry.agent_id == agent.id, AgentPromptRegistry.is_active == True
            ).first()
            tool_rows = session.query(AgentToolMapping).filter(
                AgentToolMapping.agent_id == agent.id, AgentToolMapping.is_active == True
            ).all()

            data = {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "model": agent.model,
                "is_active": agent.is_active,
                "prompt": {"id": prompt_row.id, "blob_path": prompt_row.blob_path, "description": prompt_row.description} if prompt_row else None,
                "tools": [{"id": t.id, "tool_name": t.tool_name, "blob_path": t.blob_path, "executor_name": t.executor_name} for t in tool_rows],
            }
        return _json_response(data)
    except Exception as e:
        logging.exception("get_agent error")
        return _error(str(e), 500)


@bp.route(route="config/agents", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def create_agent(req: func.HttpRequest) -> func.HttpResponse:
    """Create a new agent definition.
    Body: {"name": "...", "description": "...", "model": "gpt-4o-mini"}
    """
    import os
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentDefinition

    body, err = _parse_json_body(req)
    if err:
        return err

    name = body.get("name")
    if not name:
        return _error("'name' is required")

    description = body.get("description", f"Agent: {name}")
    model = body.get("model", os.getenv("DEFAULT_AGENT_MODEL", "gpt-4o-mini"))

    try:
        _ensure_tables()
        with get_session() as session:
            existing = session.query(AgentDefinition).filter(AgentDefinition.name == name).first()
            if existing:
                return _error(f"Agent '{name}' already exists (id={existing.id}). Use PUT to update.", 409)
            agent = AgentDefinition(name=name, description=description, model=model, is_active=True)
            session.add(agent)
            session.flush()
            agent_id = agent.id
        return _json_response({"status": "created", "id": agent_id, "name": name, "model": model}, 201)
    except Exception as e:
        logging.exception("create_agent error")
        return _error(str(e), 500)


@bp.route(route="config/agents/{id}", methods=["PUT"], auth_level=func.AuthLevel.FUNCTION)
def update_agent(req: func.HttpRequest) -> func.HttpResponse:
    """Update an existing agent definition.
    Body: {"description": "...", "model": "gpt-4o"}
    """
    from agents.utility.util_database import get_session
    try:
        agent_id = int(req.route_params["id"])
    except (ValueError, KeyError):
        return _error("Invalid agent id")

    body, err = _parse_json_body(req)
    if err:
        return err

    try:
        _ensure_tables()
        with get_session() as session:
            agent = _get_agent_by_id(session, agent_id)
            if not agent:
                return _error("Agent not found", 404)
            if "name" in body:
                agent.name = body["name"]
            if "description" in body:
                agent.description = body["description"]
            if "model" in body:
                agent.model = body["model"]
            if "is_active" in body:
                agent.is_active = body["is_active"]
        return _json_response({"status": "updated", "id": agent_id})
    except Exception as e:
        logging.exception("update_agent error")
        return _error(str(e), 500)


@bp.route(route="config/agents/{id}", methods=["DELETE"], auth_level=func.AuthLevel.FUNCTION)
def delete_agent(req: func.HttpRequest) -> func.HttpResponse:
    """Delete an agent definition. Rejects if prompt or tool mappings still reference it."""
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentPromptRegistry, AgentToolMapping

    try:
        agent_id = int(req.route_params["id"])
    except (ValueError, KeyError):
        return _error("Invalid agent id")

    try:
        _ensure_tables()
        with get_session() as session:
            agent = _get_agent_by_id(session, agent_id)
            if not agent:
                return _error("Agent not found", 404)
            prompt_count = session.query(AgentPromptRegistry).filter(AgentPromptRegistry.agent_id == agent_id).count()
            tool_count = session.query(AgentToolMapping).filter(AgentToolMapping.agent_id == agent_id).count()
            if prompt_count > 0 or tool_count > 0:
                return _json_response({
                    "error": "Cannot delete agent with existing prompt or tool mappings. Delete those first.",
                    "prompt_count": prompt_count,
                    "tool_count": tool_count,
                }, 409)
            session.delete(agent)
        return _json_response({"status": "deleted"})
    except Exception as e:
        logging.exception("delete_agent error")
        return _error(str(e), 500)


# =============================================================================
# PROMPTS
# =============================================================================

@bp.route(route="config/prompts", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def list_prompts(req: func.HttpRequest) -> func.HttpResponse:
    """List all prompt registrations."""
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentDefinition, AgentPromptRegistry

    try:
        _ensure_tables()
        with get_session() as session:
            rows = (
                session.query(AgentPromptRegistry, AgentDefinition.name)
                .join(AgentDefinition, AgentPromptRegistry.agent_id == AgentDefinition.id)
                .all()
            )
            data = [
                {"id": r.id, "agent_id": r.agent_id, "agent_name": agent_name, "blob_path": r.blob_path, "description": r.description, "is_active": r.is_active}
                for r, agent_name in rows
            ]
        return _json_response(data)
    except Exception as e:
        logging.exception("list_prompts error")
        return _error(str(e), 500)


@bp.route(route="config/prompts/{id}", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def get_prompt(req: func.HttpRequest) -> func.HttpResponse:
    """Get a prompt by id, including blob content."""
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentPromptRegistry
    from agents.utility.util_blob import get_blob_text

    try:
        prompt_id = int(req.route_params["id"])
    except (ValueError, KeyError):
        return _error("Invalid prompt id")

    try:
        _ensure_tables()
        with get_session() as session:
            row = session.query(AgentPromptRegistry).filter(AgentPromptRegistry.id == prompt_id).first()
            if not row:
                return _error("Prompt not found", 404)
            content = get_blob_text(row.blob_path)
            return _json_response({"id": row.id, "agent_id": row.agent_id, "blob_path": row.blob_path, "description": row.description, "content": content})
    except Exception as e:
        logging.exception("get_prompt error")
        return _error(str(e), 500)


@bp.route(route="config/prompts", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def create_prompt(req: func.HttpRequest) -> func.HttpResponse:
    """Create a prompt for an agent. Accepts either:
    - JSON body: {"agent_id": 1, "content": "...", "description": "..."}
    - File upload: multipart/form-data with 'agent_id', 'file', and optional 'description'
    Agent must exist.
    """
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentPromptRegistry
    from agents.utility.util_blob import upload_blob

    content_type = (req.headers.get("Content-Type") or "").lower()

    if "multipart/form-data" in content_type:
        uploaded = req.files.get("file")
        if not uploaded:
            return _error("No 'file' field in multipart upload")
        content = uploaded.stream.read().decode("utf-8")
        description = req.form.get("description")
        try:
            agent_id = int(req.form.get("agent_id", ""))
        except (ValueError, TypeError):
            return _error("'agent_id' is required (integer)")
    else:
        body, err = _parse_json_body(req)
        if err:
            return err
        agent_id = body.get("agent_id")
        if not agent_id or not isinstance(agent_id, int):
            return _error("'agent_id' is required (integer)")
        content = body.get("content", "")
        description = body.get("description")

    try:
        _ensure_tables()
        with get_session() as session:
            agent = _get_agent_by_id(session, agent_id)
            if not agent:
                return _error(f"Agent with id={agent_id} not found. Create the agent first.", 404)

            existing = session.query(AgentPromptRegistry).filter(AgentPromptRegistry.agent_id == agent_id).first()
            if existing:
                return _error(f"Prompt already exists for agent_id={agent_id} (prompt id={existing.id}). Use PUT to update.", 409)

            blob_path = f"prompts/{agent.name}.system.md"
            upload_blob(blob_path, content)
            row = AgentPromptRegistry(
                agent_id=agent_id,
                blob_path=blob_path,
                description=description or f"System prompt for {agent.name}",
                is_active=True,
            )
            session.add(row)
            session.flush()
            prompt_id = row.id

        return _json_response({"status": "created", "id": prompt_id, "agent_id": agent_id, "blob_path": blob_path}, 201)
    except Exception as e:
        logging.exception("create_prompt error")
        return _error(str(e), 500)


@bp.route(route="config/prompts/{id}", methods=["PUT"], auth_level=func.AuthLevel.FUNCTION)
def update_prompt(req: func.HttpRequest) -> func.HttpResponse:
    """Update a prompt by id. Accepts either:
    - JSON body: {"content": "...", "description": "..."}
    - File upload: multipart/form-data with 'file' and optional 'description'
    """
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentPromptRegistry
    from agents.utility.util_blob import upload_blob

    try:
        prompt_id = int(req.route_params["id"])
    except (ValueError, KeyError):
        return _error("Invalid prompt id")

    content_type = (req.headers.get("Content-Type") or "").lower()

    if "multipart/form-data" in content_type:
        uploaded = req.files.get("file")
        if not uploaded:
            return _error("No 'file' field in multipart upload")
        content = uploaded.stream.read().decode("utf-8")
        description = req.form.get("description")
    else:
        body, err = _parse_json_body(req)
        if err:
            return err
        content = body.get("content")
        description = body.get("description")

    try:
        _ensure_tables()
        with get_session() as session:
            row = session.query(AgentPromptRegistry).filter(AgentPromptRegistry.id == prompt_id).first()
            if not row:
                return _error("Prompt not found", 404)
            if content is not None:
                upload_blob(row.blob_path, content)
            if description is not None:
                row.description = description
        return _json_response({"status": "updated", "id": prompt_id})
    except Exception as e:
        logging.exception("update_prompt error")
        return _error(str(e), 500)


@bp.route(route="config/prompts/{id}", methods=["DELETE"], auth_level=func.AuthLevel.FUNCTION)
def delete_prompt(req: func.HttpRequest) -> func.HttpResponse:
    """Delete a prompt by id."""
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentPromptRegistry
    from agents.utility.util_blob import delete_blob

    try:
        prompt_id = int(req.route_params["id"])
    except (ValueError, KeyError):
        return _error("Invalid prompt id")

    try:
        _ensure_tables()
        with get_session() as session:
            row = session.query(AgentPromptRegistry).filter(AgentPromptRegistry.id == prompt_id).first()
            if not row:
                return _error("Prompt not found", 404)
            try:
                delete_blob(row.blob_path)
            except Exception:
                logging.warning(f"Blob {row.blob_path} not found during delete")
            session.delete(row)
        return _json_response({"status": "deleted"})
    except Exception as e:
        logging.exception("delete_prompt error")
        return _error(str(e), 500)


# =============================================================================
# TOOL MAPPINGS
# =============================================================================

@bp.route(route="config/tools", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def list_tools(req: func.HttpRequest) -> func.HttpResponse:
    """List all tool mappings."""
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentDefinition, AgentToolMapping

    try:
        _ensure_tables()
        with get_session() as session:
            rows = (
                session.query(AgentToolMapping, AgentDefinition.name)
                .join(AgentDefinition, AgentToolMapping.agent_id == AgentDefinition.id)
                .all()
            )
            data = [
                {"id": r.id, "agent_id": r.agent_id, "agent_name": agent_name, "tool_name": r.tool_name, "blob_path": r.blob_path, "executor_name": r.executor_name, "is_active": r.is_active}
                for r, agent_name in rows
            ]
        return _json_response(data)
    except Exception as e:
        logging.exception("list_tools error")
        return _error(str(e), 500)


@bp.route(route="config/tools/{id}", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def get_tool(req: func.HttpRequest) -> func.HttpResponse:
    """Get a tool mapping by id, including the blob definition."""
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentToolMapping
    from agents.utility.util_blob import get_blob_text

    try:
        tool_id = int(req.route_params["id"])
    except (ValueError, KeyError):
        return _error("Invalid tool mapping id")

    try:
        _ensure_tables()
        with get_session() as session:
            row = session.query(AgentToolMapping).filter(AgentToolMapping.id == tool_id).first()
            if not row:
                return _error("Tool mapping not found", 404)
            try:
                definition = json.loads(get_blob_text(row.blob_path))
            except Exception:
                definition = None
            return _json_response({
                "id": row.id, "agent_id": row.agent_id, "tool_name": row.tool_name,
                "blob_path": row.blob_path, "executor_name": row.executor_name,
                "is_active": row.is_active, "definition": definition,
            })
    except Exception as e:
        logging.exception("get_tool error")
        return _error(str(e), 500)


@bp.route(route="config/tools", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def create_tool(req: func.HttpRequest) -> func.HttpResponse:
    """Create a tool mapping for an agent. Accepts either:
    - JSON body: {"agent_id": 1, "tool_name": "...", "definition": {...}, "executor_name": "..."}
    - File upload: multipart/form-data with 'agent_id', 'tool_name', 'file' (.json), optional 'executor_name'
    Agent must exist.
    """
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentToolMapping
    from agents.utility.util_blob import upload_blob

    content_type = (req.headers.get("Content-Type") or "").lower()

    if "multipart/form-data" in content_type:
        uploaded = req.files.get("file")
        if not uploaded:
            return _error("No 'file' field in multipart upload")
        try:
            definition = json.loads(uploaded.stream.read().decode("utf-8"))
        except (json.JSONDecodeError, ValueError) as e:
            return _error(f"Invalid JSON in uploaded file: {e}")
        try:
            agent_id = int(req.form.get("agent_id", ""))
        except (ValueError, TypeError):
            return _error("'agent_id' is required (integer)")
        tool_name = req.form.get("tool_name")
        executor_name = req.form.get("executor_name", tool_name or "")
    else:
        body, err = _parse_json_body(req)
        if err:
            return err
        agent_id = body.get("agent_id")
        if not agent_id or not isinstance(agent_id, int):
            return _error("'agent_id' is required (integer)")
        tool_name = body.get("tool_name")
        definition = body.get("definition", {})
        executor_name = body.get("executor_name", tool_name or "")

    if not tool_name:
        return _error("'tool_name' is required")

    blob_path = f"tools/{tool_name}.json"

    try:
        _ensure_tables()
        with get_session() as session:
            agent = _get_agent_by_id(session, agent_id)
            if not agent:
                return _error(f"Agent with id={agent_id} not found. Create the agent first.", 404)

            existing = session.query(AgentToolMapping).filter(
                AgentToolMapping.agent_id == agent_id, AgentToolMapping.tool_name == tool_name
            ).first()
            if existing:
                return _error(f"Tool mapping '{tool_name}' already exists for agent_id={agent_id} (id={existing.id}). Use PUT to update.", 409)

            upload_blob(blob_path, json.dumps(definition, indent=2))
            row = AgentToolMapping(
                agent_id=agent_id,
                tool_name=tool_name,
                blob_path=blob_path,
                executor_name=executor_name,
                is_active=True,
            )
            session.add(row)
            session.flush()
            tool_id = row.id

        return _json_response({"status": "created", "id": tool_id, "agent_id": agent_id, "tool_name": tool_name}, 201)
    except Exception as e:
        logging.exception("create_tool error")
        return _error(str(e), 500)


@bp.route(route="config/tools/{id}", methods=["PUT"], auth_level=func.AuthLevel.FUNCTION)
def update_tool(req: func.HttpRequest) -> func.HttpResponse:
    """Update a tool mapping by id. Accepts either:
    - JSON body: {"definition": {...}, "executor_name": "..."}
    - File upload: multipart/form-data with 'file' (.json) and optional 'executor_name'
    """
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentToolMapping
    from agents.utility.util_blob import upload_blob

    try:
        tool_id = int(req.route_params["id"])
    except (ValueError, KeyError):
        return _error("Invalid tool mapping id")

    content_type = (req.headers.get("Content-Type") or "").lower()

    if "multipart/form-data" in content_type:
        uploaded = req.files.get("file")
        definition = None
        if uploaded:
            try:
                definition = json.loads(uploaded.stream.read().decode("utf-8"))
            except (json.JSONDecodeError, ValueError) as e:
                return _error(f"Invalid JSON in uploaded file: {e}")
        executor_name = req.form.get("executor_name")
    else:
        body, err = _parse_json_body(req)
        if err:
            return err
        definition = body.get("definition")
        executor_name = body.get("executor_name")

    try:
        _ensure_tables()
        with get_session() as session:
            row = session.query(AgentToolMapping).filter(AgentToolMapping.id == tool_id).first()
            if not row:
                return _error("Tool mapping not found", 404)
            if definition is not None:
                upload_blob(row.blob_path, json.dumps(definition, indent=2))
            if executor_name is not None:
                row.executor_name = executor_name
        return _json_response({"status": "updated", "id": tool_id})
    except Exception as e:
        logging.exception("update_tool error")
        return _error(str(e), 500)


@bp.route(route="config/tools/{id}", methods=["DELETE"], auth_level=func.AuthLevel.FUNCTION)
def delete_tool(req: func.HttpRequest) -> func.HttpResponse:
    """Delete a tool mapping by id."""
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentToolMapping
    from agents.utility.util_blob import delete_blob

    try:
        tool_id = int(req.route_params["id"])
    except (ValueError, KeyError):
        return _error("Invalid tool mapping id")

    try:
        _ensure_tables()
        with get_session() as session:
            row = session.query(AgentToolMapping).filter(AgentToolMapping.id == tool_id).first()
            if not row:
                return _error("Tool mapping not found", 404)
            try:
                delete_blob(row.blob_path)
            except Exception:
                logging.warning(f"Blob {row.blob_path} not found during delete")
            session.delete(row)
        return _json_response({"status": "deleted"})
    except Exception as e:
        logging.exception("delete_tool error")
        return _error(str(e), 500)


# =============================================================================
# SEED
# =============================================================================

@bp.route(route="config/seed", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def seed_config(req: func.HttpRequest) -> func.HttpResponse:
    from agents.utility.util_seed import seed_defaults
    try:
        result = seed_defaults()
        return _json_response(result)
    except Exception as e:
        logging.exception("seed_config error")
        return _error(str(e), 500)
