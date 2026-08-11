import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot import activity_handler
from app.storage.idempotency_store import IdempotencyStore


class FakeTurnContext:
    def __init__(self, activity):
        self.activity = activity
        self.sent = []

    async def send_activity(self, activity):
        self.sent.append(activity)


def adaptive_card_action(activity_id="invoke-1"):
    return SimpleNamespace(
        id=activity_id,
        name=activity_handler.ADAPTIVE_CARD_ACTION_NAME,
        value={
            "action": {
                "data": {"riskId": "RSK-1", "actionKey": "view_details"}
            }
        },
        channel_data={
            "tenant": {"id": "tenant-1"},
            "team": {"id": "team-1"},
        },
        conversation=SimpleNamespace(id="conversation-1", tenant_id="tenant-1"),
        service_url="https://smba.trafficmanager.net/apac/",
        from_property=SimpleNamespace(
            id="user-1", name="Jane Doe", aad_object_id="aad-1"
        ),
    )


def invoke_body(context):
    response = context.sent[0].value
    # This is the same object handed through the adapter to JSONResponse.
    json.dumps(response.body)
    return response.body


@pytest.mark.asyncio
async def test_adaptive_card_invoke_success_returns_json_serializable_body(monkeypatch):
    send_action = AsyncMock()
    monkeypatch.setattr(activity_handler.n8n_service, "send_action_event", send_action)
    monkeypatch.setattr(activity_handler, "idempotency_store", IdempotencyStore())
    context = FakeTurnContext(adaptive_card_action())

    await activity_handler.handle_invoke(context, SimpleNamespace())

    send_action.assert_awaited_once()
    assert invoke_body(context) == {
        "statusCode": 200,
        "type": "application/vnd.microsoft.activity.message",
        "value": {"message": "Got it - working on your request."},
    }


@pytest.mark.asyncio
async def test_duplicate_adaptive_card_invoke_returns_json_serializable_body(monkeypatch):
    send_action = AsyncMock()
    monkeypatch.setattr(activity_handler.n8n_service, "send_action_event", send_action)
    monkeypatch.setattr(activity_handler, "idempotency_store", IdempotencyStore())
    activity = adaptive_card_action()

    first_context = FakeTurnContext(activity)
    await activity_handler.handle_invoke(first_context, SimpleNamespace())
    duplicate_context = FakeTurnContext(activity)
    await activity_handler.handle_invoke(duplicate_context, SimpleNamespace())

    send_action.assert_awaited_once()
    assert invoke_body(duplicate_context) == {
        "statusCode": 200,
        "type": "application/vnd.microsoft.activity.message",
        "value": {"message": "Already processing this action."},
    }
