from types import SimpleNamespace

import pytest
import httpx

from app.bot import activity_handler
from app.services import backend_client
from app.utils.teams_context import extract_teams_context


def sample_activity(*, with_metadata=False, with_actor=False):
    channel_data = {"tenant": {"id": "tenant-1"}, "team": {"id": "team-1"}}
    if with_metadata:
        channel_data.update({
            "team": {"id": "team-1", "name": "Operations"},
            "channel": {"id": "channel-1", "name": "General"},
        })
    return SimpleNamespace(
        channel_data=channel_data,
        conversation=SimpleNamespace(id="conversation-1", tenant_id="tenant-1"),
        service_url="https://smba.trafficmanager.net/emea/",
        from_property=(
            SimpleNamespace(id="teams-user-1", name="Installation Actor", aad_object_id="aad-1")
            if with_actor else None
        ),
    )


def conversation_named_channel_activity():
    activity = sample_activity()
    activity.channel_data["channel"] = {"id": "channel-1"}
    activity.conversation = SimpleNamespace(
        id="conversation-1",
        tenant_id="tenant-1",
        conversation_type="channel",
        name="Risk Alerts",
    )
    return activity


def removal_activity(*, tenant_id="tenant-1", team_id="team-1", channel_id=None,
                     conversation_id="conversation-1"):
    channel_data = {"tenant": {"id": tenant_id}, "team": {"id": team_id}}
    if channel_id:
        channel_data["channel"] = {"id": channel_id}
    return SimpleNamespace(
        type="installationUpdate",
        action="remove",
        channel_data=channel_data,
        conversation=SimpleNamespace(id=conversation_id, tenant_id=tenant_id),
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
        "connectedByName": None,
        "connectedById": None,
        "connectedByAadObjectId": None,
    }


def test_extracts_real_team_channel_and_activity_actor():
    result = extract_teams_context(sample_activity(with_metadata=True, with_actor=True))
    assert result["teamName"] == "Operations"
    assert result["channelId"] == "channel-1"
    assert result["channelName"] == "General"
    assert result["connectedByName"] == "Installation Actor"
    assert result["connectedById"] == "teams-user-1"
    assert result["connectedByAadObjectId"] == "aad-1"


def test_extracts_channel_name_from_channel_conversation_fallback():
    result = extract_teams_context(conversation_named_channel_activity())
    assert result["channelId"] == "channel-1"
    assert result["conversationId"] == "conversation-1"
    assert result["channelName"] == "Risk Alerts"


def test_does_not_treat_non_channel_conversation_name_as_channel_name():
    activity = conversation_named_channel_activity()
    activity.conversation.conversation_type = "personal"
    activity.conversation.name = "Installation Actor"
    assert extract_teams_context(activity)["channelName"] is None


def test_existing_teams_fallback_ids_still_work():
    activity = sample_activity()
    activity.channel_data = {
        "tenant": {"id": "tenant-1"},
        "teamsTeamId": "fallback-team",
        "teamsChannelId": "fallback-channel",
    }
    result = extract_teams_context(activity)
    assert result["teamId"] == "fallback-team"
    assert result["channelId"] == "fallback-channel"
    assert result["channelName"] is None


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
async def test_registration_passes_optional_channel_and_actor_metadata(monkeypatch):
    captured = {}

    async def successful_registration(payload):
        captured.update(payload)
        return True

    monkeypatch.setattr(activity_handler, "register_teams_installation", successful_registration)
    assert await activity_handler.register_installation_from_activity(
        sample_activity(with_metadata=True, with_actor=True)
    ) is True
    assert captured["channelName"] == "General"
    assert captured["connectedByAadObjectId"] == "aad-1"
    assert "accountId" not in captured


@pytest.mark.asyncio
async def test_registration_uses_channel_conversation_name_without_route(monkeypatch):
    captured = {}

    async def successful_registration(payload):
        captured.update(payload)
        return True

    monkeypatch.setattr(activity_handler, "register_teams_installation", successful_registration)
    assert await activity_handler.register_installation_from_activity(
        conversation_named_channel_activity()
    ) is True
    assert captured["channelName"] == "Risk Alerts"
    assert "routeKey" not in captured
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


