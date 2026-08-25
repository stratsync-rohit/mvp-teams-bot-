"""Validate and forward Adaptive Card actions independently of SDK routing."""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from microsoft_agents.activity import AdaptiveCardInvokeResponse, InvokeResponse

from app.schemas.actions import ActionActor, ActionDestination, RiskActionEvent
from app.services.n8n_service import N8nActionWebhookError, N8nService
from app.utils.logger import get_logger, log_event
from app.utils.teams_context import extract_teams_context

logger = get_logger(__name__)

ADAPTIVE_CARD_ACTION_NAME = "adaptiveCard/action"


class IdempotencyStore(Protocol):
    def seen_recently(self, key: str) -> bool: ...


def extract_destination(activity: Any) -> ActionDestination:
    """Build the action destination from the current authenticated activity."""
    context = extract_teams_context(activity)
    return ActionDestination(
        tenant_id=context["tenantId"],
        team_id=context["teamId"],
        channel_id=context["channelId"],
        conversation_id=context["conversationId"],
        service_url=context["serviceUrl"],
    )


def extract_actor(activity: Any) -> ActionActor:
    """Build the optional Teams actor without retaining the raw activity."""
    actor = getattr(activity, "from_property", None)
    if not actor:
        return ActionActor()
    return ActionActor(
        id=actor.id,
        name=actor.name,
        aad_object_id=actor.aad_object_id,
    )


def adaptive_card_response(**kwargs: Any) -> dict[str, Any]:
    """Return the JSON-ready body required by InvokeResponse in SDK 1.3.0."""
    return AdaptiveCardInvokeResponse(**kwargs).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )


async def process_invoke(
    activity: Any,
    *,
    n8n_service: N8nService,
    idempotency_store: IdempotencyStore,
) -> InvokeResponse:
    """Process one invoke activity and return its synchronous Teams response."""
    if activity.name != ADAPTIVE_CARD_ACTION_NAME:
        return InvokeResponse(status=200)

    action_value = activity.value or {}
    action = action_value.get("action") or {}
    data = action.get("data") or {}
    risk_id = data.get("riskId")
    action_key = data.get("actionKey")

    if not risk_id or not action_key:
        log_event(logger, "teams_adaptive_card_action_invalid", level=30)
        return InvokeResponse(
            status=200,
            body=adaptive_card_response(
                status_code=400,
                type="application/vnd.microsoft.error",
                value={"message": "Missing riskId or actionKey"},
            ),
        )

    idempotency_key = f"{activity.id}:{risk_id}:{action_key}"
    if idempotency_store.seen_recently(idempotency_key):
        log_event(
            logger,
            "teams_adaptive_card_action_duplicate",
            risk_id=risk_id,
            action_key=action_key,
        )
        return InvokeResponse(
            status=200,
            body=adaptive_card_response(
                status_code=200,
                type="application/vnd.microsoft.activity.message",
                value={"message": "Already processing this action."},
            ),
        )

    event = RiskActionEvent(
        event_id=str(uuid.uuid4()),
        risk_id=risk_id,
        action_key=action_key,
        destination=extract_destination(activity),
        actor=extract_actor(activity),
        payload={key: value for key, value in data.items() if key not in ("riskId", "actionKey")},
    )
    log_event(
        logger,
        "teams_adaptive_card_action_forwarding",
        event_id=event.event_id,
        risk_id=risk_id,
        action_key=action_key,
    )

    try:
        await n8n_service.send_action_event(event)
        response_value = "Got it - working on your request."
        status_code = 200
    except N8nActionWebhookError:
        response_value = "Sorry, we couldn't reach the automation service. Please try again."
        status_code = 502

    return InvokeResponse(
        status=200,
        body=adaptive_card_response(
            status_code=status_code,
            type="application/vnd.microsoft.activity.message",
            value={"message": response_value},
        ),
    )
