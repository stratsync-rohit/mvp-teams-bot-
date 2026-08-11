"""Generic renderer for backend-defined Adaptive Card sections."""

from __future__ import annotations

import json
from typing import Any, Callable

from app.cards.common import container, fact_set, new_card, severity_color, text_block
from app.utils.logger import get_logger, log_event

logger = get_logger(__name__)


def _heading(title: Any) -> list[dict[str, Any]]:
    return [text_block(str(title), weight="Bolder", spacing="Medium")] if title else []


def _text_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    items = _heading(section.get("title"))
    if section.get("content") is not None:
        items.append(text_block(str(section["content"])))
    return items


def _facts_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    items = _heading(section.get("title"))
    facts = [
        (str(item.get("label", "")), str(item.get("value", "")))
        for item in section.get("items") or []
        if isinstance(item, dict) and (item.get("label") is not None or item.get("value") is not None)
    ]
    if facts:
        items.append(fact_set(facts))
    return items


def _bullets_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    items = _heading(section.get("title"))
    items.extend(
        text_block(f"• {value}", spacing="Small")
        for value in section.get("items") or []
        if value is not None
    )
    return items


def _steps_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    rendered = _heading(section.get("title"))
    for number, step in enumerate(section.get("items") or [], start=1):
        if not isinstance(step, dict):
            continue
        step_items: list[dict[str, Any]] = []
        title = step.get("title")
        step_items.append(text_block(f"{number}. {title}" if title else f"{number}.", weight="Bolder"))
        if step.get("description") is not None:
            step_items.append(text_block(str(step["description"]), spacing="Small"))
        metadata = [
            f"{label}: {step[key]}"
            for key, label in (("owner", "Owner"), ("status", "Status"))
            if step.get(key) is not None
        ]
        if metadata:
            step_items.append(text_block(" · ".join(metadata), size="Small", is_subtle=True, spacing="Small"))
        rendered.append(container(step_items, spacing="Small"))
    return rendered


def _metrics_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    rendered = _heading(section.get("title"))
    columns = []
    for metric in section.get("items") or []:
        if not isinstance(metric, dict):
            continue
        blocks = []
        if metric.get("label") is not None:
            blocks.append(text_block(str(metric["label"]), size="Small", is_subtle=True))
        if metric.get("value") is not None:
            blocks.append(text_block(str(metric["value"]), weight="Bolder", spacing="None"))
        if metric.get("status") is not None:
            blocks.append(text_block(str(metric["status"]).title(), size="Small", color=severity_color(str(metric["status"])), spacing="None"))
        if blocks:
            columns.append({"type": "Column", "width": "stretch", "items": blocks})
    if columns:
        rendered.append({"type": "ColumnSet", "columns": columns})
    return rendered


def _table_row(values: list[Any], column_count: int, *, header: bool = False) -> dict[str, Any]:
    padded = values[:column_count] + [""] * max(0, column_count - len(values))
    return {
        "type": "ColumnSet",
        "columns": [
            {
                "type": "Column",
                "width": "stretch",
                "items": [text_block(str(value), weight="Bolder" if header else None, size="Small")],
            }
            for value in padded
        ],
    }


def _table_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    rendered = _heading(section.get("title"))
    columns = section.get("columns") or []
    rows = [row for row in section.get("rows") or [] if isinstance(row, list)]
    column_count = max([len(columns), *(len(row) for row in rows)], default=0)
    if column_count:
        if columns:
            rendered.append(_table_row(list(columns), column_count, header=True))
        rendered.extend(_table_row(row, column_count) for row in rows)
    return rendered


def _callout_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    items = _heading(section.get("title"))
    if section.get("content") is not None:
        items.append(text_block(str(section["content"])))
    return [{"type": "Container", "style": "emphasis", "items": items, "spacing": "Medium"}]


_SECTION_RENDERERS: dict[str, Callable[[dict[str, Any]], list[dict[str, Any]]]] = {
    "text": _text_section,
    "facts": _facts_section,
    "bullets": _bullets_section,
    "steps": _steps_section,
    "metrics": _metrics_section,
    "table": _table_section,
    "callout": _callout_section,
}


def _unknown_section(section: dict[str, Any], risk_id: Any) -> list[dict[str, Any]]:
    section_type = section.get("type")
    log_event(
        logger,
        "unsupported_dynamic_section_type",
        section_type=section_type,
        risk_id=risk_id,
    )
    rendered = _heading(section.get("title"))
    fallback = {key: value for key, value in section.items() if key not in {"type", "title"}}
    if fallback:
        try:
            content = json.dumps(fallback, indent=2, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            content = str(fallback)
        rendered.append(text_block(content))
    return rendered


def render_dynamic_card(data: dict[str, Any]) -> dict[str, Any]:
    """Render flexible backend sections in exactly the supplied order."""
    body: list[dict[str, Any]] = []
    title = data.get("title") or "Details"
    severity = data.get("severity")
    body.append(text_block(str(title), weight="Bolder", size="Medium", color=severity_color(str(severity)) if severity else None))
    if data.get("subtitle") is not None:
        body.append(text_block(str(data["subtitle"]), is_subtle=True, spacing="Small"))

    facts: list[tuple[str, str]] = []
    if severity is not None:
        facts.append(("Severity", str(severity).title()))
    entity = data.get("entity")
    if isinstance(entity, dict):
        for key, label in (("name", "Entity"), ("id", "Entity ID"), ("type", "Entity type")):
            if entity.get(key) is not None:
                facts.append((label, str(entity[key])))
    if facts:
        body.append(fact_set(facts))

    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            log_event(logger, "unsupported_dynamic_section_type", section_type=type(section).__name__, risk_id=data.get("riskId"))
            continue
        renderer = _SECTION_RENDERERS.get(str(section.get("type", "")).lower())
        rendered = renderer(section) if renderer else _unknown_section(section, data.get("riskId"))
        if rendered:
            body.append(container(rendered, spacing="Medium"))

    return new_card(body=body)
