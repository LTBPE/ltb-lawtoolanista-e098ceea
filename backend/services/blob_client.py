"""
Azure Blob Storage client for saving and loading page content snapshots.
"""

import logging
from datetime import datetime

from azure.storage.blob.aio import BlobServiceClient
from shared.config import config

logger = logging.getLogger(__name__)

_blob_service_client: BlobServiceClient | None = None


def _get_client() -> BlobServiceClient:
    """Return a cached BlobServiceClient."""
    global _blob_service_client
    if _blob_service_client is None:
        _blob_service_client = BlobServiceClient.from_connection_string(
            config.AZURE_WEBJOBS_STORAGE
        )
    return _blob_service_client


def _build_blob_path(court_id: int, scan_time: datetime, version: str) -> str:
    """Build the blob path for a snapshot."""
    ts = scan_time.strftime("%Y%m%dT%H%M%S")
    return f"{court_id}/{ts}/{version}.txt"


async def save_snapshot(
    court_id: int, scan_time: datetime, content: str, version: str
) -> str:
    """
    Save content to Azure Blob Storage and return the blob path.

    Args:
        court_id: The court's database ID.
        scan_time: The time of the scan (used in the path).
        content: The text content to store.
        version: Either "old" or "new".

    Returns:
        Blob path string, e.g. "42/20240101T080000/new.txt".
    """
    path = _build_blob_path(court_id, scan_time, version)
    client = _get_client()
    container = client.get_container_client(config.BLOB_CONTAINER_NAME)

    # Create container if it does not exist
    try:
        await container.create_container()
    except Exception:
        pass  # Already exists

    blob = container.get_blob_client(path)
    await blob.upload_blob(
        content.encode("utf-8", errors="replace"),
        overwrite=True,
        content_settings=None,
    )
    logger.debug("Saved snapshot to blob: %s", path)
    return path


async def load_snapshot(blob_path: str) -> str:
    """
    Load text content from a blob path.

    Args:
        blob_path: Path within the container, e.g. "42/20240101T080000/new.txt".

    Returns:
        The decoded text content, or empty string if not found.
    """
    client = _get_client()
    blob = client.get_blob_client(
        container=config.BLOB_CONTAINER_NAME, blob=blob_path
    )
    try:
        stream = await blob.download_blob()
        data = await stream.readall()
        return data.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.error("Failed to load blob %s: %s", blob_path, exc)
        return ""
