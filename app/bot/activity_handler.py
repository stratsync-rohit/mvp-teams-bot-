"""Thin Microsoft 365 Agents SDK activity routing and lifecycle branching."""

from __future__ import annotations

import html
import re
from microsoft_agents.activity import (
    ActivityTypes,
    InvokeResponse,
)
from microsoft_agents.hosting.core import TurnContext, TurnState

from app.bot.teams_bot import agent_app
from app.schemas.actions import ActionActor, ActionDestination
from app.services import adaptive_card_actions, teams_lifecycle
# Retained compatibility seams below are imported by existing callers/tests.
from app.services.conversation_service import conversation_service
from app.services.teams_channel_discovery import enumerate_existing_team_channels
from app.services.backend_client import (
    disconnect_teams_installation,
    # Compatibility/test seam only. Registered lifecycle handlers never call
    # destination registration; explicit UI Connect is owned by the backend.
    register_teams_destination,
    register_teams_installation,
    record_discovered_teams_channel,
)
from app.services.n8n_service import N8nService
from app.storage.idempotency_store import idempotency_store
from app.utils.logger import get_logger, log_event
from app.utils.teams_context import (
    activity_added_recipient,
    channel_metadata_diagnostic,
    conversation_update_diagnostic,
    extract_explicit_install_channel,
    extract_teams_context,
    has_authoritative_channel_conversation,
    installation_update_diagnostic,
)

logger = get_logger(__name__)

n8n_service = N8nService()

ADAPTIVE_CARD_ACTION_NAME = adaptive_card_actions.ADAPTIVE_CARD_ACTION_NAME
DISCONNECT_COMMAND = "disconnect"

# Compatibility seams retained for direct helper callers and regression tests.
_activity_added_bot = activity_added_recipient
_conversation_update_diagnostic = conversation_update_diagnostic


async def register_installation_from_activity(activity) -> bool:
    """Register a valid Team-scoped activity without disrupting its processing."""
    return await teams_lifecycle.register_installation(
        activity, registrar=register_teams_installation
    )


async def discover_channel_from_activity(
    activity,
    *,
    available: bool = True,
    explicit_event: bool = False,
    activity_context: dict | None = None,
    diagnostic: dict | None = None,
) -> bool:
    """Persist trustworthy Bot Framework channel context without connecting it."""
    return await teams_lifecycle.discover_channel(
        activity,
        writer=record_discovered_teams_channel,
        available=available,
        explicit_event=explicit_event,
        activity_context=activity_context,
        diagnostic=diagnostic,
    )


async def capture_channel_destination_from_activity(
    activity, *, trigger: str = "lifecycle",
) -> bool:
    """Deprecated compatibility wrapper: lifecycle capture is discovery-only."""
    del trigger
    return await discover_channel_from_activity(activity)


def _message_command(activity) -> str | None:
    """Extract a bare command while tolerating the Teams bot mention markup."""
    text = html.unescape(getattr(activity, "text", None) or "")
    text = re.sub(
        r"<at\b[^>]*>.*?</at>", " ", text, flags=re.IGNORECASE | re.DOTALL
    )
    command = " ".join(text.strip().lower().split())
    return command if command == DISCONNECT_COMMAND else None


async def disconnect_channel_from_activity(activity) -> bool:
    """Disconnect only the exact channel represented by this Teams activity."""
    return await teams_lifecycle.disconnect_channel(
        activity, disconnector=disconnect_teams_installation
    )


async def handle_message(context: TurnContext, state: TurnState) -> None:
    """Handle discovery/disconnect; only explicit StratSync UI Connect connects."""
    activity = context.activity
    # Genuine in-channel message context is another authoritative discovery
    # signal. This records availability only and never creates a destination.
    activity_context = extract_teams_context(activity)
    diagnostic = channel_metadata_diagnostic(activity)
    await discover_channel_from_activity(
        activity, activity_context=activity_context, diagnostic=diagnostic
    )
    command = _message_command(activity)
    if command is not None:
        log_event(
            logger, "teams_disconnect_command_received",
            activity_type=getattr(activity, "type", None),
            normalized_command=command,
            tenant_id=activity_context["tenantId"], team_id=activity_context["teamId"],
            channel_id=activity_context["channelId"],
            conversation_id=activity_context["conversationId"],
            service_url_present=bool(activity_context["serviceUrl"]), **diagnostic,
        )
    if command is None:
        return

    try:
        successful = await disconnect_channel_from_activity(context.activity)
    except Exception as exc:
        log_event(
            logger, "teams_channel_disconnect_failed", level=40,
            error_type=type(exc).__name__, tenant_id=activity_context["tenantId"],
            team_id=activity_context["teamId"], channel_id=activity_context["channelId"],
            conversation_id=activity_context["conversationId"],
        )
        successful = False
    message = (
        "Channel disconnected successfully."
        if successful else
        "This command must be sent from a connected Microsoft Teams channel."
    )
    await context.send_activity(message)


