"""
Notification service.

Converts payloads received from n8n (POST /api/notifications) into
Adaptive Cards and sends them proactively into the requested Teams
channel. This is purely a communication/rendering layer - no risk
business logic or MongoDB access happens here.
"""

from __future__ import annotations

from typing import Any, Callable

from app.bot.proactive_sender import ChannelNotRegisteredError, send_to_conversation
from app.cards.assignment_card import build_assignment_confirmation_card
from app.cards.dynamic_card import render_dynamic_card
from app.cards.initial_risk_card import build_initial_risk_card
from app.cards.mitigation_plan_card import build_mitigation_plan_card
from app.cards.risk_details_card import build_risk_details_card
from app.cards.tracking_card import build_tracking_confirmation_card
from app.schemas.notifications import (
    ActionResult,
    ActionResultCardType,
    ActionResultPayload,
    InitialNotificationPayload,
    NotificationResponse,
)
from app.utils.logger import get_logger, log_event

logger = get_logger(__name__)


class UnsupportedCardTypeError(Exception):
    pass


class TeamsSendError(Exception):
    def __init__(self, code: str, retryable: bool):
        self.code = code
        self.retryable = retryable
        super().__init__("Failed to send Adaptive Card to Microsoft Teams")


def classify_teams_error(exc: Exception) -> tuple[str, bool]:
    """Normalize SDK failures conservatively without returning raw responses."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    text = str(exc).lower()
    if status == 429:
        return "rate_limited", True
    if status in {500, 502, 503, 504}:
        return "microsoft_server_error", True
    if any(marker in text for marker in ("conversation not found", "conversationnotfound")):
        return "conversation_not_found", False
    if any(marker in text for marker in ("channel not found", "channelnotfound")):
        return "channel_not_found", False
    if status == 403 and any(marker in text for marker in ("not a member", "bot not in", "permission revoked")):
        return "permission_revoked", False
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "network_error", True
    return "unknown_error", True


_CARD_BUILDERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "dynamic_card": render_dynamic_card,
    ActionResultCardType.RISK_DETAILS.value: build_risk_details_card,
    ActionResultCardType.MITIGATION_PLAN.value: build_mitigation_plan_card,
    ActionResultCardType.TRACKING_CONFIRMATION.value: build_tracking_confirmation_card,
    ActionResultCardType.ASSIGNMENT_CONFIRMATION.value: build_assignment_confirmation_card,
}


def render_action_result_card(result: ActionResult) -> dict[str, Any]:
    """Dispatch a standardized backend result to its isolated card renderer."""
    builder = _CARD_BUILDERS.get(result.card_type)
    if builder is None:
        log_event(logger, "Unsupported action-result card type", card_type=result.card_type)
        raise UnsupportedCardTypeError(f"Unsupported cardType: {result.card_type}")

    # riskId belongs to the result envelope. Supplying it as a renderer fallback
    # preserves the useful footer without imposing a shared shape on data.
    data = {"riskId": result.risk_id, **result.data}
    return builder(data)


class NotificationService:
    async def handle_initial_notification(
        self, payload: InitialNotificationPayload
    ) -> NotificationResponse:
        card = build_initial_risk_card(payload.notification)

        await self._send(
            tenant_id=payload.destination.tenant_id,
            team_id=payload.destination.team_id,
            channel_id=payload.destination.channel_id,
            conversation_id=payload.destination.conversation_id,
            service_url=payload.destination.service_url,
            card=card,
            event_id=payload.event_id,
            risk_id=payload.risk_id,
        )

        return NotificationResponse(
            success=True,
            event_id=payload.event_id,
            risk_id=payload.risk_id,
            message="Adaptive Card sent to Microsoft Teams",
        )

    async def handle_action_result(
        self, payload: ActionResultPayload
    ) -> NotificationResponse:
        card = render_action_result_card(payload.result)

        await self._send(
            tenant_id=payload.destination.tenant_id,
            team_id=payload.destination.team_id,
            channel_id=payload.destination.channel_id,
            conversation_id=payload.destination.conversation_id,
            service_url=payload.destination.service_url,
            card=card,
            event_id=payload.event_id,
            risk_id=payload.risk_id,
        )

        return NotificationResponse(
            success=True,
            event_id=payload.event_id,
            risk_id=payload.risk_id,
            message="Adaptive Card sent to Microsoft Teams",
        )

    async def _send(
        self,
        *,
        tenant_id: str,
        team_id: str,
        channel_id: str | None,
        conversation_id: str,
        service_url: str,
        card: dict[str, Any],
        event_id: str,
        risk_id: str,
    ) -> None:
        try:
            message_id = await send_to_conversation(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                service_url=service_url,
                card=card,
            )
        except ChannelNotRegisteredError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize any Teams send failure
            log_event(
                logger,
                "Microsoft Teams send failure",
                level=40,
                event_id=event_id,
                risk_id=risk_id,
                team_id=team_id,
                channel_id=channel_id,
                conversation_id=conversation_id,
            )
            code, retryable = classify_teams_error(exc)
            raise TeamsSendError(code, retryable) from exc

        log_event(
            logger,
            "Adaptive Card sent",
            event_id=event_id,
            risk_id=risk_id,
            team_id=team_id,
            channel_id=channel_id,
            conversation_id=conversation_id,
            message_id=message_id,
        )


notification_service = NotificationService()
