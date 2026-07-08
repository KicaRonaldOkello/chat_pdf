"""Routes under ``/api/users`` — authentication & user management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth.google_auth import (
    create_session_token,
    require_session_token,
    verify_google_id_token,
)
from app.auth.session import log_auth_event, make_fingerprint
from app.db.dependencies import get_user_repository
from app.db.repositories import UserRepository, UserRow

router = APIRouter(prefix="/api/users", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


class UserSyncResponse(BaseModel):
    user_id: str
    email: str | None
    name: str | None
    picture: str | None
    session_token: str
    created_at: str
    last_seen_at: str


@router.post("/sync", response_model=UserSyncResponse)
@limiter.limit("10/minute")
async def sync_user(
    request: Request,
    authorization: str = Header(...),
    user_repo: UserRepository = Depends(get_user_repository),
) -> UserSyncResponse:
    """Exchange a Google ID token for a custom session token. Call after Google sign-in."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
        )
    google_token = authorization[7:]  # Remove "Bearer " prefix
    
    # Verify the Google ID token
    google_claims = verify_google_id_token(google_token)
    google_sub = google_claims.get("sub")
    google_email = google_claims.get("email")
    google_name = google_claims.get("name")
    google_picture = google_claims.get("picture")

    if not google_sub or not isinstance(google_sub, str):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google token missing `sub`",
        )

    # Upsert user in our database
    user: UserRow = await user_repo.upsert_user(
        google_sub, google_email, name=google_name, picture=google_picture
    )

    fp = make_fingerprint(
        user_agent=request.headers.get("user-agent", ""),
        ip_address=request.client.host if request.client else "",
    )
    session_token = create_session_token(
        user.user_id, user.email,
        name=google_name, picture=google_picture, fingerprint=fp,
    )
    await log_auth_event(
        user.user_id, "login",
        ip_address=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent", ""),
    )

    return UserSyncResponse(
        user_id=user.user_id,
        email=user.email,
        name=google_name,
        picture=google_picture,
        session_token=session_token,
        created_at=user.created_at.isoformat(),
        last_seen_at=user.last_seen_at.isoformat(),
    )


class SessionProfile(BaseModel):
    user_id: str
    email: str | None
    name: str | None
    picture: str | None


@router.get("/me", response_model=SessionProfile)
async def get_current_user(
    claims: dict[str, Any] = Depends(require_session_token),
) -> SessionProfile:
    """Validate the session token and return the current user's profile."""
    return SessionProfile(
        user_id=claims.get("sub", ""),
        email=claims.get("email"),
        name=claims.get("name"),
        picture=claims.get("picture"),
    )