@pytest.mark.asyncio
async def test_removal_forwards_only_teams_context(monkeypatch):
    captured = {}

    async def disconnect(tenant_id, **kwargs):
        captured.update(tenant_id=tenant_id, **kwargs)
        return "disconnected"

    monkeypatch.setattr(activity_handler, "disconnect_teams_installation", disconnect)
    handled = await activity_handler.disconnect_installation_from_activity(
        removal_activity(tenant_id="TENANT-A", team_id="TEAM-A", conversation_id="CONV-A")
    )
    assert handled is True
    assert captured == {
        "tenant_id": "TENANT-A",
        "team_id": "TEAM-A",
        "channel_id": None,
        "conversation_id": "CONV-A",
        "scope": "team",
    }
    assert "accountId" not in captured
    assert "account_id" not in captured


@pytest.mark.asyncio
async def test_removal_without_team_uses_conversation(monkeypatch):
    captured = {}

    async def disconnect(tenant_id, **kwargs):
        captured.update(tenant_id=tenant_id, **kwargs)
        return "not_found"

    monkeypatch.setattr(activity_handler, "disconnect_teams_installation", disconnect)
    assert await activity_handler.disconnect_installation_from_activity(
        removal_activity(team_id=None)
    ) is True
    assert captured["team_id"] is None
    assert captured["scope"] == "team"
    assert captured["conversation_id"] == "conversation-1"


@pytest.mark.asyncio
async def test_removal_backend_failure_does_not_raise(monkeypatch):
    async def failed_disconnect(*args, **kwargs):
        raise RuntimeError("backend unavailable")

    monkeypatch.setattr(
        activity_handler, "disconnect_teams_installation", failed_disconnect
    )
    assert await activity_handler.disconnect_installation_from_activity(
        removal_activity()
    ) is False


@pytest.mark.asyncio
async def test_backend_disconnect_payload_and_internal_key(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "disconnected": True}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            captured.update(url=url, **kwargs)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        backend_client,
        "get_settings",
        lambda: SimpleNamespace(
            BACKEND_BASE_URL="https://backend.example",
            BACKEND_TIMEOUT_SECONDS=5,
            INTERNAL_API_KEY="test-internal-key",
        ),
    )
    result = await backend_client.disconnect_teams_installation(
        "TENANT-A", team_id="TEAM-A", conversation_id="CONV-A"
    )
    assert result == "disconnected"
    assert captured["url"].endswith("/api/teams/installations/disconnect")
    assert captured["json"] == {
        "tenantId": "TENANT-A",
        "teamId": "TEAM-A",
        "conversationId": "CONV-A",
        "scope": "team",
    }
    assert captured["headers"] == {"X-Internal-API-Key": "test-internal-key"}
    assert "accountId" not in captured["json"]


@pytest.mark.asyncio
async def test_channel_removal_forwards_explicit_channel_scope(monkeypatch):
    captured = {}

    async def disconnect(tenant_id, **kwargs):
        captured.update(tenant_id=tenant_id, **kwargs)
        return "disconnected"

    monkeypatch.setattr(activity_handler, "disconnect_teams_installation", disconnect)
    handled = await activity_handler.disconnect_installation_from_activity(
        removal_activity(team_id="TEAM-A", channel_id="CHANNEL-A")
    )
    assert handled is True
    assert captured["scope"] == "channel"
    assert captured["team_id"] == "TEAM-A"
    assert captured["channel_id"] == "CHANNEL-A"


@pytest.mark.asyncio
async def test_backend_disconnect_not_found_is_controlled(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "disconnected": False}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        backend_client,
        "get_settings",
        lambda: SimpleNamespace(
            BACKEND_BASE_URL="https://backend.example",
            BACKEND_TIMEOUT_SECONDS=5,
            INTERNAL_API_KEY="test-internal-key",
        ),
    )
    assert await backend_client.disconnect_teams_installation(
        "TENANT-A", conversation_id="CONV-A"
    ) == "not_found"


