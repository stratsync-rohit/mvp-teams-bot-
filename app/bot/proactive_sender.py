"""
Proactive channel sender.

Sends an Adaptive Card into a specific Microsoft Teams team/channel using
the current Microsoft 365 Agents SDK ``CloudAdapter.create_conversation``
mechanism.

CRITICAL: teamId + channelId alone are not enough to reach a channel -
Teams requires a real, previously-captured ``serviceUrl`` (and tenantId)
for that channel, obtained from a Teams-sent conversationUpdate event
when this bot was installed. This module never fabricates that context;
if it isn't on file, it raises a clean error instead of silently sending
somewhere else (or failing in an unclear way).
"""

from __future__ import annotations

from typing import Any, Optional

from microsoft_agents.activity import (
    Activity,
    ActivityTypes,
    Channels,
    ConversationParameters,
)
from microsoft_agents.hosting.core import TurnContext

from app.bot.teams_bot import adapter
from app.cards.common import to_attachment
from app.config import get_settings
from app.services.conversation_service import conversation_service
from app.utils.logger import get_logger, log_event

logger = get_logger(__name__)

BOTFRAMEWORK_AUDIENCE = "https://api.botframework.com"


class ChannelNotRegisteredError(Exception):
    """
    Raised when there is no known Teams conversation reference for the
    requested teamId + channelId - i.e. the bot is not installed there,
    or no installation event has been received/stored yet.
    """


async def send_to_channel(team_id: str, channel_id: str, card: dict[str, Any]) -> str:
    """
    Sends an Adaptive Card as a new message into the given Teams channel.

    Returns the new Teams activity (message) ID.
    """
    reference = await conversation_service.get_reference(team_id, channel_id)
    if reference is None:
        raise ChannelNotRegisteredError(
            "Bot is not installed or channel conversation is not registered."
        )

    settings = get_settings()

    message_activity = Activity(
        type=ActivityTypes.message,
        attachments=[to_attachment(card)],
    )

    conversation_parameters = ConversationParameters(
        is_group=True,
        channel_data={"channel": {"id": channel_id}},
        activity=message_activity,
        tenant_id=reference.tenant_id or None,
    )

    new_activity_id: Optional[str] = None

    async def _capture_result(turn_context: TurnContext) -> None:
        nonlocal new_activity_id
        new_activity_id = turn_context.activity.id

    await adapter.create_conversation(
        agent_app_id=settings.MICROSOFT_APP_ID,
        channel_id=Channels.ms_teams,
        service_url=reference.service_url,
        audience=BOTFRAMEWORK_AUDIENCE,
        conversation_parameters=conversation_parameters,
        callback=_capture_result,
    )

    log_event(
        logger,
        "Sent Adaptive Card to Teams channel",
        team_id=team_id,
        channel_id=channel_id,
        message_id=new_activity_id,
    )

    return new_activity_id or ""
