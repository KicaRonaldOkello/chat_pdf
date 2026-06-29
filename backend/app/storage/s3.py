"""S3-backed storage backend for staging / production.

Wraps the same boto3 logic that formerly lived in ``app.s3_storage``.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import AWS_REGION, S3_BUCKET, S3_KEY_PREFIX
from app.storage.base import StorageBackend

log = logging.getLogger(__name__)

_CHUNK_SIZE = 65_536  # 64 KiB


class S3StorageBackend(StorageBackend):
    """Read/write files in an S3 bucket."""

    def __init__(self) -> None:
        self._client: Any = None

    def _s3(self) -> Any:
        if self._client is None:
            self._client = boto3.client(
                "s3",
                region_name=AWS_REGION,
                config=Config(
                    signature_version="s3v4",
                    retries={"max_attempts": 3},
                ),
            )
        return self._client

    # ── key helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _pdf_key(doc_id: str) -> str:
        return f"{S3_KEY_PREFIX}/{doc_id}/source.pdf"

    @staticmethod
    def _image_key(doc_id: str, filename: str) -> str:
        return f"{S3_KEY_PREFIX}/{doc_id}/images/{filename.lstrip('/')}"

    # ── PDF source files ─────────────────────────────────────────────────

    def put_source_pdf_bytes(
        self, doc_id: str, data: bytes, content_type: str = "application/pdf"
    ) -> None:
        self._s3().put_object(
            Bucket=S3_BUCKET,
            Key=self._pdf_key(doc_id),
            Body=data,
            ContentType=content_type,
        )

    def get_source_pdf_bytes(self, doc_id: str) -> bytes:
        try:
            obj = self._s3().get_object(
                Bucket=S3_BUCKET, Key=self._pdf_key(doc_id)
            )
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise FileNotFoundError(
                    f"s3://{S3_BUCKET}/{self._pdf_key(doc_id)}"
                ) from e
            raise
        return obj["Body"].read()

    def get_source_pdf_streaming(self, doc_id: str) -> Iterator[bytes]:
        """Yield the PDF body in chunks from S3."""
        try:
            obj = self._s3().get_object(
                Bucket=S3_BUCKET, Key=self._pdf_key(doc_id)
            )
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise FileNotFoundError(
                    f"s3://{S3_BUCKET}/{self._pdf_key(doc_id)}"
                ) from e
            raise
        yield from obj["Body"].iter_chunks(chunk_size=_CHUNK_SIZE)

    # ── Image files ──────────────────────────────────────────────────────

    def put_image_bytes(
        self,
        doc_id: str,
        filename: str,
        data: bytes,
        content_type: str = "image/png",
    ) -> str:
        key = self._image_key(doc_id, filename)
        self._s3().put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key

    # ── Table Markdown ────────────────────────────────────────────────────

    @staticmethod
    def _table_key(doc_id: str, table_index: int) -> str:
        return f"{S3_KEY_PREFIX}/{doc_id}/tables/table_{table_index}.md"

    def put_table_markdown(self, doc_id: str, table_index: int, markdown: str) -> str:
        key = self._table_key(doc_id, table_index)
        self._s3().put_object(
            Bucket=S3_BUCKET,
            Key=key,
            Body=markdown.encode("utf-8"),
            ContentType="text/markdown; charset=utf-8",
        )
        return f"tables/table_{table_index}.md"

    def get_table_markdown(self, doc_id: str, key: str) -> str:
        s3_key = f"{S3_KEY_PREFIX}/{doc_id}/{key}"
        try:
            obj = self._s3().get_object(Bucket=S3_BUCKET, Key=s3_key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                raise FileNotFoundError(f"s3://{S3_BUCKET}/{s3_key}") from e
            raise
        return obj["Body"].read().decode("utf-8")

    # ── Cleanup ──────────────────────────────────────────────────────────

    def delete_all_for_document(self, doc_id: str) -> None:
        c = self._s3()
        prefix = f"{S3_KEY_PREFIX}/{doc_id}/"
        paginator = c.get_paginator("list_objects_v2")
        batch: list[dict[str, str]] = []
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for o in page.get("Contents", []):
                batch.append({"Key": o["Key"]})
        if not batch:
            return
        for i in range(0, len(batch), 1000):
            c.delete_objects(
                Bucket=S3_BUCKET,
                Delete={"Objects": batch[i : i + 1000]},
            )

    # ── Debug / Local Inspection ─────────────────────────────────────────

    def put_debug_json(self, doc_id: str, filename: str, data: Any) -> None:
        """No-op for S3 mode to avoid cluttering production storage."""
        pass
