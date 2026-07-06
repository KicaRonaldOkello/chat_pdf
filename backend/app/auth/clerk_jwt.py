"""Verify Clerk-issued session JWTs (RS256, JWKS)."""

from __future__ import annotations

import logging
from typing import Any, cast

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.settings import settings as _settings

CLERK_ISSUER = _settings.clerk_issuer
CLERK_JWKS_URL = _settings.clerk_jwks_url
CLERK_JWT_AUDIENCE = _settings.clerk_jwt_audience

log = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)
_bearer_optional = HTTPBearer(auto_error=False)
_jwks: PyJWKClient | None = None


def _get_jwks() -> PyJWKClient:
    global _jwks
    if not CLERK_JWKS_URL:
        raise RuntimeError("CLERK_JWKS_URL is not configured")
    if _jwks is None:
        _jwks = PyJWKClient(CLERK_JWKS_URL, cache_jwk_set=True)
    return _jwks


def verify_clerk_session_token(token: str) -> dict[str, Any]:
    jwks = _get_jwks()
    signing = jwks.get_signing_key_from_jwt(token)
    options: dict[str, bool] = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_iss": bool(CLERK_ISSUER),
        "verify_aud": bool(CLERK_JWT_AUDIENCE),
    }
    return jwt.decode(
        token,
        signing.key,
        algorithms=["RS256"],
        audience=CLERK_JWT_AUDIENCE,
        issuer=CLERK_ISSUER if CLERK_ISSUER else None,
        options=cast(Any, options),
    )


def build_http_exception(e: Exception) -> HTTPException:
    if isinstance(e, jwt.ExpiredSignatureError):
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
        )
    if isinstance(e, (jwt.PyJWTError, ValueError)):
        log.debug("JWT error: %s", e, exc_info=False)
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )


def require_clerk_session(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
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
        if not CLERK_JWKS_URL:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Clerk JWKS is not configured on the server",
            )
        return verify_clerk_session_token(creds.credentials)
    except HTTPException:
        raise
    except Exception as e:
        raise build_http_exception(e) from e


def get_optional_clerk_session(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_optional),
) -> dict[str, Any] | None:
    """If no `Authorization` header, return None. If Bearer token present, require valid Clerk JWT."""
    if creds is None or (creds.scheme or "").lower() != "bearer" or not creds.credentials:
        return None
    if not CLERK_JWKS_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk JWKS is not configured on the server",
        )
    try:
        return verify_clerk_session_token(creds.credentials)
    except Exception as e:
        raise build_http_exception(e) from e
