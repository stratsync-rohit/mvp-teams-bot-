"""Small HTTP client for registering Teams installations with the backend."""
from typing import Any

import httpx

from app.config import get_settings
from app.utils.logger import get_logger, log_event

logger = get_logger(__name__)


async def register_teams_installation(payload: dict[str, Any]) -> bool:
    settings = get_settings()
    headers = {}
    if settings.INTERNAL_API_KEY:
        headers["X-Internal-API-Key"] = settings.INTERNAL_API_KEY

    url = f"{settings.BACKEND_BASE_URL.rstrip('/')}/api/teams/installations"
    try:
        async with httpx.AsyncClient(timeout=settings.BACKEND_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 409:
                log_event(
                    logger,
                    "teams_tenant_not_mapped",
                    level=30,
                    tenant_id=payload.get("tenantId"),
                    team_id=payload.get("teamId"),
                    conversation_id=payload.get("conversationId"),
                )
                return False
            response.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        log_event(
            logger,
            "Teams installation registration failed",
            level=40,
            tenant_id=payload.get("tenantId"),
            team_id=payload.get("teamId"),
            conversation_id=payload.get("conversationId"),
            error_type=type(exc).__name__,
        )
        return False
    return True
