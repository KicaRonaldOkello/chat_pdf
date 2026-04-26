"""Clerk JWT claim helpers (not persisted here)."""

from __future__ import annotations

from typing import Any


def email_from_claims(claims: dict[str, Any]) -> str | None:
    e = claims.get("email")
    if isinstance(e, str) and e.strip():
        return e.strip()
    e2 = claims.get("https://clerk.com/primary_email")
    if isinstance(e2, str) and e2.strip():
        return e2.strip()
    return None
