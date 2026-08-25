from types import SimpleNamespace

import pytest
from microsoft_agents.activity.teams import ChannelInfo

from app.bot import activity_handler
from app.services import backend_client, teams_channel_discovery


def installation_context(*, team_id="TEAM-1", team_name="Operations"):
    activity = SimpleNamespace(
        type="installationUpdate",
        action="add",
        channel_data={
            "tenant": {"id": "TENANT-1"},
            "team": {"id": team_id, "name": team_name},
            # Real Team-level installation shape: no authoritative channel.
            "channel": {"id": team_id},
        },
        conversation=SimpleNamespace(
            id=team_id, tenant_id="TENANT-1", conversation_type="channel"
        ),
        service_url="https://smba.example/",
        from_property=None,
    )
    return SimpleNamespace(activity=activity)


@pytest.mark.asyncio
async def test_sdk_enumeration_discovers_multiple_existing_channels(monkeypatch):
    captured = []
    context = installation_context()

    async def channels(turn_context, team_id):
        assert turn_context is context
        assert team_id == "TEAM-1"
        return [
            ChannelInfo(id="TEAM-1", name="General"),
            ChannelInfo(id="CHANNEL-2", name="Risk Alerts"),
            ChannelInfo(id="CHANNEL-3", name="Operations"),
        ]

    async def persist(payload):
        captured.append(payload)
        return True

    monkeypatch.setattr(
        teams_channel_discovery.TeamsInfo, "get_team_channels", channels
    )
    result = await teams_channel_discovery.enumerate_existing_team_channels(
        context, writer=persist
    )

    assert result == teams_channel_discovery.ChannelEnumerationResult(3, 3, 0)
    assert [item["channelId"] for item in captured] == [
        "TEAM-1", "CHANNEL-2", "CHANNEL-3"
    ]
    assert all(item["tenantId"] == "TENANT-1" for item in captured)
    assert all(item["teamId"] == "TEAM-1" for item in captured)
    assert all(item["teamName"] == "Operations" for item in captured)
    assert all(item["serviceUrl"] == "https://smba.example/" for item in captured)
    assert all(item["available"] is True for item in captured)


@pytest.mark.asyncio
async def test_general_equal_team_id_with_null_name_is_normalized(monkeypatch):
    captured = []

    async def channels(context, team_id):
        return [ChannelInfo(id=team_id, name=None)]

    async def persist(payload):
        captured.append(payload)
        return True

    monkeypatch.setattr(
        teams_channel_discovery.TeamsInfo, "get_team_channels", channels
    )
    result = await teams_channel_discovery.enumerate_existing_team_channels(
        installation_context(), writer=persist
    )

    assert result.discovered == 1
    assert captured[0]["channelId"] == "TEAM-1"
    assert captured[0]["channelName"] == "General"
    assert captured[0]["conversationId"] == "TEAM-1"


@pytest.mark.asyncio
async def test_unnamed_non_general_channel_is_not_faked(monkeypatch):
    writes = []

    async def channels(context, team_id):
        return [ChannelInfo(id="CHANNEL-2", name=None)]

    monkeypatch.setattr(
        teams_channel_discovery.TeamsInfo, "get_team_channels", channels
    )
    result = await teams_channel_discovery.enumerate_existing_team_channels(
        installation_context(), writer=lambda payload: writes.append(payload)
    )
    assert result == teams_channel_discovery.ChannelEnumerationResult(1, 0, 1)
    assert writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "channel",
    [ChannelInfo(id="   ", name="Risk Alerts"),
     ChannelInfo(id="CHANNEL-2", name="   ")],
    ids=["blank-id", "blank-name"],
)
async def test_whitespace_only_channel_fields_are_rejected(monkeypatch, channel):
    writes = []

    async def channels(context, team_id):
        return [channel]

    async def persist(payload):
        writes.append(payload)
        return True

    monkeypatch.setattr(
        teams_channel_discovery.TeamsInfo, "get_team_channels", channels
    )
    result = await teams_channel_discovery.enumerate_existing_team_channels(
        installation_context(), writer=persist
    )
    assert result == teams_channel_discovery.ChannelEnumerationResult(1, 0, 1)
    assert writes == []


