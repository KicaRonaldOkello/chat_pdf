"""Routes under ``/api/chat`` — streaming chat endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.chat import chat_stream_ndjson
from app.api.schemas import ChatRequest
from app.auth.google_auth import require_session_token

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    _claims: dict[str, Any] = Depends(require_session_token),
) -> StreamingResponse:
    return StreamingResponse(
        chat_stream_ndjson(body),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
