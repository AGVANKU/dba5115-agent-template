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
            data = [
                {
                    "id": r.id,
                    "name": r.name,
                    "description": r.description,
                    "model": r.model,
                    "knowledge_source": r.knowledge_source,
                    "is_active": r.is_active
                }
                for r in rows
            ]
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
                "knowledge_source": agent.knowledge_source,
                "vector_store_id": agent.vector_store_id,
                "last_indexed_at": agent.last_indexed_at.isoformat() if agent.last_indexed_at else None,
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
    Body: {"name": "...", "description": "...", "model": "gpt-4o-mini", "knowledge_source": "knowledge/docs"}
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
    knowledge_source = body.get("knowledge_source")

    try:
        _ensure_tables()
        with get_session() as session:
            existing = session.query(AgentDefinition).filter(AgentDefinition.name == name).first()
            if existing:
                return _error(f"Agent '{name}' already exists (id={existing.id}). Use PUT to update.", 409)
            agent = AgentDefinition(
                name=name,
                description=description,
                model=model,
                knowledge_source=knowledge_source,
                is_active=True
            )
            session.add(agent)
            session.flush()
            agent_id = agent.id
        return _json_response({
            "status": "created",
            "id": agent_id,
            "name": name,
            "model": model,
            "knowledge_source": knowledge_source
        }, 201)
    except Exception as e:
        logging.exception("create_agent error")
        return _error(str(e), 500)


@bp.route(route="config/agents/{id}", methods=["PUT"], auth_level=func.AuthLevel.FUNCTION)
def update_agent(req: func.HttpRequest) -> func.HttpResponse:
    """Update an existing agent definition.
    Body: {"description": "...", "model": "gpt-4o", "knowledge_source": "knowledge/docs"}

    Note: Setting knowledge_source clears vector_store_id and file_manifest to force reindex.
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
            if "knowledge_source" in body:
                new_source = body["knowledge_source"]
                if new_source != agent.knowledge_source:
                    # Knowledge source changed — clear cached vector store to force reindex
                    agent.knowledge_source = new_source
                    agent.vector_store_id = None
                    agent.file_manifest = None
                    agent.last_indexed_at = None
            if "is_active" in body:
                agent.is_active = body["is_active"]
        return _json_response({"status": "updated", "id": agent_id})
    except Exception as e:
        logging.exception("update_agent error")
        return _error(str(e), 500)


@bp.route(route="config/agents/{id}", methods=["DELETE"], auth_level=func.AuthLevel.FUNCTION)
def delete_agent(req: func.HttpRequest) -> func.HttpResponse:
    """Delete an agent definition with cascade delete of prompts, tool mappings, and vector store.

    - Prompts: Deletes DB row and blob file
    - Tool mappings: Deletes DB row, only deletes blob if no other agent uses the same tool_name
    - Vector store: Deletes from Azure AI Foundry if agent had knowledge_source configured
    """
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentPromptRegistry, AgentToolMapping
    from agents.utility.util_blob import delete_blob

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

            deleted_prompts = 0
            deleted_tools = 0
            deleted_blobs = 0

            # Delete prompts (each agent has unique blob path)
            prompts = session.query(AgentPromptRegistry).filter(AgentPromptRegistry.agent_id == agent_id).all()
            for prompt in prompts:
                try:
                    delete_blob(prompt.blob_path)
                    deleted_blobs += 1
                except Exception:
                    logging.warning(f"Blob {prompt.blob_path} not found during cascade delete")
                session.delete(prompt)
                deleted_prompts += 1

            # Delete tool mappings (blob shared by tool_name — only delete if no other agent uses it)
            tools = session.query(AgentToolMapping).filter(AgentToolMapping.agent_id == agent_id).all()
            for tool in tools:
                # Check if other agents reference the same tool_name
                other_refs = session.query(AgentToolMapping).filter(
                    AgentToolMapping.tool_name == tool.tool_name,
                    AgentToolMapping.agent_id != agent_id
                ).count()

                if other_refs == 0:
                    # No other agent uses this tool — safe to delete blob
                    try:
                        delete_blob(tool.blob_path)
                        deleted_blobs += 1
                    except Exception:
                        logging.warning(f"Blob {tool.blob_path} not found during cascade delete")
                else:
                    logging.info(f"Keeping blob {tool.blob_path} — still referenced by {other_refs} other agent(s)")

                session.delete(tool)
                deleted_tools += 1

            # Delete vector store if agent had knowledge configured
            deleted_vector_store = False
            if agent.vector_store_id:
                try:
                    from agents.tools.knowledge import delete_vector_store
                    from agents.runtime.util_agents import get_agents_client
                    agent_client = get_agents_client()
                    delete_vector_store(agent_client, agent.vector_store_id)
                    deleted_vector_store = True
                except Exception as e:
                    logging.warning(f"Failed to delete vector store {agent.vector_store_id}: {e}")

            # Delete the agent
            session.delete(agent)

        return _json_response({
            "status": "deleted",
            "agent_id": agent_id,
            "cascade": {
                "prompts_deleted": deleted_prompts,
                "tool_mappings_deleted": deleted_tools,
                "blobs_deleted": deleted_blobs,
                "vector_store_deleted": deleted_vector_store
            }
        })
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
# KNOWLEDGE FILES
# =============================================================================

@bp.route(route="config/agents/{id}/knowledge", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def list_knowledge_files(req: func.HttpRequest) -> func.HttpResponse:
    """List all files in an agent's knowledge source."""
    from agents.utility.util_database import get_session
    from agents.utility.util_blob import list_blobs

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
            if not agent.knowledge_source:
                return _error("Agent has no knowledge_source configured", 400)

            files = list_blobs(agent.knowledge_source)
            # Return relative paths (strip knowledge_source prefix)
            prefix = agent.knowledge_source.rstrip("/") + "/"
            file_list = [
                {"name": f[len(prefix):] if f.startswith(prefix) else f, "path": f}
                for f in files
            ]

        return _json_response({
            "agent_id": agent_id,
            "knowledge_source": agent.knowledge_source,
            "files": file_list
        })
    except Exception as e:
        logging.exception("list_knowledge_files error")
        return _error(str(e), 500)


