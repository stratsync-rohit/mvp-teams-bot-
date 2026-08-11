from types import SimpleNamespace

import pytest

from app.bot import proactive_sender


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
