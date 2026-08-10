"""
Mitigation Plan Adaptive Card - sent as a NEW Teams message after the user
clicks "Mitigation Plan" and n8n calls back with cardType=mitigation_plan.
"""

from __future__ import annotations

from typing import Any

from app.cards.common import container, new_card, text_block


def _build_step_block(step: dict[str, Any]) -> dict[str, Any]:
    step_no = step.get("step", "")
    title = step.get("title", "")
    description = step.get("description", "")
    owner = step.get("owner")
    status = step.get("status")

    items = [text_block(f"{step_no}. {title}", weight="Bolder")]
    if description:
        items.append(text_block(description, is_subtle=True, spacing="None"))
    meta_bits = []
    if owner:
        meta_bits.append(f"Owner: {owner}")
    if status:
        meta_bits.append(f"Status: {status}")
    if meta_bits:
        items.append(text_block(" \u00b7 ".join(meta_bits), size="Small", spacing="None"))

    return container(items, spacing="Medium")


def build_mitigation_plan_card(data: dict[str, Any]) -> dict[str, Any]:
    risk_id = data.get("riskId", "")
    title = data.get("title", "")
    summary = data.get("summary", "")
    steps = data.get("steps") or []

    body: list[dict[str, Any]] = [
        text_block("Mitigation Plan", weight="Bolder", size="Medium"),
    ]
    if title:
        body.append(text_block(title, weight="Bolder", spacing="None"))
    if summary:
        body.append(text_block(summary, spacing="Small"))

    for step in steps:
        body.append(_build_step_block(step))

    body.append(
        container(
            [text_block(f"Risk ID: {risk_id}", is_subtle=True, size="Small")],
            spacing="Medium",
        )
    )

    return new_card(body=body)
