"""
Shared helpers for building Microsoft Teams Adaptive Cards.

Uses Adaptive Card schema version 1.5, which is broadly supported across
current Microsoft Teams clients, and sticks to well-supported elements
(TextBlock, FactSet, Container, ColumnSet, ActionSet) rather than
experimental/unverified properties.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional, Union

ADAPTIVE_CARD_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
ADAPTIVE_CARD_VERSION = "1.5"
ADAPTIVE_CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"

_CURRENCY_SYMBOLS = {
    "USD": "US$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
}

_SEVERITY_COLOR = {
    "low": "Good",
    "medium": "Warning",
    "high": "Attention",
    "critical": "Attention",
}


def format_currency(amount: Union[int, float], currency: str = "USD") -> str:
    """
    format_currency(210000, "USD") -> "US$210,000"

    Falls back to "<CODE> <amount>" for unrecognized currency codes rather
    than guessing a symbol.
    """
    symbol = _CURRENCY_SYMBOLS.get(currency.upper())
    formatted_amount = f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"
    if symbol:
        return f"{symbol}{formatted_amount}"
    return f"{currency.upper()} {formatted_amount}"


def format_display_date(value: Optional[Union[str, date, datetime]]) -> str:
    """
    Converts an ISO date (e.g. "2026-08-15") into a display string
    (e.g. "15 Aug 2026"). The underlying API data / stored value is never
    mutated - this is purely a rendering helper.
    """
    if value is None:
        return "-"
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%d %b %Y")


def severity_color(severity: str) -> str:
    return _SEVERITY_COLOR.get(severity.lower(), "Default")


def new_card(body: list[dict[str, Any]], actions: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    card: dict[str, Any] = {
        "type": "AdaptiveCard",
        "$schema": ADAPTIVE_CARD_SCHEMA,
        "version": ADAPTIVE_CARD_VERSION,
        "body": body,
    }
    if actions:
        card["actions"] = actions
    return card


def text_block(
    text: str,
    *,
    weight: Optional[str] = None,
    size: Optional[str] = None,
    color: Optional[str] = None,
    wrap: bool = True,
    is_subtle: Optional[bool] = None,
    spacing: Optional[str] = None,
) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "TextBlock", "text": text, "wrap": wrap}
    if weight:
        block["weight"] = weight
    if size:
        block["size"] = size
    if color:
        block["color"] = color
    if is_subtle is not None:
        block["isSubtle"] = is_subtle
    if spacing:
        block["spacing"] = spacing
    return block


def fact_set(facts: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "type": "FactSet",
        "facts": [{"title": title, "value": value} for title, value in facts],
    }


def bullet_list(items: list[str]) -> dict[str, Any]:
    """Renders a simple bullet list using a single wrapped TextBlock."""
    body = "\n".join(f"- {item}" for item in items) if items else "- (none)"
    return text_block(body, wrap=True)


def container(items: list[dict[str, Any]], *, spacing: Optional[str] = None) -> dict[str, Any]:
    c: dict[str, Any] = {"type": "Container", "items": items}
    if spacing:
        c["spacing"] = spacing
    return c


def action_execute(title: str, verb: str, data: dict[str, Any]) -> dict[str, Any]:
    """
    Builds a Teams-supported Action.Execute button.

    IMPORTANT: buttons that trigger bot workflows must never use
    Action.OpenUrl. Action.Execute lets Teams deliver the click back to
    this bot's /api/messages endpoint as an invoke activity, which we then
    forward to n8n - it never opens a browser.
    """
    return {
        "type": "Action.Execute",
        "title": title,
        "verb": verb,
        "data": data,
    }


def risk_action_button(label: str, action_key: str, risk_id: str) -> dict[str, Any]:
    """
    Standard button for risk workflow actions. Button data intentionally
    carries only riskId + actionKey - never the full risk object.
    """
    return action_execute(
        title=label,
        verb="risk_action",
        data={"riskId": risk_id, "actionKey": action_key},
    )


def to_attachment(card: dict[str, Any]) -> dict[str, Any]:
    """Wraps a raw Adaptive Card JSON body as a Teams message attachment."""
    return {"contentType": ADAPTIVE_CARD_CONTENT_TYPE, "content": card}