@pytest.mark.asyncio
async def test_backend_disconnect_requires_internal_key(monkeypatch):
    monkeypatch.setattr(
        backend_client,
        "get_settings",
        lambda: SimpleNamespace(INTERNAL_API_KEY=""),
    )
    assert await backend_client.disconnect_teams_installation(
        "TENANT-A", conversation_id="CONV-A"
    ) == "failed"


@pytest.mark.asyncio
async def test_installation_update_remove_uses_disconnect_flow(monkeypatch):
    captured = []

    async def disconnect(activity):
        captured.append(activity.action)
        return True

    monkeypatch.setattr(
        activity_handler, "disconnect_installation_from_activity", disconnect
    )
    context = SimpleNamespace(activity=removal_activity())
    await activity_handler.handle_installation_update(context, SimpleNamespace())
    assert captured == ["remove"]


@pytest.mark.asyncio
async def test_installation_update_add_reuses_registration_flow(monkeypatch):
    calls = []

    async def capture(context):
        calls.append("capture")

    async def register(activity):
        calls.append("register")
        return True

    monkeypatch.setattr(
        activity_handler.conversation_service, "capture_from_turn_context", capture
    )
    monkeypatch.setattr(activity_handler, "register_installation_from_activity", register)
    activity = removal_activity()
    activity.action = "add"
    context = SimpleNamespace(activity=activity)
    await activity_handler.handle_installation_update(context, SimpleNamespace())
    assert calls == ["capture", "register"]


@pytest.mark.asyncio
async def test_conversation_update_reuses_registration_flow(monkeypatch):
    calls = []

    async def capture(context):
        calls.append("capture")

    async def register(activity):
        calls.append("register")
        return True

    monkeypatch.setattr(activity_handler.conversation_service, "capture_from_turn_context", capture)
    monkeypatch.setattr(activity_handler, "register_installation_from_activity", register)
    await activity_handler.handle_conversation_update(
        SimpleNamespace(activity=sample_activity()), SimpleNamespace()
    )
    assert calls == ["capture", "register"]


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["installation", "conversation"])
async def test_lifecycle_registration_payload_includes_resolved_channel_name(
    monkeypatch, lifecycle
):
    captured = {}

    async def capture(context):
        return None

    async def register(payload):
        captured.update(payload)
        return True

    monkeypatch.setattr(
        activity_handler.conversation_service, "capture_from_turn_context", capture
    )
    monkeypatch.setattr(activity_handler, "register_teams_installation", register)
    monkeypatch.setattr(activity_handler, "register_teams_destination", register)
    activity = conversation_named_channel_activity()
    if lifecycle == "installation":
        activity.action = "add"
        await activity_handler.handle_installation_update(
            SimpleNamespace(activity=activity), SimpleNamespace()
        )
    else:
        await activity_handler.handle_conversation_update(
            SimpleNamespace(activity=activity), SimpleNamespace()
        )

    assert captured["channelName"] == "Risk Alerts"
    assert captured["channelId"] == "channel-1"
    assert captured["conversationId"] == "conversation-1"
    assert "accountId" not in captured
    assert "routeKey" not in captured


@pytest.mark.asyncio
async def test_sales_and_dev_channel_activities_register_separate_destinations(monkeypatch):
    captured = []

    async def register(payload):
        captured.append(payload)
        return True

    monkeypatch.setattr(activity_handler, "register_teams_destination", register)
    for channel_id, channel_name in (("SALES-ID", "Sales"), ("DEV-ID", "Dev")):
        activity = sample_activity(with_metadata=True)
        activity.channel_data["channel"] = {"id": channel_id, "name": channel_name}
        activity.conversation = SimpleNamespace(
            id=f"conversation-{channel_id}",
            tenant_id="tenant-1",
            conversation_type="channel",
            name=channel_name,
        )
        assert await activity_handler.capture_channel_destination_from_activity(activity)

    assert [item["channelId"] for item in captured] == ["SALES-ID", "DEV-ID"]
    assert [item["channelName"] for item in captured] == ["Sales", "Dev"]
    assert all("accountId" not in item for item in captured)


