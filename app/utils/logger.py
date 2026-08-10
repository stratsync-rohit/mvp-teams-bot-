"""
Logging configuration and helpers.

IMPORTANT: never log MICROSOFT_APP_PASSWORD, access tokens, Authorization
headers, INTERNAL_API_KEY, or the n8n webhook URL. Use ``log_event`` for
structured, safe-by-default logging of operational fields only.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Optional


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        stream=sys.stdout,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


_SAFE_FIELDS = (
    "event_id",
    "risk_id",
    "action_key",
    "team_id",
    "channel_id",
    "conversation_id",
    "tenant_id",
    "message_id",
    "operation",
    "result",
    "status",
    "correlation_id",
)


def log_event(
    logger: logging.Logger,
    message: str,
    *,
    level: int = logging.INFO,
    **fields: Optional[Any],
) -> None:
    """
    Log a message with a whitelist of operational fields appended. Any
    field not in ``_SAFE_FIELDS`` is dropped rather than risking an
    accidental credential/token leak into logs.
    """
    safe = {k: v for k, v in fields.items() if k in _SAFE_FIELDS and v is not None}
    if safe:
        suffix = " ".join(f"{k}={v}" for k, v in safe.items())
        logger.log(level, "%s | %s", message, suffix)
    else:
        logger.log(level, message)
