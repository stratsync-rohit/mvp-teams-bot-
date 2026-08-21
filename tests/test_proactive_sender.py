from types import SimpleNamespace

import pytest

from app.bot import proactive_sender
from app.services import conversation_service as conversation_service_module


@pytest.mark.asyncio
async def test_send_continues_supplied_conversation(monkeypatch):
    captured = {}

    class FakeTurnContext:
        async def send_activity(self, activity):
            captured["message"] = activity
            return SimpleNamespace(id="message-123")

    class FakeAdapter:
        async def continue_conversation(self, **kwargs):
            captured.update(kwargs)
            await kwargs["callback"](FakeTurnContext())

        async def create_conversation(self, **kwargs):
            raise AssertionError("create_conversation must not be used")

    monkeypatch.setattr(proactive_sender, "adapter", FakeAdapter())
    monkeypatch.setattr(
        proactive_sender,
        "get_settings",
        lambda: SimpleNamespace(MICROSOFT_APP_ID="bot-app-id"),
    )

    message_id = await proactive_sender.send_to_conversation(
        tenant_id="tenant-1",
        conversation_id="conversation-1",
        service_url="https://smba.trafficmanager.net/apac/",
        card={"type": "AdaptiveCard", "version": "1.5", "body": []},
    )

    continuation = captured["continuation_activity"]
    assert continuation.channel_id == "msteams"
    assert continuation.service_url == "https://smba.trafficmanager.net/apac/"
    assert continuation.conversation.id == "conversation-1"
    assert continuation.conversation.tenant_id == "tenant-1"
    assert captured["message"].type == "message"
    assert message_id == "message-123"


@pytest.mark.asyncio
async def test_send_continues_microsoft_resolved_conversation_id(monkeypatch):
    captured = {}

    class FakeTurnContext:
        async def send_activity(self, activity):
            return SimpleNamespace(id="message-456")

    class FakeAdapter:
        async def continue_conversation(self, **kwargs):
            captured.update(kwargs)
            await kwargs["callback"](FakeTurnContext())

    monkeypatch.setattr(proactive_sender, "adapter", FakeAdapter())
    monkeypatch.setattr(
        proactive_sender,
        "get_settings",
        lambda: SimpleNamespace(MICROSOFT_APP_ID="bot-app-id"),
    )
    await proactive_sender.send_to_conversation(
        tenant_id="tenant-1",
        team_id="team-1",
        channel_id="channel-r-test",
        conversation_id="microsoft-returned-thread-id",
        destination_id="destination-r-test",
        event_id="event-1",
        service_url="https://smba.trafficmanager.net/apac/",
        card={"type": "AdaptiveCard", "version": "1.5", "body": []},
    )
    assert captured["continuation_activity"].conversation.id == "microsoft-returned-thread-id"


@pytest.mark.asyncio
async def test_channel_conversation_resolution_uses_sdk_returned_id(monkeypatch):
    captured = {}

    class FakeAdapter:
        async def create_conversation(self, **kwargs):
            captured.update(kwargs)
            await kwargs["callback"](SimpleNamespace(
                activity=SimpleNamespace(
                    conversation=SimpleNamespace(id="microsoft-conversation-42")
                )
            ))

    monkeypatch.setattr(conversation_service_module, "adapter", FakeAdapter())
    monkeypatch.setattr(
        conversation_service_module,
        "get_settings",
        lambda: SimpleNamespace(MICROSOFT_APP_ID="bot-app-id"),
    )
    service = conversation_service_module.ConversationService()

    result = await service.resolve_channel_conversation(
        tenant_id="tenant-1", team_id="team-1", channel_id="channel-42",
        service_url="https://smba.trafficmanager.net/apac/",
    )

    assert result == "microsoft-conversation-42"
    assert captured["channel_id"] == "msteams"
    assert captured["service_url"] == "https://smba.trafficmanager.net/apac/"
    assert captured["audience"] == "https://api.botframework.com/.default"
    parameters = captured["conversation_parameters"]
    assert parameters.tenant_id == "tenant-1"
    assert parameters.channel_data == {
        "tenant": {"id": "tenant-1"},
        "team": {"id": "team-1"},
        "channel": {"id": "channel-42"},
        "teamsTeamId": "team-1",
        "teamsChannelId": "channel-42",
    }
    assert parameters.activity.type == "message"
