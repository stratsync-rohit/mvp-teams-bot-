from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.bot.activity_handler import _extract_destination
from app.schemas.actions import ActionActor, ActionDestination, RiskActionEvent
from app.schemas.notifications import ActionResultPayload, InitialNotificationPayload
from app.services.n8n_service import N8nActionWebhookError, N8nService

client = TestClient(app)

INITIAL_PAYLOAD = {
    "eventId": "evt-123",
    "eventType": "initial_notification",
    "riskId": "RSK-OP-0821",
    "destination": {
        "tenantId": "TENANT_ID",
        "teamId": "TEAM_ID",
        "channelId": None,
        "conversationId": "CONVERSATION_ID",
        "serviceUrl": "https://smba.trafficmanager.net/apac/",
    },
    "notification": {
        "riskId": "RSK-OP-0821",
        "title": "Owner funding is short",
        "status": "open",
        "entity": {"type": "sku", "id": "88421", "name": "Lavender Body Mist",
                   "data": {"anything": [1, 2]}},
        "severity": "high",
        "summary": "The owner needs to send US$210,000 more by 15 August 2026.",
        "metrics": [{"key": "stock", "label": "Available Stock", "value": False,
                     "data": {"source": "erp"}}],
    },
}

ACTION_RESULT_PAYLOAD = {
    "eventId": "evt-456",
    "eventType": "risk_action_result",
    "riskId": "RSK-OP-0821",
    "actionKey": "view_details",
    "destination": INITIAL_PAYLOAD["destination"],
    "result": {
        "success": True,
        "riskId": "RSK-OP-0821",
        "actionKey": "view_details",
        "cardType": "risk_details",
        "data": {},
    },
}


# ---------- Schema validation ----------


def test_initial_notification_payload_parses():
    payload = InitialNotificationPayload.model_validate(INITIAL_PAYLOAD)
    assert payload.risk_id == "RSK-OP-0821"
    assert payload.destination.team_id == "TEAM_ID"
    assert payload.destination.channel_id is None
    assert payload.destination.conversation_id == "CONVERSATION_ID"
    assert payload.notification.entity.type == "sku"
    assert payload.notification.metrics[0].value is False


def test_legacy_initial_notification_is_normalized():
    legacy = {**INITIAL_PAYLOAD, "notification": {
        "riskId": "RSK-OLD", "title": "Old", "severity": "high", "summary": "Legacy",
        "vessel": {"id": "V-1", "name": "Legacy Vessel"},
    }}
    payload = InitialNotificationPayload.model_validate(legacy)
    assert payload.notification.entity.type == "vessel"
    assert payload.notification.entity.name == "Legacy Vessel"


def test_initial_notification_payload_missing_destination_fails():
    bad = {k: v for k, v in INITIAL_PAYLOAD.items() if k != "destination"}
    with pytest.raises(ValidationError):
        InitialNotificationPayload.model_validate(bad)


@pytest.mark.parametrize("required_field", ["conversationId", "serviceUrl"])
def test_initial_notification_payload_missing_required_conversation_field_fails(
    required_field,
):
    bad = {
        **INITIAL_PAYLOAD,
        "destination": {
            key: value
            for key, value in INITIAL_PAYLOAD["destination"].items()
            if key != required_field
        },
    }
    with pytest.raises(ValidationError):
        InitialNotificationPayload.model_validate(bad)


def test_initial_notification_payload_channel_id_may_be_omitted():
    payload = InitialNotificationPayload.model_validate(
        {
            **INITIAL_PAYLOAD,
            "destination": {
                key: value
                for key, value in INITIAL_PAYLOAD["destination"].items()
                if key != "channelId"
            },
        }
    )
    assert payload.destination.channel_id is None


def test_action_result_payload_parses():
    payload = ActionResultPayload.model_validate(ACTION_RESULT_PAYLOAD)
    assert payload.action_key == "view_details"
    assert payload.result.card_type == "risk_details"
    assert payload.result.success is True
    assert payload.destination.channel_id is None


def test_action_result_payload_unknown_card_type_reaches_dispatcher():
    bad = {
        **ACTION_RESULT_PAYLOAD,
        "result": {**ACTION_RESULT_PAYLOAD["result"], "cardType": "not_a_real_type"},
    }
    payload = ActionResultPayload.model_validate(bad)
    assert payload.result.card_type == "not_a_real_type"


