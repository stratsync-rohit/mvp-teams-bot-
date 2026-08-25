"""Small HTTP client for synchronizing Teams installations with the backend."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal

import httpx

from app.config import get_settings
from app.utils.logger import get_logger, log_event

logger = get_logger(__name__)

TeamsDisconnectResult = Literal["disconnected", "not_found", "failed"]
_shared_client: httpx.AsyncClient | None = None


def start_backend_http_client() -> None:
    """Create the process-wide backend client owned by the app lifespan."""
    global _shared_client
    if _shared_client is not None:
        return
    settings = get_settings()
    headers = (
        {"X-Internal-API-Key": settings.INTERNAL_API_KEY}
        if settings.INTERNAL_API_KEY
        else {}
    )
    _shared_client = httpx.AsyncClient(
        timeout=settings.BACKEND_TIMEOUT_SECONDS,
        headers=headers,
    )


async def close_backend_http_client() -> None:
    """Close and clear the lifespan-owned backend client."""
    global _shared_client
    if _shared_client is None:
        return
    client, _shared_client = _shared_client, None
    await client.aclose()


@asynccontextmanager
async def _backend_client() -> AsyncIterator[httpx.AsyncClient]:
    """Reuse the lifespan client, with an isolated fallback for unit callers."""
    if _shared_client is not None:
        yield _shared_client
        return
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.BACKEND_TIMEOUT_SECONDS) as client:
        yield client


@dataclass(frozen=True)
class DestinationRegistrationResult:
    success: bool
    status_code: int | None = None
    destination_id: str | None = None
    error: str | None = None
    enabled: bool | None = None
    disconnect_reason: str | None = None

    def __bool__(self) -> bool:
        return self.success


async def register_teams_installation(payload: dict[str, Any]) -> str | bool:
    settings = get_settings()
    headers = {}
    if settings.INTERNAL_API_KEY:
        headers["X-Internal-API-Key"] = settings.INTERNAL_API_KEY

    url = f"{settings.BACKEND_BASE_URL.rstrip('/')}/api/teams/installations"
    try:
        async with _backend_client() as client:
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
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log_event(
            logger,
            "teams_installation_registration_failed",
            level=40,
            tenant_id=payload.get("tenantId"),
            team_id=payload.get("teamId"),
            conversation_id=payload.get("conversationId"),
            error_type=type(exc).__name__,
        )
        return False
    return (body.get("installation") or {}).get("accountId") or True


async def register_teams_destination(
    payload: dict[str, Any],
) -> DestinationRegistrationResult:
    """Register one observed Teams channel without supplying an account ID."""
    settings = get_settings()
    headers = {}
    if settings.INTERNAL_API_KEY:
        headers["X-Internal-API-Key"] = settings.INTERNAL_API_KEY
    url = f"{settings.BACKEND_BASE_URL.rstrip('/')}/api/teams/channel-destinations"
    try:
        async with _backend_client() as client:
            response = await client.post(url, json=payload, headers=headers)
            log_event(
                logger,
                "teams_channel_destination_backend_response",
                status=response.status_code,
                tenant_id=payload.get("tenantId"),
                team_id=payload.get("teamId"),
                channel_id=payload.get("channelId"),
            )
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        log_event(
            logger,
            "teams_channel_destination_registration_failed",
            level=40,
            tenant_id=payload.get("tenantId"),
            team_id=payload.get("teamId"),
            channel_id=payload.get("channelId"),
            conversation_id=payload.get("conversationId"),
            status=status_code,
            error_type=type(exc).__name__,
        )
        return DestinationRegistrationResult(
            success=False,
            status_code=status_code,
            error=type(exc).__name__,
        )
    destination = body.get("destination") or {}
    destination_id = destination.get("destinationId")
    log_event(
        logger,
        "teams_channel_destination_backend_succeeded",
        status=response.status_code,
        destination_id=destination_id,
        tenant_id=payload.get("tenantId"),
        team_id=payload.get("teamId"),
        channel_id=payload.get("channelId"),
    )
    return DestinationRegistrationResult(
        success=True,
        status_code=response.status_code,
        destination_id=destination_id,
        enabled=destination.get("enabled"),
        disconnect_reason=destination.get("disconnectReason"),
    )


async def record_discovered_teams_channel(payload: dict[str, Any]) -> bool:
    """Persist discovery state without creating a notification destination."""
    settings = get_settings()
    headers = {"X-Internal-API-Key": settings.INTERNAL_API_KEY} if settings.INTERNAL_API_KEY else {}
    url = f"{settings.BACKEND_BASE_URL.rstrip('/')}/api/teams/channels/discover"
    try:
        async with _backend_client() as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
    except (httpx.HTTPError, ValueError) as exc:
        log_event(
            logger, "teams_channel_discovery_persistence_failed", level=40,
            tenant_id=payload.get("tenantId"), team_id=payload.get("teamId"),
            channel_id=payload.get("channelId"), error_type=type(exc).__name__,
        )
        return False
    return True


async def disconnect_teams_installation(
    tenant_id: str,
    *,
    team_id: str | None = None,
    channel_id: str | None = None,
    conversation_id: str | None = None,
    scope: Literal["team", "channel"] = "team",
) -> TeamsDisconnectResult:
    """Soft-disconnect one Teams installation through the backend lifecycle API."""
    settings = get_settings()
    safe_context = {
        "tenant_id": tenant_id,
        "team_id": team_id,
        "channel_id": channel_id,
        "conversation_id": conversation_id,
    }
    if not settings.INTERNAL_API_KEY:
        log_event(
            logger,
            "teams_installation_disconnect_failed",
            level=40,
            error_type="InternalApiKeyNotConfigured",
            **safe_context,
        )
        return "failed"

    payload = {"tenantId": tenant_id, "scope": scope}
    if team_id:
        payload["teamId"] = team_id
    if channel_id:
        payload["channelId"] = channel_id
    if conversation_id:
        payload["conversationId"] = conversation_id
    if (scope == "channel" and not (team_id and channel_id)) or (
        scope == "team" and not (team_id or conversation_id)
    ):
        log_event(
            logger,
            "teams_installation_disconnect_failed",
            level=30,
            error_type="InstallationIdentityMissing",
            **safe_context,
        )
        return "failed"

    url = f"{settings.BACKEND_BASE_URL.rstrip('/')}/api/teams/installations/disconnect"
    try:
        async with _backend_client() as client:
            response = await client.post(
                url,
                json=payload,
                headers={"X-Internal-API-Key": settings.INTERNAL_API_KEY},
            )
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log_event(
            logger,
            "teams_installation_disconnect_failed",
            level=40,
            error_type=type(exc).__name__,
            **safe_context,
        )
        return "failed"

    if body.get("disconnected") is False:
        log_event(
            logger,
            "teams_installation_disconnect_not_found",
            **safe_context,
        )
        return "not_found"

    log_event(
        logger,
        "teams_installation_disconnect_succeeded",
        **safe_context,
    )
    return "disconnected"
