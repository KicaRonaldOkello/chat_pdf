"""Verify Google ID Tokens and manage custom backend session JWTs (HS256)."""

from __future__ import annotations

import logging
import time
from typing import Any, cast

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.auth.session import is_token_revoked
from app.settings import settings as _settings

log = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)

# Google JWK client for ID token verification
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_google_jwks = PyJWKClient(GOOGLE_JWKS_URL, cache_jwk_set=True)


def verify_google_id_token(token: str) -> dict[str, Any]:
    """Validate a Google-issued ID token (JWT) and return its claims."""
    if not _settings.google_client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID is not configured on the server")

    signing_key = _google_jwks.get_signing_key_from_jwt(token)
    options: dict[str, bool] = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_iss": True,
        "verify_aud": True,
    }
    
    # Google's ID Token issuer is either accounts.google.com or https://accounts.google.com
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=_settings.google_client_id,
        options=cast(Any, options),
    )
    
    iss = claims.get("iss", "")
    if iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError(f"Invalid issuer: {iss}")

    # Validate required scopes
    scope = claims.get("scope", "")
    if "email" not in scope or "profile" not in scope:
        raise ValueError(f"Insufficient token scopes: {scope}")

    return claims


def create_session_token(
    user_id: str,
    email: str | None,
    name: str | None = None,
    picture: str | None = None,
    *,
    fingerprint: str = "",
) -> str:
    """Issue a custom session JWT (HS256) signed by this backend."""
    import uuid

    now = int(time.time())
    expires = now + (_settings.jwt_expires_days * 24 * 60 * 60)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": expires,
        "jti": uuid.uuid4().hex[:16],
    }
    if name:
        payload["name"] = name
    if picture:
        payload["picture"] = picture
    if fingerprint:
        payload["fp"] = fingerprint
    return jwt.encode(payload, _settings.jwt_secret, algorithm="HS256")


def verify_session_token(token: str) -> dict[str, Any]:
    """Validate a backend-issued custom session token and return its claims."""
    return jwt.decode(token, _settings.jwt_secret, algorithms=["HS256"])


def build_http_exception(e: Exception) -> HTTPException:
    if isinstance(e, jwt.ExpiredSignatureError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )
    if isinstance(e, (jwt.PyJWTError, ValueError)):
        log.debug("JWT verification error: %s", e, exc_info=False)
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )


async def require_session_token(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    """FastAPI dependency: validate JWT, check blacklist, return claims."""
    if (
        creds is None
        or (creds.scheme or "").lower() != "bearer"
        or not creds.credentials
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    try:
        claims = verify_session_token(creds.credentials)
    except Exception as e:
        raise build_http_exception(e) from e

    if await is_token_revoked(claims.get("jti", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked",
        )
    return claims


