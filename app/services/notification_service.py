"""
Notification service.

Converts payloads received from n8n (POST /api/notifications) into
Adaptive Cards and sends them proactively into the requested Teams
channel. This is purely a communication/rendering layer - no risk
business logic or MongoDB access happens here.
"""

from __future__ import annotations

from typing import Any, Callable

from app.bot.proactive_sender import ChannelNotRegisteredError, send_to_channel
from app.cards.assignment_card import build_assignment_confirmation_card
from app.cards.initial_risk_card import build_initial_risk_card
from app.cards.mitigation_plan_card import build_mitigation_plan_card
from app.cards.risk_details_card import build_risk_details_card
from app.cards.tracking_card import build_tracking_confirmation_card
from app.schemas.notifications import (
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
    pass


_CARD_BUILDERS: dict[ActionResultCardType, Callable[[dict[str, Any]], dict[str, Any]]] = {
    ActionResultCardType.RISK_DETAILS: build_risk_details_card,
    ActionResultCardType.MITIGATION_PLAN: build_mitigation_plan_card,
    ActionResultCardType.TRACKING_CONFIRMATION: build_tracking_confirmation_card,
    ActionResultCardType.ASSIGNMENT_CONFIRMATION: build_assignment_confirmation_card,
}


class NotificationService:
    async def handle_initial_notification(
        self, payload: InitialNotificationPayload
    ) -> NotificationResponse:
        card = build_initial_risk_card(payload.notification)

        await self._send(
            team_id=payload.destination.team_id,
            channel_id=payload.destination.channel_id,
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
        builder = _CARD_BUILDERS.get(payload.result.card_type)
        if builder is None:
            raise UnsupportedCardTypeError(
                f"Unsupported cardType: {payload.result.card_type}"
            )

        card = builder(payload.result.data)

        await self._send(
            team_id=payload.destination.team_id,
            channel_id=payload.destination.channel_id,
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
        team_id: str,
        channel_id: str,
        card: dict[str, Any],
        event_id: str,
        risk_id: str,
    ) -> None:
        try:
            message_id = await send_to_channel(team_id, channel_id, card)
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
            )
            raise TeamsSendError("Failed to send Adaptive Card to Microsoft Teams") from exc

        log_event(
            logger,
            "Adaptive Card sent",
            event_id=event_id,
            risk_id=risk_id,
            team_id=team_id,
            channel_id=channel_id,
            message_id=message_id,
        )


notification_service = NotificationService()
