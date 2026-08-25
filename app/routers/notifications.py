

from __future__ import annotations

import uuid
from typing import Union

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError

from app.bot.proactive_sender import ChannelNotRegisteredError
from app.schemas.notifications import (
    ActionResultPayload,
    InitialNotificationPayload,
    NotificationResponse,
)
from app.services.notification_service import (
    TeamsSendError,
    UnsupportedCardTypeError,
    notification_service,
)
from app.utils.logger import get_logger, log_event
from app.utils.internal_auth import verify_internal_api_key

logger = get_logger(__name__)
router = APIRouter()


def _verify_internal_api_key(provided_key: str | None) -> None:
    """Compatibility wrapper for the shared internal-route authentication."""
    verify_internal_api_key(provided_key)


def _parse_payload(body: dict) -> Union[InitialNotificationPayload, ActionResultPayload]:
    event_type = body.get("eventType")
    if event_type == "initial_notification":
        return InitialNotificationPayload.model_validate(body)
    if event_type == "risk_action_result":
        return ActionResultPayload.model_validate(body)
    raise ValueError(f"Unsupported eventType: {event_type!r}")


@router.post("/api/notifications", response_model=NotificationResponse)
async def receive_notification(
    request: Request,
    x_internal_api_key: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
) -> NotificationResponse:
    _verify_internal_api_key(x_internal_api_key)

    raw_body = await request.json()

    try:
        payload = _parse_payload(raw_body)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid notification payload: {exc}",
        ) from exc

    correlation_id = x_correlation_id or payload.event_id or str(uuid.uuid4())
    log_event(
        logger,
        "teams_notification_received",
        event_id=payload.event_id,
        risk_id=payload.risk_id,
        correlation_id=correlation_id,
    )

    try:
        if isinstance(payload, InitialNotificationPayload):
            return await notification_service.handle_initial_notification(payload)
        return await notification_service.handle_action_result(payload)
    except UnsupportedCardTypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except ChannelNotRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except TeamsSendError as exc:
        raise HTTPException(
            status_code=(status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_410_GONE),
            detail={
                "success": False,
                "errorType": "destination_unavailable" if not exc.retryable else "delivery_failed",
                "errorCode": exc.code,
                "destinationId": getattr(payload.destination, "destination_id", None),
                "retryable": exc.retryable,
            },
        ) from exc
