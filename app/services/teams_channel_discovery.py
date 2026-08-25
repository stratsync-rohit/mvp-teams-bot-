"""Discover existing Team channels through the supported Teams connector API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from microsoft_agents.hosting.core import TurnContext
from microsoft_agents.hosting.teams import TeamsInfo

from app.services.backend_client import record_discovered_teams_channel
from app.utils.logger import get_logger, log_event
from app.utils.teams_context import extract_teams_context

logger = get_logger(__name__)

DiscoveryWriter = Callable[[dict[str, Any]], Awaitable[bool]]


@dataclass(frozen=True)
class ChannelEnumerationResult:
    """Safe counters returned to callers and tests; no destination state exists here."""

    returned: int = 0
    discovered: int = 0
    failed: int = 0


def _value(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _error_status(exc: Exception) -> int | str | None:
    response = getattr(exc, "response", None)
    return (
        getattr(exc, "status_code", None)
        or getattr(exc, "status", None)
        or getattr(response, "status_code", None)
        or getattr(response, "status", None)
    )


async def enumerate_existing_team_channels(
    context: TurnContext,
    *,
    writer: DiscoveryWriter = record_discovered_teams_channel,
) -> ChannelEnumerationResult:
    """Enumerate and upsert current channels without creating destinations.

    ``TeamsInfo.get_team_channels`` is the Microsoft 365 Agents SDK 1.3.0
    wrapper over the Teams Bot Framework connector's
    ``v3/teams/{team_id}/conversations`` API. Failures are deliberately
    contained so installation and event-driven discovery keep working.
    """
    activity_context = extract_teams_context(context.activity)
    tenant_id = _clean_text(activity_context["tenantId"])
    team_id = _clean_text(activity_context["teamId"])
    service_url = _clean_text(activity_context["serviceUrl"])
    if not (tenant_id and team_id and service_url):
        return ChannelEnumerationResult()

    safe_context = {"tenant_id": tenant_id, "team_id": team_id}
    log_event(logger, "teams_channel_enumeration_started", **safe_context)
    try:
        channels = await TeamsInfo.get_team_channels(context, team_id)
    except Exception as exc:
        log_event(
            logger,
            "teams_channel_enumeration_failed",
            level=40,
            error_type=type(exc).__name__,
            status=_error_status(exc),
            **safe_context,
        )
        return ChannelEnumerationResult()

    if not isinstance(channels, (list, tuple)):
        log_event(
            logger, "teams_channel_enumeration_failed", level=40,
            error_type="MalformedChannelList", status=None, **safe_context,
        )
        return ChannelEnumerationResult()

    returned = len(channels)
    discovered = 0
    failed = 0
    for channel in channels:
        channel_id = _clean_text(_value(channel, "id"))
        channel_name = _clean_text(_value(channel, "name"))

        # The General channel is the one Teams channel for which the connector
        # may return the Team ID and omit the name. Equal IDs alone are valid
        # only in this connector enumeration response, not in arbitrary events.
        if channel_id == team_id and not channel_name:
            channel_name = "General"
        if not channel_id or not channel_name:
            failed += 1
            continue

        payload = {
            "tenantId": tenant_id,
            "teamId": team_id,
            "teamName": activity_context["teamName"],
            "aadGroupId": activity_context["aadGroupId"],
            "channelId": channel_id,
            "channelName": channel_name,
            # ChannelInfo is returned by the Teams connector's conversations
            # endpoint, so its canonical channel ID is also valid conversation
            # metadata. Explicit Connect still resolves the outbound route.
            "conversationId": channel_id,
            "serviceUrl": service_url,
            "available": True,
        }
        try:
            persisted = await writer(payload)
        except Exception as exc:
            persisted = False
            log_event(
                logger,
                "teams_existing_channel_discovery_failed",
                level=40,
                tenant_id=tenant_id,
                team_id=team_id,
                channel_id=channel_id,
                error_type=type(exc).__name__,
                status=_error_status(exc),
            )
        if persisted:
            discovered += 1
            log_event(
                logger,
                "teams_existing_channel_discovered",
                tenant_id=tenant_id,
                team_id=team_id,
                channel_id=channel_id,
            )
        else:
            failed += 1

    result = ChannelEnumerationResult(
        returned=returned, discovered=discovered, failed=failed
    )
    log_event(
        logger,
        "teams_channel_enumeration_completed",
        returned_count=result.returned,
        discovered_count=result.discovered,
        failed_count=result.failed,
        **safe_context,
    )
    return result