async def disconnect_installation_from_activity(activity) -> bool:
    """Forward a Teams-issued removal identity without trusting an account ID."""
    return await teams_lifecycle.disconnect_installation(
        activity, disconnector=disconnect_teams_installation
    )


async def handle_installation_update(context: TurnContext, state: TurnState) -> None:
    """Handle the SDK's installationUpdate add/remove lifecycle activity."""
    action = (context.activity.action or "").lower()
    if action == "remove":
        await disconnect_installation_from_activity(context.activity)
    elif action == "add":
        activity = context.activity
        activity_context = extract_teams_context(activity)
        log_event(
            logger, "teams_installation_update_add_metadata",
            **installation_update_diagnostic(activity),
        )
        # Team/app lifecycle persistence is independent of channel selection and
        # must succeed (or fail safely) before discovery is attempted.
        installation_registered = await register_installation_from_activity(activity)
        if installation_registered:
            # Discovery is intentionally independent of destination creation.
            # Contain even an unexpected helper failure so installation always
            # remains successful and lifecycle handling can continue.
            try:
                await enumerate_existing_team_channels(context)
            except Exception as exc:
                log_event(
                    logger, "teams_channel_enumeration_failed", level=40,
                    tenant_id=activity_context["tenantId"],
                    team_id=activity_context["teamId"],
                    error_type=type(exc).__name__, status=None,
                )
        selected = extract_explicit_install_channel(
            activity, context=activity_context
        )
        if not selected:
            if installation_registered:
                log_event(
                    logger, "teams_team_installation_registered",
                    tenant_id=activity_context["tenantId"],
                    team_id=activity_context["teamId"],
                    conversation_id=activity_context["conversationId"],
                )
            log_event(
                logger, "teams_channel_registration_skipped",
                reason="no_explicit_channel_selection",
                tenant_id=activity_context["tenantId"],
                team_id=activity_context["teamId"],
                conversation_id=activity_context["conversationId"],
            )
            return

        required = (
            selected["tenantId"], selected["teamId"], selected["channelId"],
            selected["channelName"], selected["serviceUrl"],
        )
        if not all(required):
            log_event(
                logger, "teams_channel_registration_skipped",
                reason="explicit_channel_context_incomplete",
                tenant_id=selected["tenantId"], team_id=selected["teamId"],
                channel_id=selected["channelId"],
            )
            return

        discovered = await discover_channel_from_activity(
            activity, explicit_event=True, activity_context=selected
        )
        if discovered:
            log_event(
                logger, "teams_channel_discovered_not_connected",
                tenant_id=selected["tenantId"], team_id=selected["teamId"],
                channel_id=selected["channelId"],
                conversation_id=selected["conversationId"],
            )


async def handle_channel_member_added(
    context: TurnContext, state: TurnState,
) -> None:
    """Discover the authoritative channel where Teams added this bot."""
    activity = context.activity
    diagnostic = channel_metadata_diagnostic(activity)
    activity_context = extract_teams_context(activity)
    event_type = (diagnostic["event_type"] or "").lower()
    safe_context = {
        "tenant_id": activity_context["tenantId"],
        "team_id": activity_context["teamId"],
        "channel_id": activity_context["channelId"],
        "conversation_id": activity_context["conversationId"],
        "event_type": diagnostic["event_type"],
    }
    log_event(logger, "teams_channel_member_added_received", **safe_context)
    await register_installation_from_activity(activity)

    if getattr(activity, "type", None) != ActivityTypes.conversation_update:
        log_event(logger, "teams_channel_registration_skipped",
                  reason="not_conversation_update", **safe_context)
        return
    if event_type != "channelmemberadded":
        log_event(logger, "teams_channel_registration_skipped",
                  reason="not_channel_member_added", **safe_context)
        return
    if not _activity_added_bot(activity):
        log_event(logger, "teams_channel_registration_skipped",
                  reason="added_member_is_not_bot", **safe_context)
        return
    log_event(logger, "teams_channel_member_added_bot_verified", **safe_context)

    if not has_authoritative_channel_conversation(
        activity, context=activity_context, diagnostic=diagnostic
    ):
        log_event(logger, "teams_channel_registration_skipped",
                  reason="invalid_channel_conversation_context", **safe_context)
        return
    discovered = await discover_channel_from_activity(
        activity, activity_context=activity_context, diagnostic=diagnostic
    )
    if discovered:
        log_event(logger, "teams_channel_discovered_not_connected", **safe_context)


