"""
POST /api/notifications

Internal endpoint called by n8n workflows. Carries both:
  * initial_notification payloads (send the Initial Risk Card), and
  * risk_action_result payloads (send a follow-up card as a NEW message).

Secured with an optional X-Internal-API-Key header (INTERNAL_API_KEY env
var). If INTERNAL_API_KEY is blank (development only), requests are
allowed through unauthenticated.
"""

from __future__ import annotations

import hmac
import uuid
from typing import Union

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError

from app.bot.proactive_sender import ChannelNotRegisteredError
from app.config import get_settings
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

logger = get_logger(__name__)
router = APIRouter()


def _verify_internal_api_key(provided_key: str | None) -> None:
    settings = get_settings()
    expected_key = settings.INTERNAL_API_KEY

    if not expected_key:
        # No key configured - allowed only because this is meant purely
        # for local/dev use (see README / .env.example).
        return

    if not provided_key or not hmac.compare_digest(provided_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Internal-API-Key",
        )


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
        "Received notification from n8n",
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
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