@bp.route(route="config/agents/{id}/knowledge", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def upload_knowledge_file(req: func.HttpRequest) -> func.HttpResponse:
    """Upload a file to an agent's knowledge source.

    Accepts multipart/form-data with 'file' field.
    Clears file_manifest to trigger reindex on next agent run.
    """
    from agents.utility.util_database import get_session
    from agents.utility.util_blob import ensure_container
    from azure.storage.blob import BlobServiceClient
    import os

    try:
        agent_id = int(req.route_params["id"])
    except (ValueError, KeyError):
        return _error("Invalid agent id")

    content_type = (req.headers.get("Content-Type") or "").lower()
    if "multipart/form-data" not in content_type:
        return _error("Content-Type must be multipart/form-data")

    uploaded = req.files.get("file")
    if not uploaded:
        return _error("No 'file' field in multipart upload")

    filename = uploaded.filename
    if not filename:
        return _error("Uploaded file has no filename")

    try:
        _ensure_tables()
        with get_session() as session:
            agent = _get_agent_by_id(session, agent_id)
            if not agent:
                return _error("Agent not found", 404)
            if not agent.knowledge_source:
                return _error("Agent has no knowledge_source configured. Set knowledge_source first via PUT.", 400)

            # Upload to blob
            ensure_container()
            blob_path = f"{agent.knowledge_source.rstrip('/')}/{filename}"

            conn_str = os.getenv("AGENT_CONFIG_BLOB_CONN_STR", "")
            container_name = os.getenv("AGENT_CONFIG_CONTAINER", "agent-config")
            blob_service = BlobServiceClient.from_connection_string(conn_str)
            blob_client = blob_service.get_blob_client(container=container_name, blob=blob_path)
            blob_client.upload_blob(uploaded.stream.read(), overwrite=True)

            # Clear manifest to force reindex
            agent.file_manifest = None
            agent.vector_store_id = None
            session.commit()

            logging.info(f"Uploaded knowledge file: {blob_path}")

        return _json_response({
            "status": "uploaded",
            "agent_id": agent_id,
            "filename": filename,
            "blob_path": blob_path,
            "note": "Knowledge base will reindex on next agent run"
        }, 201)
    except Exception as e:
        logging.exception("upload_knowledge_file error")
        return _error(str(e), 500)


@bp.route(route="config/agents/{id}/knowledge/{filename}", methods=["DELETE"], auth_level=func.AuthLevel.FUNCTION)
def delete_knowledge_file(req: func.HttpRequest) -> func.HttpResponse:
    """Delete a file from an agent's knowledge source.

    Clears file_manifest to trigger reindex on next agent run.
    """
    from agents.utility.util_database import get_session
    from agents.utility.util_blob import delete_blob

    try:
        agent_id = int(req.route_params["id"])
        filename = req.route_params.get("filename")
    except (ValueError, KeyError):
        return _error("Invalid agent id")

    if not filename:
        return _error("Filename is required")

    try:
        _ensure_tables()
        with get_session() as session:
            agent = _get_agent_by_id(session, agent_id)
            if not agent:
                return _error("Agent not found", 404)
            if not agent.knowledge_source:
                return _error("Agent has no knowledge_source configured", 400)

            blob_path = f"{agent.knowledge_source.rstrip('/')}/{filename}"

            try:
                delete_blob(blob_path)
            except Exception:
                return _error(f"File '{filename}' not found in knowledge source", 404)

            # Clear manifest to force reindex
            agent.file_manifest = None
            agent.vector_store_id = None
            session.commit()

            logging.info(f"Deleted knowledge file: {blob_path}")

        return _json_response({
            "status": "deleted",
            "agent_id": agent_id,
            "filename": filename,
            "note": "Knowledge base will reindex on next agent run"
        })
    except Exception as e:
        logging.exception("delete_knowledge_file error")
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
