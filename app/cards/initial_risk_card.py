"""
Initial Risk Adaptive Card.

Rendered from an ``InitialNotificationData`` (see app/schemas/notifications.py)
and sent proactively into the target Teams channel by the notification
service. No risk data is ever hardcoded here.
"""

from __future__ import annotations

from typing import Any

from app.cards.common import (
    new_card,
    risk_action_button,
    severity_color,
    text_block,
)
from app.schemas.notifications import InitialNotificationData


def _display_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _entity_blocks(notification: InitialNotificationData) -> list[dict[str, Any]]:
    entity = notification.entity
    identity = " · ".join(str(value) for value in (entity.id, entity.name) if value)
    blocks = []
    if identity:
        blocks.append(text_block(identity, is_subtle=True, spacing="None"))
    if entity.type:
        blocks.append(text_block(entity.type.replace("_", " ").title(), is_subtle=True,
                                 size="Small", spacing="None"))
    return blocks


def _metrics_blocks(notification: InitialNotificationData) -> list[dict[str, Any]]:
    if not notification.metrics:
        return []
    blocks: list[dict[str, Any]] = [
        text_block("KEY METRICS", weight="Bolder", size="Small", spacing="Medium")
    ]
    for start in range(0, len(notification.metrics), 2):
        columns = []
        for metric in notification.metrics[start:start + 2]:
            columns.append({
                "type": "Column",
                "width": "stretch",
                "items": [
                    text_block(metric.label, weight="Bolder", size="Small", is_subtle=True),
                    text_block(_display_value(metric.value), weight="Bolder", spacing="Small",
                               color=severity_color(metric.status or "")),
                ],
            })
        blocks.append({"type": "ColumnSet", "columns": columns, "spacing": "Small"})
    return blocks


def build_initial_risk_card(notification: InitialNotificationData) -> dict[str, Any]:
    header = {
        "type": "ColumnSet",
        "columns": [
            {
                "type": "Column",
                "width": "stretch",
                "items": [text_block(notification.title, weight="Bolder", size="Medium")],
            },
            {
                "type": "Column",
                "width": "auto",
                "items": [
                    text_block(
                        notification.severity.upper(),
                        weight="Bolder",
                        color=severity_color(notification.severity),
                    )
                ],
            },
        ],
    }

    summary = text_block(notification.summary, spacing="Medium")
    body = [header, *_entity_blocks(notification), summary, *_metrics_blocks(notification)]
    body.append(text_block(f"Risk ID: {notification.risk_id}", is_subtle=True,
                           size="Small", spacing="Medium"))

    actions = [
        risk_action_button("View Details", "view_details", notification.risk_id),
        risk_action_button("Mitigation Plan", "mitigation_plan", notification.risk_id),
    ]

    return new_card(body=body, actions=actions)
