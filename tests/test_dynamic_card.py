from unittest.mock import AsyncMock
import logging

from fastapi.testclient import TestClient

from app.cards.dynamic_card import render_dynamic_card
from app.main import app
from app.schemas.notifications import ActionResult
from app.services.notification_service import render_action_result_card

client = TestClient(app)


def _payload(data: dict) -> dict:
    return {
        "eventId": "evt-dynamic",
        "eventType": "risk_action_result",
        "riskId": "RSK-88421-0318",
        "actionKey": "view_details",
        "destination": {
            "tenantId": "tenant-1",
            "teamId": "team-1",
            "channelId": None,
            "conversationId": "conversation-1",
            "serviceUrl": "https://smba.trafficmanager.net/apac/",
        },
        "result": {
            "success": True,
            "riskId": "RSK-88421-0318",
            "actionKey": "view_details",
            "cardType": "dynamic_card",
            "data": data,
        },
    }


def test_dynamic_card_is_accepted_and_channel_id_null_remains_supported(monkeypatch):
    mock_send = AsyncMock(return_value="message-1")
    monkeypatch.setattr("app.services.notification_service.send_to_conversation", mock_send)

    response = client.post("/api/notifications", json=_payload({"title": "Risk Details", "sections": []}))

    assert response.status_code == 200
    assert response.json()["success"] is True
    mock_send.assert_awaited_once()
    assert "channel_id" not in mock_send.await_args.kwargs


def test_all_known_sections_render_in_supplied_order():
    data = {
        "title": "Risk Details",
        "subtitle": "SKU 88421",
        "severity": "high",
        "entity": {"type": "sku", "id": "88421", "name": "Lavender Mist"},
        "sections": [
            {"type": "text", "title": "01 Text", "content": "Summary content"},
            {"type": "facts", "title": "02 Facts", "items": [{"label": "Exposure", "value": "$84,000"}]},
            {"type": "bullets", "title": "03 Bullets", "items": ["First impact"]},
            {"type": "steps", "title": "04 Steps", "items": [{"title": "Call supplier", "description": "Today", "owner": "Alex", "status": "open", "data": {"future": True}}]},
            {"type": "metrics", "title": "05 Metrics", "items": [{"label": "OTD", "value": "91%", "status": "critical"}]},
            {"type": "table", "title": "06 Table", "columns": ["Supplier", "OTD"], "rows": [["A1", "96%"], ["A2"]]},
            {"type": "callout", "title": "07 Callout", "content": "Proceed with A1"},
        ],
    }

    card = render_dynamic_card(data)
    rendered = str(card["body"])

    assert card["type"] == "AdaptiveCard"
    assert card["msteams"]["width"] == "Full"
    for value in ("Summary content", "$84,000", "First impact", "Call supplier", "Alex", "91%", "A1", "Proceed with A1"):
        assert value in rendered
    positions = [rendered.index(f"0{number} ") for number in range(1, 8)]
    assert positions == sorted(positions)


def test_header_supports_arbitrary_entity_type():
    rendered = str(render_dynamic_card({"title": "Invoice risk", "entity": {"type": "invoice", "id": "INV-7", "name": "August invoice"}, "sections": []})["body"])
    assert "invoice" in rendered
    assert "INV-7" in rendered
    assert "August invoice" in rendered
    assert "Vessel" not in rendered


def test_empty_sections_and_missing_optional_fields_render_valid_card():
    card = render_dynamic_card({"sections": []})
    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.5"
    assert card["body"]

    sparse = render_dynamic_card({"sections": [{"type": kind} for kind in ("text", "facts", "bullets", "steps", "metrics", "table", "callout")]})
    assert sparse["type"] == "AdaptiveCard"


def test_unknown_future_section_does_not_crash_and_following_section_renders(caplog):
    caplog.set_level(logging.INFO, logger="app.cards.dynamic_card")
    card = render_dynamic_card(
        {
            "riskId": "RSK-7",
            "sections": [
                {"type": "timeline", "title": "Future timeline", "events": [{"at": "now"}]},
                {"type": "text", "title": "Still rendered", "content": "After fallback"},
            ],
        }
    )
    rendered = str(card["body"])
    assert "Future timeline" in rendered and "events" in rendered
    assert "Still rendered" in rendered and "After fallback" in rendered
    assert "unsupported_dynamic_section_type" in caplog.text
    assert "RSK-7" in caplog.text


def test_legacy_action_result_renderers_remain_available():
    for card_type, expected in (("risk_details", "Legacy details"), ("mitigation_plan", "Mitigation Plan")):
        result = ActionResult.model_validate(
            {
                "success": True,
                "riskId": "RSK-legacy",
                "actionKey": "test",
                "cardType": card_type,
                "data": {"title": "Legacy details"},
            }
        )
        assert expected in str(render_action_result_card(result))
