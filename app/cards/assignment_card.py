"""
Assignment Adaptive Cards.

V1 supports two paths, kept deliberately modular so a full Teams dialog /
people-picker implementation can replace ``build_assignment_input_card``
later without touching the confirmation path:

  1. ``build_assignment_confirmation_card`` - result already contains the
     assigned user (e.g. n8n/backend resolved the assignment already).
  2. ``build_assignment_input_card`` - a simple Adaptive Card Input.Text
     fallback for capturing ``assignedTo`` when no richer picker is wired
     up yet. This is intentionally minimal; do not treat it as a complete
     people-picker implementation.
"""

from __future__ import annotations

from typing import Any

from app.cards.common import action_execute, new_card, text_block


def build_assignment_confirmation_card(data: dict[str, Any]) -> dict[str, Any]:
    risk_id = data.get("riskId", "")
    assigned_to = data.get("assignedTo") or data.get("assigned_to") or "Unassigned"

    body: list[dict[str, Any]] = [
        text_block("Risk assigned", weight="Bolder", size="Medium"),
        text_block(f"{risk_id} has been assigned to {assigned_to}.", spacing="Small"),
    ]
    return new_card(body=body)


def build_assignment_input_card(risk_id: str) -> dict[str, Any]:
    """
    Minimal fallback input card for capturing an assignee name when no
    richer Teams dialog / people-picker flow is available yet. Submitting
    this card raises the same Action.Execute verb ("risk_action") with
    actionKey "assign" and the entered value included, which the bot
    forwards to n8n exactly like any other button click.
    """
    body = [
        text_block("Assign this risk", weight="Bolder", size="Medium"),
        {
            "type": "Input.Text",
            "id": "assignedTo",
            "placeholder": "Enter a name or email",
            "label": "Assign to",
        },
    ]
    actions = [action_execute("Submit", "risk_action", {"riskId": risk_id, "actionKey": "assign"})]
    return new_card(body=body, actions=actions)
