"""
AgentApplication route registration.

Two responsibilities live here:

  1. conversationUpdate handling - captures real Teams conversation
     context (tenantId, teamId, channelId, conversationId, serviceUrl)
     whenever the bot is installed/added to a Team or channel, so we can
     proactively message that channel later and registers it with the backend.

  2. Adaptive Card action handling - Teams delivers Action.Execute button
     clicks as an ``invoke`` activity named ``adaptiveCard/action``. We
     extract riskId + actionKey + actor + conversation info and forward
     them to the n8n Action Handler webhook. We do NOT call the backend or
     MongoDB directly - n8n owns that orchestration.
"""

from __future__ import annotations

import uuid

from microsoft_agents.activity import (
    ActivityTypes,
    AdaptiveCardInvokeResponse,
    InvokeResponse,
)
from microsoft_agents.hosting.core import TurnContext, TurnState

from app.bot.teams_bot import agent_app
from app.schemas.actions import ActionActor, ActionDestination, RiskActionEvent
from app.services.conversation_service import conversation_service
from app.services.backend_client import register_teams_installation
from app.config import get_settings
from app.services.n8n_service import N8nActionWebhookError, N8nService
from app.storage.idempotency_store import idempotency_store
from app.utils.logger import get_logger, log_event
from app.utils.teams_context import extract_teams_context

logger = get_logger(__name__)

n8n_service = N8nService()

ADAPTIVE_CARD_ACTION_NAME = "adaptiveCard/action"


async def register_installation_from_activity(activity) -> bool:
    """Register a valid Team-scoped activity without disrupting its processing."""
    context = extract_teams_context(activity)
    if not (
        context["tenantId"]
        and context["teamId"]
        and context["conversationId"]
        and context["serviceUrl"]
    ):
        return False

    settings = get_settings()
    payload = {
        **context,
        "botAppId": settings.MICROSOFT_APP_ID,
        "enabled": True,
    }
    log_event(
        logger,
        "teams_installation_received",
        tenant_id=payload["tenantId"],
        team_id=payload["teamId"],
        conversation_id=payload["conversationId"],
    )
    try:
        registered = await register_teams_installation(payload)
    except Exception as exc:  # registration must never break Teams activity handling
        log_event(
            logger,
            "teams_installation_registration_failed",
            level=40,
            tenant_id=payload["tenantId"],
            team_id=payload["teamId"],
            conversation_id=payload["conversationId"],
            error_type=type(exc).__name__,
        )
        return False
    if registered:
        log_event(
            logger,
            "teams_installation_registered",
            tenant_id=payload["tenantId"],
            team_id=payload["teamId"],
            conversation_id=payload["conversationId"],
        )
    return registered


def _extract_destination(turn_context: TurnContext) -> ActionDestination:
    context = extract_teams_context(turn_context.activity)
    return ActionDestination(
        tenant_id=context["tenantId"],
        team_id=context["teamId"],
        channel_id=context["channelId"],
        conversation_id=context["conversationId"],
        service_url=context["serviceUrl"],
    )


def _extract_actor(turn_context: TurnContext) -> ActionActor:
    from_property = turn_context.activity.from_property
    if not from_property:
        return ActionActor()
    return ActionActor(
        id=from_property.id,
        name=from_property.name,
        aad_object_id=from_property.aad_object_id,
    )


def register_handlers() -> None:
    @agent_app.activity(ActivityTypes.conversation_update)
    async def on_conversation_update(context: TurnContext, state: TurnState) -> None:
        await conversation_service.capture_from_turn_context(context)
        await register_installation_from_activity(context.activity)

        channel_data = context.activity.channel_data or {}
        team = channel_data.get("team") or {}
        channel = channel_data.get("channel") or {}
        log_event(
            logger,
            "conversationUpdate received",
            team_id=team.get("id"),
            channel_id=channel.get("id"),
            tenant_id=(context.activity.conversation.tenant_id if context.activity.conversation else None),
        )

    @agent_app.activity(ActivityTypes.invoke)
    async def on_invoke(context: TurnContext, state: TurnState) -> None:
        activity = context.activity

        if activity.name != ADAPTIVE_CARD_ACTION_NAME:
            # Not an Adaptive Card action (could be sign-in, task/fetch,
            # etc. from other Teams features) - nothing for this bot to do.
            await context.send_activity(
                _invoke_response_activity(InvokeResponse(status=200))
            )
            return

        action_value = activity.value or {}
        action = action_value.get("action") or {}
        data = action.get("data") or {}

        risk_id = data.get("riskId")
        action_key = data.get("actionKey")

        if not risk_id or not action_key:
            log_event(
                logger,
                "Adaptive Card action missing riskId/actionKey",
                level=30,
            )
            await context.send_activity(
                _invoke_response_activity(
                    InvokeResponse(
                        status=200,
                        body=AdaptiveCardInvokeResponse(
                            status_code=400,
                            type="application/vnd.microsoft.error",
                            value={"message": "Missing riskId or actionKey"},
                        ),
                    )
                )
            )
            return

        idempotency_key = f"{activity.id}:{risk_id}:{action_key}"
        if idempotency_store.seen_recently(idempotency_key):
            log_event(
                logger,
                "Duplicate Teams action ignored",
                risk_id=risk_id,
                action_key=action_key,
            )
            await context.send_activity(
                _invoke_response_activity(
                    InvokeResponse(
                        status=200,
                        body=AdaptiveCardInvokeResponse(
                            status_code=200,
                            type="application/vnd.microsoft.activity.message",
                            value={"message": "Already processing this action."},
                        ),
                    )
                )
            )
            return

        event = RiskActionEvent(
            event_id=str(uuid.uuid4()),
            risk_id=risk_id,
            action_key=action_key,
            destination=_extract_destination(context),
            actor=_extract_actor(context),
            payload={k: v for k, v in data.items() if k not in ("riskId", "actionKey")},
        )

        log_event(
            logger,
            "Forwarding Teams action to n8n",
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

        await context.send_activity(
            _invoke_response_activity(
                InvokeResponse(
                    status=200,
                    body=AdaptiveCardInvokeResponse(
                        status_code=status_code,
                        type="application/vnd.microsoft.activity.message",
                        value={"message": response_value},
                    ),
                )
            )
        )


def _invoke_response_activity(invoke_response: InvokeResponse):
    from microsoft_agents.activity import Activity

    return Activity(type=ActivityTypes.invoke_response, value=invoke_response)
