"""Routes under ``/api/users`` — authentication & user management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.claims import email_from_claims
from app.auth.clerk_jwt import require_clerk_session
from app.db.dependencies import get_user_repository
from app.db.repositories import UserRepository, UserRow

router = APIRouter(prefix="/api/users", tags=["auth"])


class UserSyncResponse(BaseModel):
    clerk_user_id: str
    email: str | None
    created_at: str
    last_seen_at: str


@router.post("/sync", response_model=UserSyncResponse)
async def sync_user(
    user_repo: UserRepository = Depends(get_user_repository),
    claims: dict[str, Any] = Depends(require_clerk_session),
) -> UserSyncResponse:
    """Idempotent: upsert the signed-in Clerk user; call after sign-in with Bearer session token."""
    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token missing `sub`",
        )
    email = email_from_claims(claims)
    user: UserRow = await user_repo.upsert_clerk_user(sub, email)
    return UserSyncResponse(
        clerk_user_id=user.clerk_user_id,
        email=user.email,
        created_at=user.created_at.isoformat(),
        last_seen_at=user.last_seen_at.isoformat(),
    )
