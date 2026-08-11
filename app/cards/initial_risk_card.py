"""
Initial Risk Adaptive Card.

Rendered from an ``InitialNotificationData`` (see app/schemas/notifications.py)
and sent proactively into the target Teams channel by the notification
service. No risk data is ever hardcoded here.
"""

from __future__ import annotations

from typing import Any

from app.cards.common import (
    container,
    fact_set,
    format_display_date,
    new_card,
    risk_action_button,
    severity_color,
    text_block,
)
from app.schemas.notifications import InitialNotificationData


INITIAL_RISK_ACTION_KEYS = {"view_details", "mitigation_plan"}


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
                        notification.severity.value.upper() + " SEVERITY",
                        weight="Bolder",
                        color=severity_color(notification.severity.value),
                    )
                ],
            },
        ],
    }

    vessel_line = text_block(
        f"{notification.vessel.id} \u00b7 {notification.vessel.name}",
        is_subtle=True,
        spacing="None",
    )

    summary = text_block(notification.summary, spacing="Medium")

    deadline_fact = fact_set(
        [("Deadline", format_display_date(notification.deadline))]
    ) if notification.deadline else None

    body = [header, vessel_line, summary]
    if deadline_fact:
        body.append(deadline_fact)

    body.append(
        container(
            [text_block(f"Risk ID: {notification.risk_id}", is_subtle=True, size="Small")],
            spacing="Medium",
        )
    )

    actions = [
        risk_action_button(action.label, action.key, notification.risk_id)
        for action in notification.actions
        if action.key in INITIAL_RISK_ACTION_KEYS
    ]

    return new_card(body=body, actions=actions)
