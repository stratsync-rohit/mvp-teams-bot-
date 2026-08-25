"""Business operations for Teams installation and channel lifecycle events."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal

from app.config import get_settings
from app.utils.logger import get_logger, log_event
from app.utils.teams_context import (
    channel_metadata_diagnostic,
    extract_teams_context,
    has_authoritative_channel_conversation,
)

logger = get_logger(__name__)

InstallationRegistrar = Callable[[dict[str, Any]], Awaitable[str | bool]]
DiscoveryWriter = Callable[[dict[str, Any]], Awaitable[bool]]
DisconnectResult = Literal["disconnected", "not_found", "failed"]
InstallationDisconnector = Callable[..., Awaitable[DisconnectResult]]


async def register_installation(
    activity: Any,
    *,
    registrar: InstallationRegistrar,
) -> str | bool:
    """Persist a valid Team installation without breaking activity handling."""
    context = extract_teams_context(activity)
    diagnostic = channel_metadata_diagnostic(activity)
    if not (
        context["tenantId"]
        and context["teamId"]
        and context["conversationId"]
        and context["serviceUrl"]
    ):
        return False

    log_event(
        logger,
        "teams_channel_metadata_found" if context["channelName"] else "teams_channel_name_missing",
        tenant_id=context["tenantId"],
        team_id=context["teamId"],
        channel_id=context["channelId"],
        **diagnostic,
    )
    payload = {
        **context,
        "botAppId": get_settings().MICROSOFT_APP_ID,
        "enabled": True,
    }
    log_event(
        logger,
        "teams_installation_metadata_extracted",
        tenant_id=payload["tenantId"],
        team_id=payload["teamId"],
        channel_id=payload["channelId"],
        conversation_id=payload["conversationId"],
        has_channel_name=bool(payload["channelName"]),
        has_connected_by=bool(
            payload["connectedById"] or payload["connectedByAadObjectId"]
        ),
    )
    try:
        registered = await registrar(payload)
    except Exception as exc:  # noqa: BLE001 - isolate external lifecycle sync
        log_event(
            logger,
            "teams_installation_registration_failed",
            level=40,
            tenant_id=payload["tenantId"],
            team_id=payload["teamId"],
            channel_id=payload["channelId"],
            conversation_id=payload["conversationId"],
            error_type=type(exc).__name__,
        )
        return False
    if registered:
        log_event(
            logger,
            "teams_installation_registered",
            tenant_id=payload["tenantId"],
            team_id=payload["teamId"],
            conversation_id=payload["conversationId"],
        )
    return registered


async def discover_channel(
    activity: Any,
    *,
    writer: DiscoveryWriter,
    available: bool = True,
    explicit_event: bool = False,
    activity_context: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> bool:
    """Persist authoritative channel discovery without creating a destination."""
    activity_context = activity_context or extract_teams_context(activity)
    diagnostic = diagnostic or channel_metadata_diagnostic(activity)
    trustworthy = explicit_event or has_authoritative_channel_conversation(
        activity, context=activity_context, diagnostic=diagnostic
    )
    required = (
        activity_context["tenantId"],
        activity_context["teamId"],
        activity_context["channelId"],
        activity_context["channelName"],
        activity_context["serviceUrl"],
    )
    if not trustworthy or not all(required):
        return False

    payload = {
        "tenantId": activity_context["tenantId"],
        "teamId": activity_context["teamId"],
        "teamName": activity_context["teamName"],
        "aadGroupId": activity_context["aadGroupId"],
        "channelId": activity_context["channelId"],
        "channelName": activity_context["channelName"],
        "conversationId": activity_context["conversationId"],
        "serviceUrl": activity_context["serviceUrl"],
        "available": available,
    }
    try:
        return await writer(payload)
    except Exception as exc:  # noqa: BLE001 - isolate one discovery write
        log_event(
            logger,
            "teams_channel_discovery_persistence_failed",
            level=40,
            tenant_id=payload["tenantId"],
            team_id=payload["teamId"],
            channel_id=payload["channelId"],
            error_type=type(exc).__name__,
        )
        return False


async def disconnect_channel(
    activity: Any,
    *,
    disconnector: InstallationDisconnector,
) -> bool:
    """Disconnect only the exact authoritative channel in an activity."""
    context = extract_teams_context(activity)
    diagnostic = channel_metadata_diagnostic(activity)
    safe_context = {
        "tenant_id": context["tenantId"],
        "team_id": context["teamId"],
        "channel_id": context["channelId"],
        "conversation_id": context["conversationId"],
        **diagnostic,
    }
    if not (
        context["tenantId"]
        and context["teamId"]
        and context["channelId"]
        and (diagnostic["has_channel"] or diagnostic["conversation_type"] == "channel")
    ):
        return False
    log_event(logger, "teams_channel_disconnect_requested", **safe_context)
    result = await disconnector(
        context["tenantId"],
        team_id=context["teamId"],
        channel_id=context["channelId"],
        conversation_id=context["conversationId"],
        scope="channel",
    )
    return result in ("disconnected", "not_found")


async def disconnect_installation(
    activity: Any,
    *,
    disconnector: InstallationDisconnector,
) -> bool:
    """Forward a Teams-issued Team removal identity to the backend."""
    context = extract_teams_context(activity)
    safe_context = {
        "tenant_id": context["tenantId"],
        "team_id": context["teamId"],
        "channel_id": context["channelId"],
        "conversation_id": context["conversationId"],
    }
    log_event(logger, "teams_app_removal_received", **safe_context)
    if not context["tenantId"] or not (context["teamId"] or context["conversationId"]):
        log_event(
            logger,
            "teams_installation_disconnect_failed",
            level=30,
            error_type="TeamsContextMissing",
            **safe_context,
        )
        return False

    log_event(logger, "teams_installation_disconnect_requested", **safe_context)
    try:
        result = await disconnector(
            context["tenantId"],
            team_id=context["teamId"],
            conversation_id=context["conversationId"],
            scope="team",
        )
    except Exception as exc:  # noqa: BLE001 - isolate external lifecycle sync
        log_event(
            logger,
            "teams_installation_disconnect_failed",
            level=40,
            error_type=type(exc).__name__,
            **safe_context,
        )
        return False
    return result in ("disconnected", "not_found")