@pytest.mark.asyncio
async def test_one_persistence_failure_does_not_stop_later_channels(monkeypatch):
    attempted = []

    async def channels(context, team_id):
        return [
            ChannelInfo(id="CHANNEL-1", name="One"),
            ChannelInfo(id="CHANNEL-2", name="Two"),
        ]

    async def persist(payload):
        attempted.append(payload["channelId"])
        if payload["channelId"] == "CHANNEL-1":
            raise RuntimeError("backend unavailable")
        return True

    monkeypatch.setattr(
        teams_channel_discovery.TeamsInfo, "get_team_channels", channels
    )
    result = await teams_channel_discovery.enumerate_existing_team_channels(
        installation_context(), writer=persist
    )
    assert attempted == ["CHANNEL-1", "CHANNEL-2"]
    assert result == teams_channel_discovery.ChannelEnumerationResult(2, 1, 1)


@pytest.mark.asyncio
async def test_installation_add_registers_then_enumerates(monkeypatch):
    calls = []

    async def register(activity):
        calls.append("register")
        return True

    async def enumerate_channels(context):
        calls.append("enumerate")

    monkeypatch.setattr(
        activity_handler, "register_installation_from_activity", register
    )
    monkeypatch.setattr(
        activity_handler, "enumerate_existing_team_channels", enumerate_channels
    )
    await activity_handler.handle_installation_update(
        installation_context(), SimpleNamespace()
    )
    assert calls == ["register", "enumerate"]


@pytest.mark.asyncio
async def test_failed_installation_is_not_enumerated(monkeypatch):
    async def register(activity):
        return False

    async def unexpected(context):
        raise AssertionError("untrusted installation must not enumerate")

    monkeypatch.setattr(
        activity_handler, "register_installation_from_activity", register
    )
    monkeypatch.setattr(
        activity_handler, "enumerate_existing_team_channels", unexpected
    )
    await activity_handler.handle_installation_update(
        installation_context(), SimpleNamespace()
    )


@pytest.mark.asyncio
async def test_enumeration_failure_does_not_fail_installation_or_write(monkeypatch):
    writes = []

    async def fail(context, team_id):
        raise RuntimeError("connector unavailable")

    monkeypatch.setattr(
        teams_channel_discovery.TeamsInfo, "get_team_channels", fail
    )
    result = await teams_channel_discovery.enumerate_existing_team_channels(
        installation_context(), writer=lambda payload: writes.append(payload)
    )
    assert result == teams_channel_discovery.ChannelEnumerationResult()
    assert writes == []


@pytest.mark.asyncio
async def test_unexpected_enumeration_failure_is_contained_by_install_handler(
    monkeypatch,
):
    calls = []

    async def register(activity):
        calls.append("registered")
        return True

    async def fail(context):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(
        activity_handler, "register_installation_from_activity", register
    )
    monkeypatch.setattr(
        activity_handler, "enumerate_existing_team_channels", fail
    )
    await activity_handler.handle_installation_update(
        installation_context(), SimpleNamespace()
    )
    assert calls == ["registered"]


@pytest.mark.asyncio
async def test_lifespan_backend_client_is_reused(monkeypatch):
    created = []

    class Response:
        def raise_for_status(self):
            return None

    class Client:
        def __init__(self, **kwargs):
            created.append(kwargs)

        async def post(self, *args, **kwargs):
            return Response()

        async def aclose(self):
            return None

    monkeypatch.setattr(backend_client.httpx, "AsyncClient", Client)
    backend_client.start_backend_http_client()
    try:
        payload = {
            "tenantId": "TENANT-1",
            "teamId": "TEAM-1",
            "channelId": "CHANNEL-1",
        }
        assert await backend_client.record_discovered_teams_channel(payload)
        assert await backend_client.record_discovered_teams_channel(payload)
        assert len(created) == 1
    finally:
        await backend_client.close_backend_http_client()
