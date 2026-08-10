"""
Conversation/channel reference storage.

Microsoft Teams requires real, Teams-provided conversation context
(tenantId, teamId, channelId, conversationId, serviceUrl) before this bot
can proactively post into a channel - none of that can be fabricated from
teamId + channelId alone.

This module defines a small storage protocol plus an in-memory
implementation suitable for V1/local development and tests. Swap
``InMemoryConversationStore`` for a Mongo/Redis-backed implementation later
without changing any calling code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChannelConversationReference:
    """Real Teams conversation context captured from a conversation-update event."""

    tenant_id: str
    team_id: str
    channel_id: str
    conversation_id: str
    service_url: str

    def key(self) -> str:
        return ConversationStore.make_key(self.team_id, self.channel_id)


class ConversationStore(ABC):
    """Abstract interface for storing Teams channel conversation references."""

    @staticmethod
    def make_key(team_id: str, channel_id: str) -> str:
        return f"{team_id}:{channel_id}"

    @abstractmethod
    async def save(self, reference: ChannelConversationReference) -> None: ...

    @abstractmethod
    async def get(
        self, team_id: str, channel_id: str
    ) -> Optional[ChannelConversationReference]: ...

    @abstractmethod
    async def delete(self, team_id: str, channel_id: str) -> None: ...


class InMemoryConversationStore(ConversationStore):
    """
    V1 in-memory store. Not persisted across process restarts - acceptable
    for local development/testing. Swap for a database-backed
    ConversationStore implementation for production.
    """

    def __init__(self) -> None:
        self._store: dict[str, ChannelConversationReference] = {}

    async def save(self, reference: ChannelConversationReference) -> None:
        self._store[reference.key()] = reference

    async def get(
        self, team_id: str, channel_id: str
    ) -> Optional[ChannelConversationReference]:
        return self._store.get(self.make_key(team_id, channel_id))

    async def delete(self, team_id: str, channel_id: str) -> None:
        self._store.pop(self.make_key(team_id, channel_id), None)


# Process-wide singleton used by the FastAPI app. Replace with a
# dependency-injected database-backed store when moving beyond V1.
conversation_store = InMemoryConversationStore()
