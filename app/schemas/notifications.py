"""
Pydantic v2 schemas for POST /api/notifications.

This endpoint is called exclusively by n8n and carries two kinds of
payloads, distinguished by ``eventType``:

  * ``initial_notification`` -> render + send the Initial Risk Adaptive Card
  * ``risk_action_result``   -> render + send a follow-up card (details,
    mitigation plan, tracking confirmation, assignment confirmation)

No business logic (risk scoring, MongoDB access, etc.) lives here or
anywhere else in this service - these models only describe the shape of
data handed to us by n8n so we can turn it into an Adaptive Card.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Destination(BaseModel):
    """Identifies the existing Microsoft Teams conversation to notify."""

    model_config = ConfigDict(populate_by_name=True)

    tenant_id: str = Field(alias="tenantId")
    team_id: str = Field(alias="teamId")
    channel_id: str | None = Field(default=None, alias="channelId")
    conversation_id: str = Field(alias="conversationId")
    service_url: str = Field(alias="serviceUrl")


class NotificationAction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    label: str


class Vessel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class InitialNotificationData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    risk_id: str = Field(alias="riskId")
    title: str
    vessel: Vessel
    severity: Severity
    summary: str
    deadline: Optional[date] = None
    actions: list[NotificationAction] = Field(default_factory=list)


class InitialNotificationPayload(BaseModel):
    """Top-level payload when eventType == 'initial_notification'."""

    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="eventId")
    event_type: Literal["initial_notification"] = Field(alias="eventType")
    risk_id: str = Field(alias="riskId")
    destination: Destination
    notification: InitialNotificationData


class ActionResultCardType(str, Enum):
    RISK_DETAILS = "risk_details"
    MITIGATION_PLAN = "mitigation_plan"
    TRACKING_CONFIRMATION = "tracking_confirmation"
    ASSIGNMENT_CONFIRMATION = "assignment_confirmation"


class ActionResult(BaseModel):
    """
    The rendered-card instructions n8n sends back after handling a button
    click. ``data`` is intentionally a free-form dict: its shape depends on
    ``card_type`` and is validated/rendered by the relevant card builder in
    app/cards, not here - this schema is just the routing envelope.
    """

    model_config = ConfigDict(populate_by_name=True)

    risk_id: str = Field(alias="riskId")
    action_key: str = Field(alias="actionKey")
    card_type: ActionResultCardType = Field(alias="cardType")
    data: dict[str, Any] = Field(default_factory=dict)


class ActionResultPayload(BaseModel):
    """Top-level payload when eventType == 'risk_action_result'."""

    model_config = ConfigDict(populate_by_name=True)

    event_id: str = Field(alias="eventId")
    event_type: Literal["risk_action_result"] = Field(alias="eventType")
    risk_id: str = Field(alias="riskId")
    action_key: str = Field(alias="actionKey")
    destination: Destination
    result: ActionResult


class NotificationResponse(BaseModel):
    """Response returned to n8n from POST /api/notifications."""

    model_config = ConfigDict(populate_by_name=True)

    success: bool
    event_id: str = Field(alias="eventId")
    risk_id: str = Field(alias="riskId")
    message: str
