"""
Conversation service.

Captures real Teams-provided conversation context when the bot is
installed into a Team/channel (conversationUpdate activity) and looks it
up later when we need to proactively send a message to a specific
teamId + channelId.
"""

from __future__ import annotations

from typing import Optional

from microsoft_agents.hosting.core import TurnContext

from app.storage.conversation_store import (
    ChannelConversationReference,
    ConversationStore,
    conversation_store,
)
from app.utils.logger import get_logger, log_event
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
            "Captured Teams channel conversation reference",
            team_id=team_id,
            channel_id=channel_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )

    async def get_reference(
        self, team_id: str, channel_id: str
    ) -> Optional[ChannelConversationReference]:
        return await self._store.get(team_id, channel_id)


conversation_service = ConversationService()