@pytest.mark.parametrize("required_field", ["actionKey", "result"])
def test_action_result_requires_envelope_fields(required_field):
    bad = {
        key: value
        for key, value in ACTION_RESULT_PAYLOAD.items()
        if key != required_field
    }
    with pytest.raises(ValidationError):
        ActionResultPayload.model_validate(bad)


def test_risk_action_event_wire_format():
    event = RiskActionEvent(
        eventId="evt-1",
        riskId="RSK-1",
        actionKey="view_details",
        destination=ActionDestination(
            tenantId="tenant-1",
            teamId="T1",
            channelId=None,
            conversationId="conversation-1",
            serviceUrl="https://smba.trafficmanager.net/apac/",
        ),
        actor=ActionActor(id="u1", name="Jane Doe", aadObjectId="aad-1"),
        payload={},
    )
    wire = event.to_wire_dict()
    assert wire["eventId"] == "evt-1"
    assert wire["riskId"] == "RSK-1"
    assert wire["actionKey"] == "view_details"
    assert wire["destination"] == {
        "tenantId": "tenant-1",
        "teamId": "T1",
        "channelId": None,
        "conversationId": "conversation-1",
        "serviceUrl": "https://smba.trafficmanager.net/apac/",
    }
    assert wire["actor"] == {"id": "u1", "name": "Jane Doe", "aadObjectId": "aad-1"}
    assert wire["payload"] == {}
    assert wire["actor"]["aadObjectId"] == "aad-1"


def test_action_destination_uses_current_activity_context_without_channel_id():
    activity = type("Activity", (), {})()
    activity.channel_data = {
        "tenant": {"id": "tenant-current"},
        "team": {"id": "team-current"},
    }
    activity.conversation = type(
        "Conversation", (), {"id": "conversation-current", "tenant_id": None}
    )()
    activity.service_url = "https://smba.trafficmanager.net/amer/"
    turn_context = type("TurnContext", (), {"activity": activity})()

    destination = _extract_destination(turn_context).model_dump(by_alias=True)

    assert destination == {
        "tenantId": "tenant-current",
        "teamId": "team-current",
        "channelId": None,
        "conversationId": "conversation-current",
        "serviceUrl": "https://smba.trafficmanager.net/amer/",
    }


# ---------- n8n service ----------


@pytest.mark.asyncio
async def test_n8n_service_success(monkeypatch):
    mock_response = httpx.Response(200, json={"ok": True})
    captured = {}

    async def fake_post(self, url, json=None, headers=None):
        captured.update({"url": url, "json": json, "headers": headers})
        return mock_response

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    service = N8nService()
    event = RiskActionEvent(
        eventId="evt-1",
        riskId="RSK-1",
        actionKey="view_details",
        destination=ActionDestination(
            tenantId="tenant-1",
            teamId="T1",
            channelId=None,
            conversationId="conversation-1",
            serviceUrl="https://smba.trafficmanager.net/apac/",
        ),
        actor=ActionActor(id="user-1", name="Jane Doe", aadObjectId="aad-1"),
        payload={},
    )
    await service.send_action_event(event)  # should not raise
    assert captured["json"] == {
        "eventId": "evt-1",
        "riskId": "RSK-1",
        "actionKey": "view_details",
        "destination": {
            "tenantId": "tenant-1",
            "teamId": "T1",
            "channelId": None,
            "conversationId": "conversation-1",
            "serviceUrl": "https://smba.trafficmanager.net/apac/",
        },
        "actor": {"id": "user-1", "name": "Jane Doe", "aadObjectId": "aad-1"},
        "payload": {},
    }


@pytest.mark.asyncio
async def test_n8n_service_non_2xx_raises(monkeypatch):
    mock_response = httpx.Response(500, json={"error": "boom"})

    async def fake_post(self, url, json=None, headers=None):
        return mock_response

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    service = N8nService()
    event = RiskActionEvent(
        eventId="evt-1",
        riskId="RSK-1",
        actionKey="view_details",
        destination=ActionDestination(
            tenantId="tenant-1",
            teamId="T1",
            channelId="C1",
            conversationId="conversation-1",
            serviceUrl="https://smba.trafficmanager.net/apac/",
        ),
        actor=ActionActor(),
        payload={},
    )
    with pytest.raises(N8nActionWebhookError):
        await service.send_action_event(event)


