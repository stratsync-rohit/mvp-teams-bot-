

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
from app.routers import channel_resolution, health, notifications
from app.services.backend_client import (
    close_backend_http_client,
    start_backend_http_client,
)
from app.utils.logger import configure_logging, get_logger, log_event
from app.utils.teams_context import safe_activity_log_fields

settings = get_settings()
configure_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


register_handlers()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting %s (env=%s, teams_credentials_configured=%s)",
        settings.APP_NAME,
        settings.APP_ENV,
        settings.teams_credentials_configured,
    )
    start_backend_http_client()
    try:
        yield
    finally:
        await close_backend_http_client()
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
app.include_router(channel_resolution.router)


# Backward-compatible import seam for callers that used the old private helper.
_safe_activity_log_fields = safe_activity_log_fields


@app.post("/api/messages")
@jwt_authorization_decorator
async def messages(request: Request) -> Response:
    body = await request.json()
    log_event(
        logger,
        "teams_activity_received",
        **_safe_activity_log_fields(body),
    )
  
    response = await start_agent_process(request, agent_app, adapter)
    return response if response is not None else Response(status_code=200)
