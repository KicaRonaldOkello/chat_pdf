"""Timezone-safe date helpers (daily usage buckets are pinned to UTC)."""

from __future__ import annotations

from datetime import UTC, date, datetime


def utc_today() -> date:
    """Today's date in UTC, independent of the container/server timezone."""
    return datetime.now(UTC).date()