@pytest.mark.asyncio
async def test_n8n_service_network_failure_raises(monkeypatch):
    async def fake_post(self, url, json=None, headers=None):
        raise httpx.ConnectError("boom", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    service = N8nService()
    event = RiskActionEvent(
        eventId="evt-1",
        riskId="RSK-1",
        actionKey="view_details",
        destination=ActionDestination(
            tenantId="tenant-1",
            teamId="T1",
            channelId="C1",
            conversationId="conversation-1",
            serviceUrl="https://smba.trafficmanager.net/apac/",
        ),
        actor=ActionActor(),
        payload={},
    )
    with pytest.raises(N8nActionWebhookError):
        await service.send_action_event(event)


# ---------- POST /api/notifications (Teams sender mocked) ----------


def test_notifications_initial_success(monkeypatch):
    mock_send = AsyncMock(return_value="msg-123")
    monkeypatch.setattr(
        "app.services.notification_service.send_to_conversation", mock_send
    )

    response = client.post("/api/notifications", json=INITIAL_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["eventId"] == "evt-123"
    assert body["riskId"] == "RSK-OP-0821"
    mock_send.assert_awaited_once()
    assert mock_send.await_args.kwargs["conversation_id"] == "CONVERSATION_ID"
    assert mock_send.await_args.kwargs["service_url"].endswith("/apac/")
    assert "channel_id" not in mock_send.await_args.kwargs


def test_notifications_action_result_success(monkeypatch):
    mock_send = AsyncMock(return_value="msg-456")
    monkeypatch.setattr(
        "app.services.notification_service.send_to_conversation", mock_send
    )

    response = client.post("/api/notifications", json=ACTION_RESULT_PAYLOAD)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["eventId"] == "evt-456"
    mock_send.assert_awaited_once()


def test_notifications_missing_destination_returns_400():
    bad = {k: v for k, v in INITIAL_PAYLOAD.items() if k != "destination"}
    response = client.post("/api/notifications", json=bad)
    assert response.status_code == 400


@pytest.mark.parametrize("required_field", ["conversationId", "serviceUrl"])
def test_notifications_missing_required_conversation_field_returns_400(required_field):
    bad = {
        **INITIAL_PAYLOAD,
        "destination": {
            key: value
            for key, value in INITIAL_PAYLOAD["destination"].items()
            if key != required_field
        },
    }
    response = client.post("/api/notifications", json=bad)
    assert response.status_code == 400
    assert required_field in response.json()["detail"]


def test_notifications_unknown_card_type_returns_400():
    bad = {
        **ACTION_RESULT_PAYLOAD,
        "result": {**ACTION_RESULT_PAYLOAD["result"], "cardType": "not_a_real_type"},
    }
    response = client.post("/api/notifications", json=bad)
    assert response.status_code == 400


def test_notifications_channel_not_registered_returns_404(monkeypatch):
    from app.bot.proactive_sender import ChannelNotRegisteredError

    async def raise_not_registered(*args, **kwargs):
        raise ChannelNotRegisteredError(
            "Bot is not installed or channel conversation is not registered."
        )

    monkeypatch.setattr(
        "app.services.notification_service.send_to_conversation", raise_not_registered
    )

    response = client.post("/api/notifications", json=INITIAL_PAYLOAD)
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("error", "expected_status", "code", "retryable"),
    [
        (Exception("Conversation not found"), 410, "conversation_not_found", False),
        (TimeoutError("secret raw timeout"), 503, "network_error", True),
    ],
)
def test_notifications_normalizes_delivery_failures(
    monkeypatch, error, expected_status, code, retryable
):
    async def fail_send(*args, **kwargs):
        raise error

    monkeypatch.setattr(
        "app.services.notification_service.send_to_conversation", fail_send
    )
    payload = {
        **INITIAL_PAYLOAD,
        "destination": {**INITIAL_PAYLOAD["destination"], "destinationId": "opaque-123"},
    }
    response = client.post("/api/notifications", json=payload)
    assert response.status_code == expected_status
    detail = response.json()["detail"]
    assert detail == {
        "success": False,
        "errorType": "destination_unavailable" if not retryable else "delivery_failed",
        "errorCode": code,
        "destinationId": "opaque-123",
        "retryable": retryable,
    }
    assert "secret raw timeout" not in response.text


def test_notifications_internal_api_key_required(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("INTERNAL_API_KEY", "secret-key")
    get_settings.cache_clear()

    try:
        response = client.post("/api/notifications", json=INITIAL_PAYLOAD)
        assert response.status_code == 401

        response = client.post(
            "/api/notifications",
            json=INITIAL_PAYLOAD,
            headers={"X-Internal-API-Key": "wrong"},
        )
        assert response.status_code == 401
    finally:
        monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
        get_settings.cache_clear()
