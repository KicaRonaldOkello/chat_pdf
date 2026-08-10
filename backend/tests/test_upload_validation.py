"""Upload endpoint validation tests (magic bytes, readability)."""

from __future__ import annotations

from unittest.mock import patch

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.upload import router as upload_router
from app.auth.google_auth import require_session_token


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(upload_router)
    return app


def _text_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello world. " * 20)
    data = doc.tobytes()
    doc.close()
    return data


def test_upload_rejects_non_pdf_magic_bytes() -> None:
    app = _make_app()
    app.dependency_overrides[require_session_token] = lambda: {"sub": "user-1"}

    with (
        patch("app.api.routes.upload.document_data.save_upload_and_record") as save,
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/upload",
            files={
                "file": (
                    "notes.pdf",
                    b"PK\x03\x04 not really a pdf",
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 400
    assert "valid PDF" in response.json()["detail"]
    save.assert_not_called()


def test_upload_accepts_real_pdf() -> None:
    app = _make_app()
    app.dependency_overrides[require_session_token] = lambda: {"sub": "user-1"}

    with (
        patch(
            "app.api.routes.upload.document_data.save_upload_and_record",
            return_value="doc-1",
        ) as save,
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/upload",
            files={
                "file": (
                    "notes.pdf",
                    _text_pdf_bytes(),
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 200
    assert response.json()["document_id"] == "doc-1"
    save.assert_called_once()
