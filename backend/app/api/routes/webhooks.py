"""Routes under ``/webhooks`` — inbound provider callbacks (no auth)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from app.billing import dodo
from app.billing import webhooks as webhook_handlers

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger(__name__)


@router.post("/dodo")
async def dodo_webhook(request: Request) -> dict[str, Any]:
    """Receive a verified Dodo webhook delivery."""
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty body")

    try:
        event = dodo.unwrap_webhook(raw.decode("utf-8"), dict(request.headers))
    except Exception as exc:
        log.warning("Dodo webhook signature verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        ) from exc

    session_maker = getattr(request.app.state, "async_session_maker", None)
    if session_maker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured.",
        )

    try:
        await webhook_handlers.process_event(
            event,
            session_maker,
            message_id=request.headers.get("webhook-id") or None,
        )
    except Exception as exc:
        log.exception("Dodo webhook %s processing failed", getattr(event, "type", "?"))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing failed",
        ) from exc

    return {"received": True, "type": getattr(event, "type", "")}
