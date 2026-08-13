"""Safe extraction of installation context from a Teams activity."""
from typing import Any


def _value(source: Any, name: str) -> Any:
    if source is None:
        return None
    return source.get(name) if isinstance(source, dict) else getattr(source, name, None)


def extract_teams_context(activity: Any) -> dict[str, Any]:
    channel_data = _value(activity, "channel_data") or _value(activity, "channelData") or {}
    team = _value(channel_data, "team") or {}
    channel = _value(channel_data, "channel") or {}
    tenant = _value(channel_data, "tenant") or {}
    conversation = _value(activity, "conversation")
    actor = _value(activity, "from_property") or _value(activity, "from")

    return {
        "tenantId": _value(tenant, "id") or _value(conversation, "tenant_id")
        or _value(conversation, "tenantId"),
        "teamId": _value(team, "id") or _value(channel_data, "teamsTeamId"),
        "channelId": _value(channel, "id") or _value(channel_data, "teamsChannelId"),
        "conversationId": _value(conversation, "id"),
        "serviceUrl": _value(activity, "service_url") or _value(activity, "serviceUrl"),
        "teamName": _value(team, "name"),
        "channelName": _value(channel, "name"),
        # This is the actor attached to the lifecycle activity.  When Teams
        # supplies it, it represents the user who triggered this connection
        # event; it is not necessarily an administrator or account owner.
        "connectedByName": _value(actor, "name"),
        "connectedById": _value(actor, "id"),
        "connectedByAadObjectId": _value(actor, "aad_object_id")
        or _value(actor, "aadObjectId"),
    }
