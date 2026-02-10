"""
Knowledge Base Management - Vector Store, Ingestion, and Sync

Provides RAG capabilities for agents using Azure AI Foundry's file_search.
Knowledge source is configured directly on AgentDefinition.
Indexing happens automatically when agent runs if files changed.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    from azure.ai.agents.models import ToolResources, FileSearchToolResource, FileSearchToolDefinition
except ImportError:
    from azure.ai.agents.models import ToolResources
    FileSearchToolResource = None
    FileSearchToolDefinition = None


# =============================================================================
# CONFIGURATION
# =============================================================================

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}


# =============================================================================
# VECTOR STORE MANAGEMENT
# =============================================================================

def create_vector_store(agent_client, name: str) -> str:
    """Create a new vector store in Azure AI Foundry."""
    vector_store = agent_client.vector_stores.create(
        name=name,
        expires_after={"anchor": "last_active_at", "days": 30}
    )
    logging.info(f"Created vector store: {vector_store.id} ({name})")
    return vector_store.id


def delete_vector_store(agent_client, vector_store_id: str) -> bool:
    """Delete a vector store."""
    try:
        agent_client.vector_stores.delete(vector_store_id)
        logging.info(f"Deleted vector store: {vector_store_id}")
        return True
    except Exception as e:
        logging.error(f"Failed to delete vector store {vector_store_id}: {e}")
        return False


def upload_files_to_vector_store(agent_client, vector_store_id: str, file_paths: list[str]) -> int:
    """Upload files to a vector store for indexing."""
    uploaded = 0
    for file_path in file_paths:
        try:
            with open(file_path, "rb") as f:
                uploaded_file = agent_client.files.upload(file=f, purpose="assistants")
                agent_client.vector_store_files.create(
                    vector_store_id=vector_store_id,
                    file_id=uploaded_file.id
                )
                uploaded += 1
        except Exception as e:
            logging.error(f"Failed to upload {file_path}: {e}")
    return uploaded


# =============================================================================
# DOCUMENT INGESTION
# =============================================================================

def load_documents(knowledge_source: str) -> list[dict]:
    """Load documents from blob storage or local repo (fallback)."""
    documents = load_from_blob(knowledge_source)
    if not documents:
        documents = load_from_repo(knowledge_source)
    logging.info(f"Loaded {len(documents)} documents from {knowledge_source}")
    return documents


def load_from_blob(source_path: str) -> list[dict]:
    """Load documents from Azure Blob Storage."""
    try:
        from agents.utility.util_blob import list_blobs, get_blob_bytes

        documents = []
        blob_names = list_blobs(source_path)

        for blob_name in blob_names:
            ext = Path(blob_name).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            content = get_blob_bytes(blob_name)
            file_hash = hashlib.md5(content).hexdigest()
            documents.append({"path": blob_name, "content": content, "hash": file_hash})

        return documents
    except Exception as e:
        logging.warning(f"Blob storage load failed: {e}")
        return []


def load_from_repo(source_path: str) -> list[dict]:
    """Load documents from local repository (fallback)."""
    documents = []
    repo_root = Path(__file__).resolve().parents[2]
    local_path = repo_root / source_path

    if not local_path.exists():
        logging.warning(f"Local path does not exist: {local_path}")
        return []

    for file_path in local_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        content = file_path.read_bytes()
        file_hash = hashlib.md5(content).hexdigest()
        documents.append({
            "path": str(file_path.relative_to(repo_root)),
            "content": content,
            "hash": file_hash
        })

    return documents


def save_documents_locally(documents: list[dict], temp_dir: str) -> list[str]:
    """Save document contents to temporary local files for upload."""
    file_paths = []
    temp_path = Path(temp_dir)
    temp_path.mkdir(parents=True, exist_ok=True)

    for doc in documents:
        filename = Path(doc["path"]).name
        local_path = temp_path / filename
        local_path.write_bytes(doc["content"])
        file_paths.append(str(local_path))

    return file_paths


# =============================================================================
# CHANGE DETECTION
# =============================================================================

def compute_manifest(documents: list[dict]) -> dict[str, str]:
    """Compute file manifest for change detection."""
    return {Path(doc["path"]).name: doc["hash"] for doc in documents}


def needs_reindex(stored_manifest: dict | None, current_manifest: dict) -> bool:
    """Check if re-indexing is needed by comparing manifests."""
    if not stored_manifest:
        return True
    if set(stored_manifest.keys()) != set(current_manifest.keys()):
        return True
    for filename, current_hash in current_manifest.items():
        if stored_manifest.get(filename) != current_hash:
            return True
    return False


# =============================================================================
# SYNC ORCHESTRATION
# =============================================================================

def sync_agent_knowledge(agent_name: str) -> str | None:
    """
    Sync knowledge base for an agent: load documents, check for changes, reindex if needed.

    Args:
        agent_name: Name of the agent

    Returns:
        Vector store ID (existing or newly created), or None if no knowledge source
    """
    import tempfile
    from agents.utility.util_database import get_session
    from agents.utility.util_datamodel import AgentDefinition
    from agents.runtime.util_agents import get_agents_client

    with get_session() as session:
        agent = session.query(AgentDefinition).filter(
            AgentDefinition.name == agent_name,
            AgentDefinition.is_active == True
        ).first()

        if not agent or not agent.knowledge_source:
            return None

        # Load documents
        documents = load_documents(agent.knowledge_source)

        if not documents:
            logging.warning(f"No documents found in {agent.knowledge_source}")
            return agent.vector_store_id

        # Check if reindex needed
        current_manifest = compute_manifest(documents)
        stored_manifest = json.loads(agent.file_manifest) if agent.file_manifest else None

        if not needs_reindex(stored_manifest, current_manifest):
            return agent.vector_store_id

        # Get agent client
        agent_client = get_agents_client()

        # Delete old vector store if exists
        if agent.vector_store_id:
            delete_vector_store(agent_client, agent.vector_store_id)

        # Create new vector store
        vector_store_id = create_vector_store(agent_client, f"kb_{agent_name}")

        # Upload documents
        with tempfile.TemporaryDirectory() as temp_dir:
            file_paths = save_documents_locally(documents, temp_dir)
            upload_files_to_vector_store(agent_client, vector_store_id, file_paths)

        # Update agent record
        agent.vector_store_id = vector_store_id
        agent.file_manifest = json.dumps(current_manifest)
        agent.last_indexed_at = datetime.now(timezone.utc)
        session.commit()

        logging.info(f"Knowledge indexed for '{agent_name}': {len(documents)} files")
        return vector_store_id


# =============================================================================
# PUBLIC API (called from util_agents.py)
# =============================================================================

def get_knowledge_resources(agent_type: str) -> ToolResources | None:
    """
    Get Foundry ToolResources for a knowledge-enabled agent.

    Called by get_tools() to attach vector store to agent.
    Returns None for agents without knowledge_source configured.

    Side effect: Syncs knowledge base if files changed.
    """
    from agents.utility.util_database import get_session, ensure_table
    from agents.utility.util_datamodel import AgentDefinition

    ensure_table(AgentDefinition)

    # Quick check if agent has knowledge_source
    with get_session() as session:
        agent = session.query(AgentDefinition).filter(
            AgentDefinition.name == agent_type,
            AgentDefinition.is_active == True
        ).first()

        if not agent or not agent.knowledge_source:
            return None

    # Sync knowledge base (indexes if needed)
    vector_store_id = sync_agent_knowledge(agent_type)

    if not vector_store_id:
        return None

    # Return Foundry tool resources with file_search
    if FileSearchToolResource:
        return ToolResources(
            file_search=FileSearchToolResource(vector_store_ids=[vector_store_id])
        )
    else:
        resources = ToolResources()
        resources.file_search = {"vector_store_ids": [vector_store_id]}
        return resources


def get_file_search_tool():
    """Get FileSearchTool definition for agents with knowledge base."""
    if FileSearchToolDefinition:
        return FileSearchToolDefinition()
    return {"type": "file_search"}