async def handle_conversation_update(context: TurnContext, state: TurnState) -> None:
    """Safely route Teams conversation updates without SDK subtype selectors."""
    activity = context.activity
    raw_diagnostic = _conversation_update_diagnostic(activity)
    log_event(logger, "teams_conversation_update_received", **raw_diagnostic)

    diagnostic = channel_metadata_diagnostic(activity)
    activity_context = extract_teams_context(activity)
    event_type = (diagnostic["event_type"] or "").lower()
    if event_type == "channelcreated":
        discovered = await discover_channel_from_activity(
            activity,
            explicit_event=True,
            activity_context=activity_context,
            diagnostic=diagnostic,
        )
        log_event(
            logger, "teams_channel_discovered_not_connected",
            tenant_id=activity_context["tenantId"],
            team_id=activity_context["teamId"],
            channel_id=activity_context["channelId"],
            conversation_id=activity_context["conversationId"],
            event_type=diagnostic["event_type"],
            result="persisted" if discovered else "persistence_failed",
            reason="explicit_channel_install_required",
        )
        return

    if event_type in {"channeldeleted", "channelremoved"}:
        await discover_channel_from_activity(
            activity,
            available=False,
            explicit_event=True,
            activity_context=activity_context,
            diagnostic=diagnostic,
        )
        return

    if event_type == "channelmemberadded":
        await handle_channel_member_added(context, state)
        return

    await discover_channel_from_activity(
        activity, activity_context=activity_context, diagnostic=diagnostic
    )

    # Team-scoped member/lifecycle conversation updates may refresh installation
    # metadata. No conversation-update path creates a destination.
    await register_installation_from_activity(activity)

    log_event(
        logger,
        "teams_conversation_update_completed",
        team_id=activity_context["teamId"],
        channel_id=activity_context["channelId"],
        tenant_id=activity_context["tenantId"],
    )


def _extract_destination(turn_context: TurnContext) -> ActionDestination:
    """Compatibility wrapper for the action destination parser."""
    return adaptive_card_actions.extract_destination(turn_context.activity)


def _extract_actor(turn_context: TurnContext) -> ActionActor:
    """Compatibility wrapper for the action actor parser."""
    return adaptive_card_actions.extract_actor(turn_context.activity)


def register_handlers() -> None:
    @agent_app.activity(ActivityTypes.installation_update)
    async def on_installation_update(context: TurnContext, state: TurnState) -> None:
        await handle_installation_update(context, state)

    @agent_app.activity(ActivityTypes.conversation_update)
    async def on_conversation_update(context: TurnContext, state: TurnState) -> None:
        await handle_conversation_update(context, state)

    @agent_app.activity(ActivityTypes.message)
    async def on_message(context: TurnContext, state: TurnState) -> None:
        await handle_message(context, state)

    @agent_app.activity(ActivityTypes.invoke)
    async def on_invoke(context: TurnContext, state: TurnState) -> None:
        await handle_invoke(context, state)


async def handle_invoke(context: TurnContext, state: TurnState) -> None:
    """Process an invoke activity and send its synchronous SDK response."""
    response = await adaptive_card_actions.process_invoke(
        context.activity,
        n8n_service=n8n_service,
        idempotency_store=idempotency_store,
    )
    await context.send_activity(
        _invoke_response_activity(response)
    )


def _invoke_response_activity(invoke_response: InvokeResponse):
    from microsoft_agents.activity import Activity

    return Activity(type=ActivityTypes.invoke_response, value=invoke_response)


def _adaptive_card_response(**kwargs) -> dict:
    """Compatibility wrapper for the JSON-ready Adaptive Card response."""
    return adaptive_card_actions.adaptive_card_response(**kwargs)
