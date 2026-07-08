"""Session token helpers: blacklist checks, audit logging, fingerprint."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy import text

from app.runtime import get_db_session_maker

log = logging.getLogger(__name__)


def make_fingerprint(user_agent: str = "", ip_address: str = "") -> str:
    raw = f"{user_agent}|{ip_address}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


async def is_token_revoked(jti: str) -> bool:
    sm = get_db_session_maker()
    if sm is None:
        return False
    async with sm() as session:
        result = await session.execute(
            text("SELECT 1 FROM token_blacklist WHERE jti = :jti"),
            {"jti": jti},
        )
        return result.scalar() is not None


async def revoke_token(jti: str, user_id: str) -> None:
    from datetime import datetime, timezone as tz

    sm = get_db_session_maker()
    if sm is None:
        return
    async with sm() as session:
        await session.execute(
            text(
                "INSERT INTO token_blacklist (jti, user_id, expires_at, revoked_at) "
                "VALUES (:jti, :user_id, :exp, :now) "
                "ON CONFLICT (jti) DO NOTHING"
            ),
            {
                "jti": jti,
                "user_id": user_id,
                "exp": datetime.now(tz.utc),
                "now": datetime.now(tz.utc),
            },
        )
        await session.commit()


async def log_auth_event(
    user_id: str,
    event_type: str,
    ip_address: str = "",
    user_agent: str = "",
) -> None:
    sm = get_db_session_maker()
    if sm is None:
        return
    async with sm() as session:
        await session.execute(
            text(
                "INSERT INTO auth_events (user_id, event_type, ip_address, user_agent) "
                "VALUES (:uid, :type, :ip, :ua)"
            ),
            {"uid": user_id, "type": event_type, "ip": ip_address or "", "ua": user_agent or ""},
        )
        await session.commit()
