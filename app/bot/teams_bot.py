"""
Wires up the current Microsoft-supported Teams SDK primitives:

  * ``CloudAdapter``      - handles inbound/outbound channel communication
  * ``AgentApplication``  - decorator-based activity routing (the modern
                             programming model recommended by the SDK,
                             see microsoft_agents.hosting.core.AgentApplication)

These are process-wide singletons, built once at import time and reused by
main.py (for POST /api/messages) and by the proactive sender (for outbound
channel messages).
"""

from __future__ import annotations

from microsoft_agents.hosting.core import AgentApplication, ApplicationOptions, MemoryStorage, TurnState
from microsoft_agents.hosting.fastapi import CloudAdapter

from app.config import get_agent_auth_configuration, get_connection_manager, get_settings

_settings = get_settings()

# The MSAL-based connection manager acquires tokens for outbound requests to
# Microsoft Teams (proactive messages, connector client calls, etc).
connection_manager = get_connection_manager()

adapter = CloudAdapter(connection_manager=connection_manager)

agent_app: AgentApplication[TurnState] = AgentApplication(
    ApplicationOptions(
        adapter=adapter,
        bot_app_id=_settings.MICROSOFT_APP_ID,
        storage=MemoryStorage(),
    ),
    connection_manager=connection_manager,
)

# The AgentAuthConfiguration used to validate inbound JWTs on
# POST /api/messages (wired into FastAPI app.state in app/main.py).
agent_auth_configuration = get_agent_auth_configuration()
