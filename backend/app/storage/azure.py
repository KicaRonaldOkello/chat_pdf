"""Azure Blob Storage backend for staging / production."""

from __future__ import annotations

import logging
from typing import Any, Iterator

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings

from app.settings import settings
from app.storage.base import StorageBackend

log = logging.getLogger(__name__)

_CHUNK_SIZE = 65_536  # 64 KiB


class AzureStorageBackend(StorageBackend):
    """Read/write files in an Azure Blob Storage container."""

    def __init__(self) -> None:
        self._client: BlobServiceClient | None = None
        self._container_client: Any = None

    def _blob(self) -> BlobServiceClient:
        if self._client is None:
            self._client = BlobServiceClient.from_connection_string(
                settings.azure_storage_connection_string
            )
        return self._client

    def _container(self):
        if self._container_client is None:
            container_name = settings.azure_storage_container_name
            client = self._blob()
            self._container_client = client.get_container_client(container_name)
            try:
                self._container_client.get_container_properties()
                log.info("Using existing Azure container: %s", container_name)
            except ResourceNotFoundError:
                log.info("Creating Azure container: %s", container_name)
                client.create_container(container_name)
        return self._container_client

    # ── key helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _pdf_blob_name(doc_id: str) -> str:
        return f"{doc_id}/source.pdf"

    @staticmethod
    def _image_blob_name(doc_id: str, filename: str) -> str:
        return f"{doc_id}/images/{filename.lstrip('/')}"

    @staticmethod
    def _table_blob_name(doc_id: str, table_index: int) -> str:
        return f"{doc_id}/tables/table_{table_index}.md"

    # ── PDF source files ─────────────────────────────────────────────────

    def put_source_pdf_bytes(
        self, doc_id: str, data: bytes, content_type: str = "application/pdf"
    ) -> None:
        self._container().upload_blob(
            name=self._pdf_blob_name(doc_id),
            data=data,
            content_settings=ContentSettings(content_type=content_type),
            overwrite=True,
        )

    def get_source_pdf_bytes(self, doc_id: str) -> bytes:
        try:
            return self._container().download_blob(
                self._pdf_blob_name(doc_id)
            ).readall()
        except ResourceNotFoundError:
            raise FileNotFoundError(
                f"azure://{settings.azure_storage_container_name}/{self._pdf_blob_name(doc_id)}"
            )

    def get_source_pdf_streaming(self, doc_id: str) -> Iterator[bytes]:
        try:
            stream = self._container().download_blob(
                self._pdf_blob_name(doc_id)
            )
        except ResourceNotFoundError:
            raise FileNotFoundError(
                f"azure://{settings.azure_storage_container_name}/{self._pdf_blob_name(doc_id)}"
            )
        while chunk := stream.read(_CHUNK_SIZE):
            yield chunk

    # ── Image files ──────────────────────────────────────────────────────

    def put_image_bytes(
        self,
        doc_id: str,
        filename: str,
        data: bytes,
        content_type: str = "image/png",
    ) -> str:
        name = self._image_blob_name(doc_id, filename)
        self._container().upload_blob(
            name=name,
            data=data,
            content_settings=ContentSettings(content_type=content_type),
            overwrite=True,
        )
        return name

    # ── Table Markdown ────────────────────────────────────────────────────

    def put_table_markdown(self, doc_id: str, table_index: int, markdown: str) -> str:
        name = self._table_blob_name(doc_id, table_index)
        key = f"tables/table_{table_index}.md"
        self._container().upload_blob(
            name=name,
            data=markdown.encode("utf-8"),
            content_settings=ContentSettings(content_type="text/markdown; charset=utf-8"),
            overwrite=True,
        )
        return key

    def get_table_markdown(self, doc_id: str, key: str) -> str:
        name = f"{doc_id}/{key}"
        try:
            return self._container().download_blob(name).readall().decode("utf-8")
        except ResourceNotFoundError:
            raise FileNotFoundError(
                f"azure://{settings.azure_storage_container_name}/{name}"
            )

    # ── Cleanup ──────────────────────────────────────────────────────────

    def delete_all_for_document(self, doc_id: str) -> None:
        container = self._container()
        prefix = f"{doc_id}/"
        for blob in container.list_blobs(name_starts_with=prefix):
            container.delete_blob(blob.name)

    # ── Debug / Local Inspection ─────────────────────────────────────────

    def put_debug_json(self, doc_id: str, filename: str, data: Any) -> None:
        """No-op in Azure — all enrichment data (tree, chunks, sections_index, metadata)
        is already persisted in PostgreSQL/pgvector and read from there at query time.
        These JSON copies only exist for local filesystem debugging convenience."""
        pass
