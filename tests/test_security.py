import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import _safe_activity_log_fields
from app.utils.service_url import validate_service_url


@pytest.mark.parametrize(
    "url",
    [
        "https://smba.trafficmanager.net/emea/",
        "https://smba.trafficmanager.net/amer/",
        "https://example.botframework.com/v3/conversations",
    ],
)
def test_service_url_accepts_public_https_connector_hosts(url):
    assert validate_service_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://smba.trafficmanager.net/emea/",
        "https://localhost/",
        "https://127.0.0.1/",
        "https://10.0.0.8/",
        "https://192.168.1.10/",
        "https://[::1]/",
    ],
)
def test_service_url_rejects_insecure_or_local_targets(url):
    with pytest.raises(ValueError):
        validate_service_url(url)


def test_production_requires_internal_api_key():
    with pytest.raises(ValidationError, match="INTERNAL_API_KEY"):
        Settings(APP_ENV="production", INTERNAL_API_KEY="")
    assert Settings(APP_ENV="production", INTERNAL_API_KEY="configured").INTERNAL_API_KEY == "configured"


def test_safe_activity_metadata_excludes_raw_message_and_card_payload():
    body = {
        "id": "activity-1",
        "type": "message",
        "text": "secret message content",
        "value": {"action": {"data": {"secret": "card secret"}}},
        "channelData": {
            "eventType": "channelCreated",
            "tenant": {"id": "tenant-1"},
            "team": {"id": "team-1"},
            "channel": {"id": "channel-1", "name": "Risk Alerts"},
        },
        "conversation": {
            "id": "channel-1", "tenantId": "tenant-1",
            "conversationType": "channel",
        },
    }
    fields = _safe_activity_log_fields(body)
    assert fields == {
        "activity_type": "message", "event_type": "channelCreated",
        "activity_id": "activity-1", "tenant_id": "tenant-1",
        "team_id": "team-1", "channel_id": "channel-1",
        "conversation_id": "channel-1",
    }
    assert "secret" not in repr(fields)
