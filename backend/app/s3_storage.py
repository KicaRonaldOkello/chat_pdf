"""S3 object helpers for `documents/{doc_id}/source.pdf`."""

from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import AWS_REGION, S3_BUCKET, S3_KEY_PREFIX

log = logging.getLogger(__name__)

_s3: Any = None  # type: ignore[valid-type]


def s3_key_for_document(doc_id: str) -> str:
    return f"{S3_KEY_PREFIX}/{doc_id}/source.pdf"


def s3_key_for_image(doc_id: str, filename: str) -> str:
    return f"{S3_KEY_PREFIX}/{doc_id}/images/{filename.lstrip('/')}"


def _client() -> Any:
    global _s3
    if _s3 is None:
        # Signature version 4; reuse connections
        _s3 = boto3.client(
            "s3",
            region_name=AWS_REGION,
            config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
        )
    return _s3


def put_source_pdf_bytes(doc_id: str, data: bytes, content_type: str = "application/pdf") -> None:
    _client().put_object(
        Bucket=S3_BUCKET,
        Key=s3_key_for_document(doc_id),
        Body=data,
        ContentType=content_type,
    )


def get_source_pdf_bytes(doc_id: str) -> bytes:
    try:
        obj = _client().get_object(Bucket=S3_BUCKET, Key=s3_key_for_document(doc_id))
    except ClientError as e:  # pragma: no cover
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            raise FileNotFoundError(f"s3://{S3_BUCKET}/{s3_key_for_document(doc_id)}") from e
        raise
    return obj["Body"].read()


def put_image_bytes(
    doc_id: str,
    filename: str,
    data: bytes,
    content_type: str = "image/png",
) -> str:
    """Upload under ``documents/{doc_id}/images/...``; returns the S3 object key."""
    key = s3_key_for_image(doc_id, filename)
    _client().put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return key


def delete_all_for_document(doc_id: str) -> None:
    """Remove every object under ``{prefix}/{doc_id}/`` (PDF, images, any future files)."""
    c = _client()
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
            Bucket=S3_BUCKET, Delete={"Objects": batch[i : i + 1000]}
        )


def get_object_streaming(doc_id: str) -> Any:
    """S3 get_object result; use ``['Body'].iter_chunks()`` for the PDF bytes."""
    return _client().get_object(Bucket=S3_BUCKET, Key=s3_key_for_document(doc_id))