@pytest.mark.asyncio
async def test_same_channel_reregisters_and_missing_name_remains_null(monkeypatch):
    captured = []

    async def register(payload):
        captured.append(payload)
        return True

    monkeypatch.setattr(activity_handler, "register_teams_destination", register)
    activity = sample_activity(with_metadata=True)
    activity.channel_data["channel"] = {"id": "SALES-ID"}
    activity.conversation = SimpleNamespace(
        id="conversation-sales", tenant_id="tenant-1", conversation_type="channel"
    )
    assert await activity_handler.capture_channel_destination_from_activity(activity)
    assert await activity_handler.capture_channel_destination_from_activity(activity)
    assert len(captured) == 2
    assert captured[0]["channelName"] is None
    assert captured[0]["channelId"] == captured[1]["channelId"] == "SALES-ID"


@pytest.mark.asyncio
async def test_team_level_or_missing_channel_identity_is_not_registered(monkeypatch):
    async def unexpected(payload):
        raise AssertionError("team-level activity must not register a destination")

    monkeypatch.setattr(activity_handler, "register_teams_destination", unexpected)
    assert not await activity_handler.capture_channel_destination_from_activity(
        sample_activity()
    )
    activity = conversation_named_channel_activity()
    activity.channel_data.pop("channel")
    assert not await activity_handler.capture_channel_destination_from_activity(activity)


@pytest.mark.asyncio
async def test_backend_destination_client_uses_internal_endpoint(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            captured.update(url=url, **kwargs)
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient())
    monkeypatch.setattr(
        backend_client,
        "get_settings",
        lambda: SimpleNamespace(
            BACKEND_BASE_URL="https://backend.example",
            BACKEND_TIMEOUT_SECONDS=5,
            INTERNAL_API_KEY="internal-key",
        ),
    )
    payload = {
        "tenantId": "tenant-1", "teamId": "team-1", "channelId": "sales",
        "conversationId": "conversation-sales", "serviceUrl": "https://service/",
    }
    assert await backend_client.register_teams_destination(payload)
    assert captured["url"].endswith("/api/teams/channel-destinations")
    assert captured["json"] == payload
    assert captured["headers"] == {"X-Internal-API-Key": "internal-key"}


@pytest.mark.asyncio
@pytest.mark.parametrize("incoming_conversation", ["team-1", None])
async def test_verified_channel_normalizes_team_or_missing_conversation(
    monkeypatch, incoming_conversation, caplog
):
    captured = {}

    async def register(payload):
        captured.update(payload)
        return True

    monkeypatch.setattr(activity_handler, "register_teams_destination", register)
    activity = sample_activity(with_metadata=True)
    activity.channel_data["channel"] = {"id": "channel-1", "name": "r_test"}
    activity.conversation = SimpleNamespace(
        id=incoming_conversation,
        tenant_id="tenant-1",
        conversation_type="channel",
    )
    with caplog.at_level("WARNING"):
        assert await activity_handler.capture_channel_destination_from_activity(activity)
    assert captured["conversationId"] == captured["channelId"] == "channel-1"
    assert "teams_channel_conversation_normalized" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("conversation_type", ["personal", "groupChat", "meeting"])
async def test_non_channel_conversations_are_not_normalized_or_registered(
    monkeypatch, conversation_type
):
    async def unexpected(payload):
        raise AssertionError("non-channel activity must not register")

    monkeypatch.setattr(activity_handler, "register_teams_destination", unexpected)
    activity = sample_activity()
    activity.channel_data["teamsChannelId"] = "channel-1"
    activity.conversation = SimpleNamespace(
        id="team-1", tenant_id="tenant-1", conversation_type=conversation_type
    )
    assert not await activity_handler.capture_channel_destination_from_activity(activity)
