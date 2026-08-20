"""Safe extraction of installation context from a Teams activity."""
from typing import Any


def _value(source: Any, name: str) -> Any:
    if source is None:
        return None
    return source.get(name) if isinstance(source, dict) else getattr(source, name, None)


def _first_value(source: Any, *names: str) -> Any:
    for name in names:
        value = _value(source, name)
        if value is not None:
            return value
    return None


def channel_metadata_diagnostic(activity: Any) -> dict[str, Any]:
    """Return only non-sensitive shape metadata suitable for structured logs."""
    channel_data = _first_value(activity, "channel_data", "channelData") or {}
    team = _value(channel_data, "team")
    channel = _value(channel_data, "channel")
    settings = _value(channel_data, "settings") or {}
    selected_channel = (
        _first_value(settings, "selected_channel", "selectedChannel")
        or _first_value(channel_data, "selected_channel", "selectedChannel")
    )
    conversation = _value(activity, "conversation")
    conversation_type = _first_value(
        conversation, "conversation_type", "conversationType"
    )
    channel_name = _value(channel, "name") or _value(selected_channel, "name")
    conversation_name = _value(conversation, "name")
    resolution_source = None
    if channel_name:
        resolution_source = "channelData.channel.name"
    elif (
        resolve_authoritative_channel(activity)[0]
        and conversation_type in (None, "channel")
        and conversation_name
    ):
        resolution_source = "conversation.name"

    return {
        "has_channel_data": bool(channel_data),
        "has_team": bool(team),
        "has_channel": bool(channel),
        "has_channel_name": bool(resolution_source),
        "conversation_type": conversation_type,
        "resolution_source": resolution_source,
        "event_type": _first_value(channel_data, "event_type", "eventType"),
        "channel_resolution_source": resolve_authoritative_channel(activity)[1],
    }


def resolve_authoritative_channel(activity: Any) -> tuple[Any, str | None]:
    """Resolve a channel only from Teams fields that explicitly identify one."""
    channel_data = _first_value(activity, "channel_data", "channelData") or {}
    channel = _value(channel_data, "channel")
    settings = _value(channel_data, "settings") or {}
    selected_in_settings = _first_value(settings, "selected_channel", "selectedChannel")
    selected_direct = _first_value(channel_data, "selected_channel", "selectedChannel")
    candidates = (
        (_value(channel, "id"), "channelData.channel.id"),
        (_first_value(channel_data, "teams_channel_id", "teamsChannelId"),
         "channelData.teamsChannelId"),
        (_value(selected_in_settings, "id"),
         "channelData.settings.selectedChannel.id"),
        (_value(selected_direct, "id"), "channelData.selectedChannel.id"),
    )
    return next(((value, source) for value, source in candidates if value), (None, None))


def has_authoritative_channel_conversation(activity: Any) -> bool:
    """True only for the channel identity shape proven by an incoming activity."""
    context = extract_teams_context(activity)
    diagnostic = channel_metadata_diagnostic(activity)
    return bool(
        context["tenantId"]
        and context["teamId"]
        and context["channelId"]
        and context["conversationId"]
        and context["serviceUrl"]
        and diagnostic["conversation_type"] == "channel"
        and context["conversationId"] == context["channelId"]
    )


def extract_teams_context(activity: Any) -> dict[str, Any]:
    channel_data = _first_value(activity, "channel_data", "channelData") or {}
    team = _value(channel_data, "team") or {}
    channel = _value(channel_data, "channel") or {}
    settings = _value(channel_data, "settings") or {}
    selected_channel = (
        _first_value(settings, "selected_channel", "selectedChannel")
        or _first_value(channel_data, "selected_channel", "selectedChannel")
        or {}
    )
    tenant = _value(channel_data, "tenant") or {}
    conversation = _value(activity, "conversation")
    actor = _value(activity, "from_property") or _value(activity, "from")
    conversation_type = _first_value(
        conversation, "conversation_type", "conversationType"
    )
    channel_id, channel_resolution_source = resolve_authoritative_channel(activity)
    channel_name = _value(channel, "name") or _value(selected_channel, "name")
    if not channel_name and channel_id and conversation_type in (None, "channel"):
        channel_name = _value(conversation, "name")

    return {
        "tenantId": _value(tenant, "id") or _first_value(
            conversation, "tenant_id", "tenantId"
        ),
        "teamId": _value(team, "id") or _first_value(
            channel_data, "teams_team_id", "teamsTeamId"
        ),
        "channelId": channel_id,
        "channelResolutionSource": channel_resolution_source,
        "conversationId": _value(conversation, "id"),
        "serviceUrl": _first_value(activity, "service_url", "serviceUrl"),
        "teamName": _value(team, "name"),
        "channelName": channel_name,
        # This is the actor attached to the lifecycle activity.  When Teams
        # supplies it, it represents the user who triggered this connection
        # event; it is not necessarily an administrator or account owner.
        "connectedByName": _value(actor, "name"),
        "connectedById": _value(actor, "id"),
        "connectedByAadObjectId": _value(actor, "aad_object_id")
        or _value(actor, "aadObjectId"),
    }
