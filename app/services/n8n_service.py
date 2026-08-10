"""
n8n Action Handler client.

Forwards riskId + actionKey + actor + destination (constructed from a
Teams Adaptive Card Action.Execute activity) to n8n's Action Handler
workflow via HTTP. This bot never talks to MongoDB or the backend
directly - n8n owns that orchestration.
"""

from __future__ import annotations

import httpx

from app.config import Settings, get_settings
from app.schemas.actions import RiskActionEvent
from app.utils.logger import get_logger, log_event

logger = get_logger(__name__)


class N8nActionWebhookError(Exception):
    """Raised when the n8n Action Handler webhook cannot be reached or fails."""


class N8nService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def send_action_event(self, event: RiskActionEvent) -> None:
        webhook_url = self._settings.N8N_ACTION_WEBHOOK_URL
        if not webhook_url:
            log_event(
                logger,
                "N8N_ACTION_WEBHOOK_URL is not configured; skipping forward",
                level=30,
                event_id=event.event_id,
                risk_id=event.risk_id,
                action_key=event.action_key,
            )
            raise N8nActionWebhookError("n8n action webhook is not configured")

        headers = {
            "Content-Type": "application/json",
            "X-Correlation-ID": event.event_id,
        }
        # Structured so an X-Internal-API-Key (or similar) header required by
        # n8n in the future can be added here without touching call sites.
        if self._settings.INTERNAL_API_KEY:
            headers["X-Internal-API-Key"] = self._settings.INTERNAL_API_KEY

        body = event.to_wire_dict()

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.N8N_TIMEOUT_SECONDS
            ) as client:
                response = await client.post(webhook_url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            log_event(
                logger,
                "n8n action webhook timed out",
                level=40,
                event_id=event.event_id,
                risk_id=event.risk_id,
                action_key=event.action_key,
            )
            raise N8nActionWebhookError("n8n action webhook timed out") from exc
        except httpx.HTTPError as exc:
            log_event(
                logger,
                "n8n action webhook network failure",
                level=40,
                event_id=event.event_id,
                risk_id=event.risk_id,
                action_key=event.action_key,
            )
            raise N8nActionWebhookError("n8n action webhook network failure") from exc

        if response.status_code >= 300:
            log_event(
                logger,
                "n8n action webhook returned non-2xx",
                level=40,
                event_id=event.event_id,
                risk_id=event.risk_id,
                action_key=event.action_key,
                status=response.status_code,
            )
            raise N8nActionWebhookError(
                f"n8n action webhook returned status {response.status_code}"
            )

        log_event(
            logger,
            "n8n action webhook call succeeded",
            event_id=event.event_id,
            risk_id=event.risk_id,
            action_key=event.action_key,
            status=response.status_code,
        )
