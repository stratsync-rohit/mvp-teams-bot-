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
    severity_color,
    text_block,
)


def build_risk_details_card(data: dict[str, Any]) -> dict[str, Any]:
    risk_id = data.get("riskId", "")
    title = data.get("title", "Risk details")

    facts: list[tuple[str, str]] = []
    severity = data.get("severity")
    vessel = data.get("vessel") or {}
    if severity:
        facts.append(("Severity", str(severity).title()))
    if vessel.get("name"):
        facts.append(("Vessel", str(vessel["name"])))
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

    body: list[dict[str, Any]] = [
        text_block(
            title,
            weight="Bolder",
            size="Medium",
            color=severity_color(str(severity)) if severity else None,
        )
    ]
    if facts:
        body.append(fact_set(facts))
    if data.get("summary"):
        body.append(text_block(str(data["summary"]), spacing="Medium"))

    details = data.get("details") or {}
    underlying_exposure = (
        details.get("underlyingExposure")
        or data.get("underlyingExposure")
        or []
    )
    if underlying_exposure:
        body.append(
            container(
                [
                    text_block("Underlying exposure", weight="Bolder", spacing="Medium"),
                    bullet_list(underlying_exposure),
                ]
            )
        )

    impact = details.get("impact") or data.get("impact") or []
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
