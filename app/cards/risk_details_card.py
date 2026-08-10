"""
Risk Details Adaptive Card - sent as a NEW Teams message (never replaces
the original Initial Risk Card) after the user clicks "View Details" and
n8n calls back into POST /api/notifications with cardType=risk_details.
"""

from __future__ import annotations

from typing import Any

from app.cards.common import (
    bullet_list,
    container,
    fact_set,
    format_currency,
    format_display_date,
    new_card,
    text_block,
)


def build_risk_details_card(data: dict[str, Any]) -> dict[str, Any]:
    risk_id = data.get("riskId", "")
    title = data.get("title", "Risk details")

    facts: list[tuple[str, str]] = []
    if "fundingShortfall" in data:
        facts.append(
            ("Funding shortfall", format_currency(data["fundingShortfall"]))
        )
    if "paymentsAtRisk" in data:
        facts.append(("Payments at risk", format_currency(data["paymentsAtRisk"])))
    if data.get("deadline"):
        facts.append(("Deadline", format_display_date(data["deadline"])))
    if data.get("accountRisk"):
        facts.append(("Account risk", str(data["accountRisk"])))

    body: list[dict[str, Any]] = [text_block(title, weight="Bolder", size="Medium")]
    if facts:
        body.append(fact_set(facts))

    underlying_exposure = data.get("underlyingExposure") or []
    if underlying_exposure:
        body.append(
            container(
                [
                    text_block("Underlying exposure", weight="Bolder", spacing="Medium"),
                    bullet_list(underlying_exposure),
                ]
            )
        )

    impact = data.get("impact") or []
    if impact:
        body.append(
            container(
                [
                    text_block("Impact", weight="Bolder", spacing="Medium"),
                    bullet_list(impact),
                ]
            )
        )

    body.append(
        container(
            [text_block(f"Risk ID: {risk_id}", is_subtle=True, size="Small")],
            spacing="Medium",
        )
    )

    return new_card(body=body)
