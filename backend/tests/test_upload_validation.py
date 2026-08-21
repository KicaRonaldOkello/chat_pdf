"""Upload endpoint validation tests (magic bytes, readability)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import fitz
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.upload import router as upload_router
from app.auth.google_auth import require_session_token
from app.db.dependencies import (
    get_plan_repository,
    get_subscription_repository,
    get_usage_meter_repository,
)
from app.db.repositories import PlanRow


def _free_plan() -> PlanRow:
    return PlanRow(
        id=1,
        slug="free",
        name="Free",
        billing_period=None,
        dodo_product_id=None,
        price_cents=0,
        words_per_day=2_000,
        uploads_per_day=5,
        upload_bytes_per_day=5 * 1024 * 1024,
        max_upload_bytes_per_import=5 * 1024 * 1024,
        files_in_scope=2,
        is_active=True,
        created_at=datetime.now(UTC),
    )


class _FakePlanRepo:
    async def get_by_slug(self, slug: str) -> PlanRow | None:
        return _free_plan()

    async def get_free_plan(self) -> PlanRow | None:
        return _free_plan()


class _FakeSubscriptionRepo:
    async def get_for_user(self, user_id: str) -> None:
        return None


class _FakeUsageRepo:
    async def get_for_user_date(self, user_id: str, usage_date) -> None:
        return None

    async def increment(self, *args, **kwargs) -> None:
        return None


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(upload_router)
    app.dependency_overrides[get_plan_repository] = lambda: _FakePlanRepo()
    app.dependency_overrides[get_subscription_repository] = (
        lambda: _FakeSubscriptionRepo()
    )
    app.dependency_overrides[get_usage_meter_repository] = lambda: _FakeUsageRepo()
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
