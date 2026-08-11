from types import SimpleNamespace

import pytest
import httpx

from app.bot import activity_handler
from app.services import backend_client
from app.utils.teams_context import extract_teams_context


def sample_activity():
    return SimpleNamespace(
        channel_data={"tenant": {"id": "tenant-1"}, "team": {"id": "team-1"}},
        conversation=SimpleNamespace(id="conversation-1", tenant_id="tenant-1"),
        service_url="https://smba.trafficmanager.net/emea/",
    )


def test_extract_teams_context_uses_optional_values():
    result = extract_teams_context(sample_activity())
    assert result == {
        "tenantId": "tenant-1",
        "teamId": "team-1",
        "channelId": None,
        "conversationId": "conversation-1",
        "serviceUrl": "https://smba.trafficmanager.net/emea/",
        "teamName": None,
        "channelName": None,
    }


@pytest.mark.asyncio
async def test_registration_failure_does_not_raise(monkeypatch):
    async def failed_registration(payload):
        raise RuntimeError("backend unavailable")

    monkeypatch.setattr(activity_handler, "register_teams_installation", failed_registration)
    assert await activity_handler.register_installation_from_activity(sample_activity()) is False


@pytest.mark.asyncio
async def test_registration_payload_uses_tenant_without_account(monkeypatch):
    captured = {}

    async def successful_registration(payload):
        captured.update(payload)
        return True

    monkeypatch.setattr(
        activity_handler, "register_teams_installation", successful_registration
    )
    assert await activity_handler.register_installation_from_activity(sample_activity()) is True
    assert captured["tenantId"] == "tenant-1"
    assert "accountId" not in captured


@pytest.mark.asyncio
async def test_backend_unmapped_tenant_does_not_raise(monkeypatch):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return httpx.Response(409, request=httpx.Request("POST", args[0]))

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient())
    assert await backend_client.register_teams_installation({
        "tenantId": "tenant-1",
        "teamId": "team-1",
        "conversationId": "conversation-1",
    }) is False
