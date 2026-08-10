"""
Tracking confirmation Adaptive Card - a small confirmation card sent as a
NEW Teams message when result.cardType == tracking_confirmation.
"""

from __future__ import annotations

from typing import Any

from app.cards.common import new_card, text_block


def build_tracking_confirmation_card(data: dict[str, Any]) -> dict[str, Any]:
    risk_id = data.get("riskId", "")
    actor_name = data.get("actorName") or (data.get("actor") or {}).get("name")

    body: list[dict[str, Any]] = [
        text_block("Risk tracking enabled", weight="Bolder", size="Medium"),
        text_block(f"{risk_id} is now being tracked.", spacing="Small"),
    ]
    if actor_name:
        body.append(text_block(f"Tracked by {actor_name}", is_subtle=True, size="Small"))

    return new_card(body=body)
