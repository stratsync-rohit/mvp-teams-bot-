"""
Conversation service.

Captures real Teams-provided conversation context when the bot is
installed into a Team/channel (conversationUpdate activity) and looks it
up later when we need to proactively send a message to a specific
teamId + channelId.
"""

from __future__ import annotations

from typing import Optional

from microsoft_agents.activity import (
    Activity,
    ActivityTypes,
    ChannelAccount,
    Channels,
    ConversationParameters,
)
from microsoft_agents.hosting.core import TurnContext

from app.bot.teams_bot import adapter
from app.config import get_settings
from app.storage.conversation_store import (
    ChannelConversationReference,
    ConversationStore,
    conversation_store,
)
from app.utils.logger import get_logger, log_event
from app.utils.service_url import validate_service_url
from app.utils.teams_context import (
    extract_teams_context,
    has_authoritative_channel_conversation,
)

logger = get_logger(__name__)


class ConversationService:
    def __init__(self, store: ConversationStore | None = None) -> None:
        self._store = store or conversation_store

    async def capture_from_turn_context(self, turn_context: TurnContext) -> None:
        """
        Extracts tenantId, teamId, channelId, conversationId and serviceUrl
        from an incoming Teams activity (typically a conversationUpdate
        fired when the bot is added to a team) and persists it.

        Safe to call defensively on any Teams activity: if the required
        Teams channel data isn't present, this is a no-op.
        """
        context = extract_teams_context(turn_context.activity)
        team_id = context["teamId"]
        channel_id = context["channelId"]
        tenant_id = context["tenantId"]
        conversation_id = context["conversationId"]
        service_url = context["serviceUrl"]

        if not has_authoritative_channel_conversation(turn_context.activity):
            # Not enough Teams context to register a channel reference
            # (e.g. a 1:1 chat install event) - nothing to store.
            return

        reference = ChannelConversationReference(
            tenant_id=tenant_id or "",
            team_id=team_id,
            channel_id=channel_id,
            conversation_id=conversation_id,
            service_url=service_url,
        )
        await self._store.save(reference)

        log_event(
            logger,
            "teams_conversation_reference_captured",
            team_id=team_id,
            channel_id=channel_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )

    async def save_channel_context(self, context: dict) -> None:
        """Persist a validated, normalized channel route for proactive delivery."""
        reference = ChannelConversationReference(
            tenant_id=context["tenantId"],
            team_id=context["teamId"],
            channel_id=context["channelId"],
            conversation_id=context["destinationConversationId"],
            service_url=context["serviceUrl"],
        )
        await self._store.save(reference)
        log_event(
            logger,
            "teams_conversation_reference_captured",
            tenant_id=reference.tenant_id,
            team_id=reference.team_id,
            channel_id=reference.channel_id,
            conversation_id=reference.conversation_id,
        )

    async def get_reference(
        self, team_id: str, channel_id: str
    ) -> Optional[ChannelConversationReference]:
        return await self._store.get(team_id, channel_id)

    async def resolve_channel_conversation(
        self,
        *,
        tenant_id: str,
        team_id: str,
        channel_id: str,
        service_url: str,
    ) -> str:
        """Create a real Teams channel thread and return Microsoft's route ID."""
        service_url = validate_service_url(service_url)
        settings = get_settings()
        resolved_conversation_id: str | None = None

        async def capture_created_conversation(turn_context: TurnContext) -> None:
            nonlocal resolved_conversation_id
            conversation = getattr(turn_context.activity, "conversation", None)
            resolved_conversation_id = getattr(conversation, "id", None)

        parameters = ConversationParameters(
            is_group=True,
            agent=ChannelAccount(id=settings.MICROSOFT_APP_ID),
            tenant_id=tenant_id,
            channel_data={
                "tenant": {"id": tenant_id},
                "team": {"id": team_id},
                "channel": {"id": channel_id},
                "teamsTeamId": team_id,
                "teamsChannelId": channel_id,
            },
            activity=Activity(
                type=ActivityTypes.message,
                text="StratSync is ready to deliver risk notifications to this channel.",
            ),
        )
        await adapter.create_conversation(
            agent_app_id=settings.MICROSOFT_APP_ID,
            channel_id=Channels.ms_teams,
            service_url=service_url,
            audience="https://api.botframework.com/.default",
            conversation_parameters=parameters,
            callback=capture_created_conversation,
        )
        if not resolved_conversation_id:
            raise RuntimeError("Microsoft did not return a conversation ID")
        return resolved_conversation_id


conversation_service = ConversationService()
