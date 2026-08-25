"""Send Adaptive Cards proactively to existing Teams conversations."""

from __future__ import annotations

from typing import Any

from microsoft_agents.activity import (
    Activity,
    ActivityTypes,
    ChannelAccount,
    Channels,
    ConversationAccount,
    ConversationReference,
)
from microsoft_agents.hosting.core import TurnContext

from app.bot.teams_bot import adapter
from app.cards.common import to_attachment
from app.config import get_settings
from app.utils.logger import get_logger, log_event
from app.utils.service_url import validate_service_url

logger = get_logger(__name__)

class ChannelNotRegisteredError(Exception):
    """Retained for API compatibility with existing route error handling."""


async def send_to_conversation(
    *,
    tenant_id: str,
    conversation_id: str,
    service_url: str,
    card: dict[str, Any],
    team_id: str | None = None,
    channel_id: str | None = None,
    event_id: str | None = None,
    destination_id: str | None = None,
) -> str:
    """Send a card into a Teams-provided conversation reference."""
    service_url = validate_service_url(service_url)
    settings = get_settings()
    message_activity = Activity(
        type=ActivityTypes.message,
        attachments=[to_attachment(card)],
    )
    reference = ConversationReference(
        # SDK 1.3.0 requires both accounts when materializing the continuation
        # activity. A channel continuation is routed by the conversation ID and
        # service URL, so the configured bot identity is sufficient here.
        agent=ChannelAccount(id=settings.MICROSOFT_APP_ID),
        user=ChannelAccount(id=settings.MICROSOFT_APP_ID),
        channel_id=Channels.ms_teams,
        service_url=service_url,
        conversation=ConversationAccount(
            id=conversation_id,
            tenant_id=tenant_id,
        ),
    )
    continuation_activity = reference.get_continuation_activity()
    new_activity_id: str | None = None

    async def _capture_result(turn_context: TurnContext) -> None:
        nonlocal new_activity_id
        response = await turn_context.send_activity(message_activity)
        new_activity_id = response.id if response else None

    await adapter.continue_conversation(
        agent_app_id=settings.MICROSOFT_APP_ID,
        continuation_activity=continuation_activity,
        callback=_capture_result,
    )

    log_event(
        logger,
        "teams_notification_sent",
        tenant_id=tenant_id,
        team_id=team_id,
        channel_id=channel_id,
        conversation_id=conversation_id,
        event_id=event_id,
        destination_id=destination_id,
        message_id=new_activity_id,
    )

    return new_activity_id or ""
