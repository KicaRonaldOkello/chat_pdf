"""Storage layer — choose backend via ``STORAGE_BACKEND`` env var.

Usage at any call site::

    from app.storage import get_storage

    storage = get_storage()
    storage.put_source_pdf_bytes(doc_id, data)
"""

from __future__ import annotations

import logging

from app.storage.base import StorageBackend

log = logging.getLogger(__name__)

_instance: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """Return the singleton storage backend (created on first call)."""
    global _instance
    if _instance is not None:
        return _instance

    from app.settings import settings

    backend = settings.storage_backend.lower()
    if backend == "local":
        from app.storage.local import LocalStorageBackend

        _instance = LocalStorageBackend()
        log.info("storage backend: local filesystem")
    elif backend == "s3":
        from app.storage.s3 import S3StorageBackend

        _instance = S3StorageBackend()
        log.info("storage backend: S3")
    else:
        raise ValueError(
            f"Unknown STORAGE_BACKEND={backend!r}. "
            "Expected 'local' or 's3'."
        )
    return _instance


# Re-export the base type for type annotations
__all__ = ["StorageBackend", "get_storage"]
