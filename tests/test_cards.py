from app.cards.common import format_currency, format_display_date
from app.cards.initial_risk_card import build_initial_risk_card
from app.cards.mitigation_plan_card import build_mitigation_plan_card
from app.cards.risk_details_card import build_risk_details_card
from app.schemas.notifications import InitialNotificationData


def _sample_notification() -> InitialNotificationData:
    return InitialNotificationData.model_validate(
        {
            "riskId": "RSK-OP-0821",
            "title": "Owner funding is short",
            "vessel": {"id": "V-OP-2417", "name": "MV Ocean Pioneer"},
            "severity": "high",
            "summary": "The owner needs to send US$210,000 more by 15 August 2026.",
            "deadline": "2026-08-15",
            "actions": [
                {"key": "view_details", "label": "View Details"},
                {"key": "mitigation_plan", "label": "Mitigation Plan"},
                {"key": "assign", "label": "Assign To"},
                {"key": "track_risk", "label": "Track This Problem"},
            ],
        }
    )


def test_format_currency():
    assert format_currency(210000, "USD") == "US$210,000"
    assert format_currency(1500.5, "EUR") == "€1,500.50"
    assert format_currency(100, "XYZ") == "XYZ 100"


def test_format_display_date():
    assert format_display_date("2026-08-15") == "15 Aug 2026"
    assert format_display_date(None) == "-"


def test_build_initial_risk_card_structure():
    card = build_initial_risk_card(_sample_notification())

    assert card["type"] == "AdaptiveCard"
    assert card["version"] == "1.5"
    assert len(card["actions"]) == 4

    action_keys = {a["data"]["actionKey"] for a in card["actions"]}
    assert action_keys == {"view_details", "mitigation_plan", "assign", "track_risk"}

    for action in card["actions"]:
        assert action["type"] == "Action.Execute"
        assert action["verb"] == "risk_action"
        assert action["data"]["riskId"] == "RSK-OP-0821"
        # riskId + actionKey only - no full risk object in button data
        assert set(action["data"].keys()) == {"riskId", "actionKey"}

    body_text = str(card["body"])
    assert "Owner funding is short" in body_text
    assert "V-OP-2417" in body_text
    assert "MV Ocean Pioneer" in body_text
    assert "RSK-OP-0821" in body_text


def test_build_risk_details_card():
    data = {
        "riskId": "RSK-OP-0821",
        "title": "Owner funding is short",
        "fundingShortfall": 210000,
        "paymentsAtRisk": 210000,
        "deadline": "2026-08-15",
        "accountRisk": "High",
        "underlyingExposure": ["Exposure A", "Exposure B"],
        "impact": ["Impact A"],
    }

    card = build_risk_details_card(data)

    assert card["type"] == "AdaptiveCard"
    body_text = str(card["body"])
    assert "US$210,000" in body_text
    assert "15 Aug 2026" in body_text
    assert "Exposure A" in body_text
    assert "Impact A" in body_text
    assert "RSK-OP-0821" in body_text


def test_build_mitigation_plan_card():
    data = {
        "riskId": "RSK-OP-0821",
        "title": "Owner funding is short",
        "summary": "Secure additional funding and prioritise critical payments.",
        "steps": [
            {
                "step": 1,
                "title": "Check the 30-day cash need",
                "description": "Calculate all critical cash requirements.",
                "owner": "Fleet Finance Manager",
                "status": "pending",
            }
        ],
    }

    card = build_mitigation_plan_card(data)

    body_text = str(card["body"])
    assert "Mitigation Plan" in body_text
    assert "Check the 30-day cash need" in body_text
    assert "Fleet Finance Manager" in body_text
    assert "RSK-OP-0821" in body_text
