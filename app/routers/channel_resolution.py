"""Internal endpoints for resolving proactive Teams metadata and routes."""
import httpx
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


class TeamNameResolutionRequest(BaseModel):
    tenantId: str = Field(min_length=1)
    teamId: str = Field(min_length=1)
    aadGroupId: str | None = None


class TeamChannelsRequest(BaseModel):
    tenantId: str = Field(min_length=1)
    teamId: str = Field(min_length=1)


async def acquire_graph_token(tenant_id: str) -> str:
    from app.config import get_settings

    settings = get_settings()
    if not settings.teams_credentials_configured:
        raise ValueError("Microsoft credentials are not configured")
    async with httpx.AsyncClient(timeout=settings.BACKEND_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
            data={"client_id": settings.MICROSOFT_APP_ID,
                  "client_secret": settings.MICROSOFT_APP_PASSWORD,
                  "scope": "https://graph.microsoft.com/.default",
                  "grant_type": "client_credentials"},
        )
        response.raise_for_status()
        return response.json()["access_token"]


async def resolve_microsoft_team_name(payload: TeamNameResolutionRequest) -> str | None:
    """Resolve authoritative display metadata with the bot's app credentials."""
    from app.config import get_settings

    settings = get_settings()
    if not settings.teams_credentials_configured:
        return None
    token = await acquire_graph_token(payload.tenantId)
    async with httpx.AsyncClient(timeout=settings.BACKEND_TIMEOUT_SECONDS) as client:
        headers = {"Authorization": f"Bearer {token}"}
        # aadGroupId is the authoritative Entra group object ID and is preferred.
        if payload.aadGroupId:
            response = await client.get(
                f"https://graph.microsoft.com/v1.0/groups/{payload.aadGroupId}",
                params={"$select": "displayName"}, headers=headers,
            )
            if response.status_code != 404:
                response.raise_for_status()
                return response.json().get("displayName")
        response = await client.get(
            f"https://graph.microsoft.com/v1.0/teams/{payload.teamId}",
            params={"$select": "displayName"}, headers=headers,
        )
        response.raise_for_status()
        return response.json().get("displayName")


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


@router.post("/api/internal/teams/resolve-team-name")
async def resolve_team_name(
    payload: TeamNameResolutionRequest,
    x_internal_api_key: str | None = Header(default=None),
) -> dict:
    _verify_internal_api_key(x_internal_api_key)
    try:
        team_name = await resolve_microsoft_team_name(payload)
    except (httpx.HTTPError, KeyError, ValueError):
        team_name = None
    return {"teamName": team_name}


@router.post("/api/internal/teams/list-channels")
async def list_team_channels(
    payload: TeamChannelsRequest,
    x_internal_api_key: str | None = Header(default=None),
) -> dict:
    _verify_internal_api_key(x_internal_api_key)
    from app.config import get_settings
    settings = get_settings()
    token = await acquire_graph_token(payload.tenantId)
    url: str | None = f"https://graph.microsoft.com/v1.0/teams/{payload.teamId}/channels"
    params = {"$select": "id,displayName,membershipType"}
    channels = []
    async with httpx.AsyncClient(timeout=settings.BACKEND_TIMEOUT_SECONDS) as client:
        while url:
            response = await client.get(
                url, params=params if not channels else None,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            body = response.json()
            channels.extend(body.get("value") or [])
            url = body.get("@odata.nextLink")
    return {"channels": channels}
