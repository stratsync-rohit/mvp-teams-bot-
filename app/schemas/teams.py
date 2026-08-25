"""Pydantic contracts for internal Microsoft Teams routing endpoints."""

from pydantic import BaseModel, Field, field_validator

from app.utils.service_url import validate_service_url


class ChannelResolutionRequest(BaseModel):
    tenantId: str = Field(min_length=1)
    teamId: str = Field(min_length=1)
    channelId: str = Field(min_length=1)
    serviceUrl: str = Field(min_length=1)

    @field_validator("serviceUrl")
    @classmethod
    def validate_connector_url(cls, value: str) -> str:
        return validate_service_url(value)
