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


def _safe_structural_metadata(value: Any) -> Any:
    """Serialize SDK metadata without introspecting arbitrary object state."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _safe_structural_metadata(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_structural_metadata(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _safe_structural_metadata(model_dump(mode="json", exclude_none=True))
    return {"runtimeType": type(value).__name__}


def installation_update_diagnostic(activity: Any) -> dict[str, Any]:
    """Return the complete known, non-secret installation metadata shape."""
    channel_data = _first_value(activity, "channel_data", "channelData") or {}
    team = _value(channel_data, "team") or {}
    channel = _value(channel_data, "channel") or {}
    settings = _value(channel_data, "settings") or {}
    selected_in_settings = _first_value(settings, "selected_channel", "selectedChannel") or {}
    selected_direct = _first_value(channel_data, "selected_channel", "selectedChannel") or {}
    conversation = _value(activity, "conversation") or {}
    tenant = _value(channel_data, "tenant") or {}
    return {
        "activity_type": _value(activity, "type"),
        "activity_action": _value(activity, "action"),
        "conversation_id": _value(conversation, "id"),
        "conversation_type": _first_value(
            conversation, "conversation_type", "conversationType"
        ),
        "channel_data_runtime_type": type(channel_data).__name__,
        "team_id": _value(team, "id"),
        "team_name": _value(team, "name"),
        "channel_id": _value(channel, "id"),
        "channel_name": _value(channel, "name"),
        "settings_runtime_type": type(settings).__name__,
        "channel_data_settings": _safe_structural_metadata(settings),
        "settings_selected_channel_id": _value(selected_in_settings, "id"),
        "settings_selected_channel_name": _value(selected_in_settings, "name"),
        "selected_channel_id": _value(selected_direct, "id"),
        "selected_channel_name": _value(selected_direct, "name"),
        "channel_data_selected_channel": _safe_structural_metadata(selected_direct),
        "tenant_id": _value(tenant, "id") or _first_value(
            conversation, "tenant_id", "tenantId"
        ),
    }


def extract_explicit_install_channel(
    activity: Any, *, context: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    """Extract a user-selected installation channel, never a Team-only route."""
    context = context or extract_teams_context(activity)
    channel_data = _first_value(activity, "channel_data", "channelData") or {}
    settings = _value(channel_data, "settings") or {}
    selected_in_settings = _first_value(settings, "selected_channel", "selectedChannel")
    selected_direct = _first_value(channel_data, "selected_channel", "selectedChannel")
    channel = _value(channel_data, "channel")
    team_id = context["teamId"]
    conversation_id = context["conversationId"]

    candidates = (
        (selected_in_settings, "channelData.settings.selectedChannel"),
        (selected_direct, "channelData.selectedChannel"),
        (channel, "channelData.channel"),
    )
    for candidate, source in candidates:
        channel_id = _value(candidate, "id")
        channel_name = _value(candidate, "name")
        if not channel_id or not channel_name:
            continue
        if channel_id == team_id and channel_name.strip().lower() != "general":
            continue
        return {
            **context,
            "channelId": channel_id,
            "channelName": channel_name,
            "channelResolutionSource": source,
            "explicitSelection": True,
        }

    # Microsoft's documented installation conversation is sufficient only when
    # it is demonstrably not the Team route and carries a real channel name.
    conversation = _value(activity, "conversation") or {}
    conversation_name = _value(conversation, "name")
    if conversation_id and conversation_id != team_id and conversation_name:
        return {
            **context,
            "channelId": conversation_id,
            "channelName": conversation_name,
            "channelResolutionSource": "installationUpdate.conversation.id",
            "explicitSelection": True,
        }
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
    channel_id, channel_resolution_source = resolve_authoritative_channel(activity)
    resolution_source = None
    if channel_name:
        resolution_source = "channelData.channel.name"
    elif (
        channel_id
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
        "channel_resolution_source": channel_resolution_source,
    }


def resolve_authoritative_channel(activity: Any) -> tuple[Any, str | None]:
    """Resolve a channel only from Teams fields that explicitly identify one."""
    channel_data = _first_value(activity, "channel_data", "channelData") or {}
    team = _value(channel_data, "team") or {}
    team_id = _value(team, "id") or _first_value(
        channel_data, "teams_team_id", "teamsTeamId"
    )
    channel = _value(channel_data, "channel")
    settings = _value(channel_data, "settings") or {}
    selected_in_settings = _first_value(settings, "selected_channel", "selectedChannel")
    selected_direct = _first_value(channel_data, "selected_channel", "selectedChannel")
    channel_id = _value(channel, "id")
    # Teams' General channel may legitimately share the Team ID, but a
    # Team-scoped lifecycle event can expose that same ID as incidental channel
    # data. Require an explicit channel name for this ambiguous equal-ID shape.
    explicit_channel_id = channel_id if (
        channel_id != team_id or _value(channel, "name")
    ) else None
    candidates = (
        (explicit_channel_id, "channelData.channel.id"),
        (_first_value(channel_data, "teams_channel_id", "teamsChannelId"),
         "channelData.teamsChannelId"),
        (_value(selected_in_settings, "id"),
         "channelData.settings.selectedChannel.id"),
        (_value(selected_direct, "id"), "channelData.selectedChannel.id"),
    )
    return next(
        (
            (value, source) for value, source in candidates
            if value and (value != team_id or source == "channelData.channel.id")
        ),
        (None, None),
    )


def has_authoritative_channel_conversation(
    activity: Any,
    *,
    context: dict[str, Any] | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> bool:
    """True only for the channel identity shape proven by an incoming activity."""
    context = context or extract_teams_context(activity)
    diagnostic = diagnostic or channel_metadata_diagnostic(activity)
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
        "aadGroupId": _first_value(team, "aad_group_id", "aadGroupId"),
        "channelName": channel_name,
        # This is the actor attached to the lifecycle activity.  When Teams
        # supplies it, it represents the user who triggered this connection
        # event; it is not necessarily an administrator or account owner.
        "connectedByName": _value(actor, "name"),
        "connectedById": _value(actor, "id"),
        "connectedByAadObjectId": _value(actor, "aad_object_id")
        or _value(actor, "aadObjectId"),
    }


def safe_activity_log_fields(activity: Any) -> dict[str, Any]:
    """Return an allowlisted activity envelope without message/card content."""
    context = extract_teams_context(activity)
    channel_data = _first_value(activity, "channel_data", "channelData") or {}
    return {
        "activity_type": _value(activity, "type"),
        "event_type": _first_value(channel_data, "event_type", "eventType"),
        "activity_id": _value(activity, "id"),
        "tenant_id": context["tenantId"],
        "team_id": context["teamId"],
        "channel_id": context["channelId"],
        "conversation_id": context["conversationId"],
    }


def activity_added_recipient(activity: Any) -> bool:
    """Return whether an activity says its recipient joined the channel."""
    recipient = _value(activity, "recipient")
    recipient_id = _value(recipient, "id")
    if not recipient_id:
        return False
    return any(
        _value(member, "id") == recipient_id
        for member in (_first_value(activity, "members_added", "membersAdded") or [])
    )


def conversation_update_diagnostic(activity: Any) -> dict[str, Any]:
    """Return non-secret structural diagnostics for conversation updates."""
    channel_data = _first_value(activity, "channel_data", "channelData") or {}
    channel = _value(channel_data, "channel") or {}
    team = _value(channel_data, "team") or {}
    conversation = _value(activity, "conversation")
    recipient = _value(activity, "recipient")
    members_added = _first_value(activity, "members_added", "membersAdded") or []
    return {
        "activity_type": _value(activity, "type"),
        "event_type": _first_value(channel_data, "event_type", "eventType"),
        "channel_data_runtime_type": type(channel_data).__name__,
        "conversation_id": _value(conversation, "id"),
        "conversation_type": _first_value(
            conversation, "conversation_type", "conversationType"
        ),
        "channel_id": _value(channel, "id"),
        "channel_name": _value(channel, "name"),
        "team_id": _value(team, "id"),
        "members_added_ids": [_value(member, "id") for member in members_added],
        "recipient_id": _value(recipient, "id"),
    }
