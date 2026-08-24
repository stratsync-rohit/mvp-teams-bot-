"""Internal endpoint for resolving a proactive Teams channel route."""
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.routers.notifications import _verify_internal_api_key
from app.services.conversation_service import conversation_service

router = APIRouter()


class ChannelResolutionRequest(BaseModel):
    tenantId: str = Field(min_length=1)
    teamId: str = Field(min_length=1)
    channelId: str = Field(min_length=1)
    serviceUrl: str = Field(min_length=1)


@router.post("/api/internal/teams/resolve-channel-conversation")
async def resolve_channel_conversation(
    payload: ChannelResolutionRequest,
    x_internal_api_key: str | None = Header(default=None),
) -> dict:
    _verify_internal_api_key(x_internal_api_key)
    conversation_id = await conversation_service.resolve_channel_conversation(
        tenant_id=payload.tenantId, team_id=payload.teamId,
        channel_id=payload.channelId, service_url=payload.serviceUrl,
    )
    return {"conversationId": conversation_id}
