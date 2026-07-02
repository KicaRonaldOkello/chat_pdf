"""Journey logging utility for tracking query processing through LangGraph nodes."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)


class JourneyLogger:
    """Logs journey events with timestamps for terminal and frontend streaming."""

    def __init__(self, node_name: str):
        self.node_name = node_name
        self.start_time = datetime.now()
        self.events: list[dict[str, Any]] = []

    def log_start(self, message: str = "") -> None:
        """Log node start with timestamp."""
        timestamp = datetime.now().isoformat()
        event = {
            "timestamp": timestamp,
            "node": self.node_name,
            "type": "start",
            "message": message,
        }
        self.events.append(event)
        log.info(f"[{self.node_name}] {message or 'Starting'}")

    def log_info(self, message: str) -> None:
        """Log info message with timestamp."""
        timestamp = datetime.now().isoformat()
        event = {
            "timestamp": timestamp,
            "node": self.node_name,
            "type": "info",
            "message": message,
        }
        self.events.append(event)
        log.info(f"[{self.node_name}] {message}")

    def log_debug(self, message: str) -> None:
        """Log debug message with timestamp."""
        timestamp = datetime.now().isoformat()
        event = {
            "timestamp": timestamp,
            "node": self.node_name,
            "type": "debug",
            "message": message,
        }
        self.events.append(event)
        log.debug(f"[{self.node_name}] {message}")

    def log_error(self, message: str, error: Exception | None = None) -> None:
        """Log error with timestamp and exception details."""
        timestamp = datetime.now().isoformat()
        event = {
            "timestamp": timestamp,
            "node": self.node_name,
            "type": "error",
            "message": message,
            "error": str(error) if error else None,
        }
        self.events.append(event)
        log.error(f"[{self.node_name}] {message}", exc_info=error is not None)

    def log_complete(self, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Log node completion with duration and return trace data."""
        duration_ms = int((datetime.now() - self.start_time).total_seconds() * 1000)
        timestamp = datetime.now().isoformat()
        event = {
            "timestamp": timestamp,
            "node": self.node_name,
            "type": "complete",
            "duration_ms": duration_ms,
            "data": data or {},
        }
        self.events.append(event)
        log.info(f"[{self.node_name}] Complete ({duration_ms}ms)")

        return {
            "node": self.node_name,
            "duration_ms": duration_ms,
            "events": self.events,
            "output": data or {},
        }
