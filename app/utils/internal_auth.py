"""Authentication shared by internal FastAPI routes."""

from __future__ import annotations

import hmac

from fastapi import HTTPException, status

from app.config import get_settings


def verify_internal_api_key(provided_key: str | None) -> None:
    """Require the configured internal key using constant-time comparison."""
    expected_key = get_settings().INTERNAL_API_KEY
    if not expected_key:
        # Settings rejects this configuration in production. A blank key is
        # intentionally permissive only for local/development environments.
        return
    if not provided_key or not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-API-Key",
        )
