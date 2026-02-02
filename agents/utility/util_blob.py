"""
Azure Blob Storage utilities for agent configuration.

Container: agent-config (configurable via AGENT_CONFIG_CONTAINER env var)
Connection: AGENT_CONFIG_BLOB_CONN_STR env var
"""

import logging
import os

from azure.storage.blob import BlobServiceClient, ContainerClient

BLOB_CONN_STR = os.getenv("AGENT_CONFIG_BLOB_CONN_STR", "")
CONTAINER_NAME = os.getenv("AGENT_CONFIG_CONTAINER", "agent-config")


def _get_container_client() -> ContainerClient:
    if not BLOB_CONN_STR:
        raise RuntimeError("AGENT_CONFIG_BLOB_CONN_STR not set")
    client = BlobServiceClient.from_connection_string(BLOB_CONN_STR)
    return client.get_container_client(CONTAINER_NAME)


def ensure_container() -> None:
    """Create the blob container if it doesn't exist."""
    container = _get_container_client()
    if not container.exists():
        container.create_container()
        logging.info(f"Created blob container: {CONTAINER_NAME}")


def get_blob_text(path: str) -> str:
    """Download a blob as UTF-8 text."""
    container = _get_container_client()
    blob = container.get_blob_client(path)
    return blob.download_blob(encoding="utf-8").readall()


def upload_blob(path: str, content: str) -> None:
    """Upload text content to a blob (overwrite if exists)."""
    container = _get_container_client()
    blob = container.get_blob_client(path)
    blob.upload_blob(content, overwrite=True)
    logging.info(f"Uploaded blob: {path}")


def delete_blob(path: str) -> None:
    """Delete a blob."""
    container = _get_container_client()
    blob = container.get_blob_client(path)
    blob.delete_blob()
    logging.info(f"Deleted blob: {path}")


def list_blobs(prefix: str = "") -> list[str]:
    """List blob names under a prefix."""
    container = _get_container_client()
    return [b.name for b in container.list_blobs(name_starts_with=prefix)]
