"""
FastAPI application entrypoint for the Risk Notification Teams Bot.

Routes:
  GET  /health              - liveness check
  POST /api/notifications   - called by n8n (initial + action-result payloads)
  POST /api/messages        - Microsoft Teams activity endpoint (Bot/Agents protocol)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from microsoft_agents.hosting.fastapi import (
    jwt_authorization_decorator,
    start_agent_process,
)

from app.bot.activity_handler import register_handlers
from app.bot.teams_bot import adapter, agent_app, agent_auth_configuration
from app.config import get_settings
from app.routers import health, notifications
from app.utils.logger import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)

# Register AgentApplication routes (conversationUpdate capture, Adaptive
# Card action handling) once at import time.
register_handlers()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting %s (env=%s, teams_credentials_configured=%s)",
        settings.APP_NAME,
        settings.APP_ENV,
        settings.teams_credentials_configured,
    )
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)

# Used by JwtAuthorizationMiddleware / jwt_authorization_decorator to
# validate inbound Teams JWTs on POST /api/messages.
app.state.agent_configuration = agent_auth_configuration

app.include_router(health.router)
app.include_router(notifications.router)


@app.post("/api/messages")
@jwt_authorization_decorator
async def messages(request: Request) -> Response:
    """
    Microsoft Teams sends all bot activities (messages, Adaptive Card
    Action.Execute invokes, conversationUpdate installs, etc.) here.

    ``jwt_authorization_decorator`` validates the inbound JWT against
    ``app.state.agent_configuration`` (the current Microsoft-supported
    auth mechanism) *before* the activity is processed, populating
    ``request.state.claims_identity``. Without it, CloudAdapter silently
    falls back to an anonymous identity, which must never happen in
    production. Anonymous access is only permitted when
    ``AgentAuthConfiguration.anonymous_allowed`` is explicitly set (see
    app/config.py - development only, and only when no Microsoft App
    credentials are configured).
    """
    response = await start_agent_process(request, agent_app, adapter)
    return response if response is not None else Response(status_code=200)
