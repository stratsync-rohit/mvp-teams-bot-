"""Internal endpoints for resolving proactive Teams metadata and routes."""
from fastapi import APIRouter, Header

from app.schemas.teams import ChannelResolutionRequest
from app.services.conversation_service import conversation_service
from app.utils.internal_auth import verify_internal_api_key

router = APIRouter()


@router.post("/api/internal/teams/resolve-channel-conversation")
async def resolve_channel_conversation(
    payload: ChannelResolutionRequest,
    x_internal_api_key: str | None = Header(default=None),
) -> dict:
    verify_internal_api_key(x_internal_api_key)
    conversation_id = await conversation_service.resolve_channel_conversation(
        tenant_id=payload.tenantId, team_id=payload.teamId,
        channel_id=payload.channelId, service_url=payload.serviceUrl,
    )
    return {"conversationId": conversation_id}
