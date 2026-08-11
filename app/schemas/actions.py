"""
Pydantic v2 schemas describing the payload this bot POSTs to
``N8N_ACTION_WEBHOOK_URL`` whenever a user clicks an Adaptive Card button
(Action.Execute) inside Microsoft Teams.

riskId + actionKey are the single source of truth carried in the button;
we never stuff the full risk object into card button data.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ActionDestination(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    team_id: Optional[str] = Field(default=None, alias="teamId")
    channel_id: Optional[str] = Field(default=None, alias="channelId")
    conversation_id: str = Field(alias="conversationId")
    service_url: str = Field(alias="serviceUrl")


class ActionActor(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: Optional[str] = None
    name: Optional[str] = None
    aad_object_id: Optional[str] = Field(default=None, alias="aadObjectId")


class RiskActionEvent(BaseModel):
    """The event forwarded to n8n's Action Handler workflow."""

    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="eventId")
    risk_id: str = Field(alias="riskId")
    action_key: str = Field(alias="actionKey")
    destination: ActionDestination
    actor: ActionActor
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_wire_dict(self) -> dict[str, Any]:
        """Serialize using the camelCase wire format expected by n8n."""
        return self.model_dump(by_alias=True, mode="json")
