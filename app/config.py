"""
Application configuration.

Loads settings from environment variables / .env using pydantic-settings.

The Microsoft 365 Agents SDK for Python (the current, Microsoft-supported
Teams SDK - NOT the deprecated botbuilder / Bot Framework SDK) natively
expects nested "double underscore" environment variables such as:

    CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID
    CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET
    CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID

Per the project requirements we keep the simpler, requested environment
variable names (MICROSOFT_APP_ID / MICROSOFT_APP_PASSWORD /
MICROSOFT_TENANT_ID) and translate them into an
``AgentAuthConfiguration`` object ourselves in ``get_agent_auth_configuration()``
below, rather than forcing the nested naming convention onto the .env file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- App ----
    APP_NAME: str = "Risk Teams Bot"
    APP_ENV: str = "development"

    HOST: str = "0.0.0.0"
    PORT: int = 3978

    # ---- Microsoft Teams / Microsoft 365 Agents SDK credentials ----
    MICROSOFT_APP_ID: str = ""
    MICROSOFT_APP_PASSWORD: str = ""
    MICROSOFT_TENANT_ID: str = ""

    # ---- n8n ----
    N8N_ACTION_WEBHOOK_URL: str = ""
    N8N_TIMEOUT_SECONDS: int = 15

    # ---- Backend installation registration ----
    BACKEND_BASE_URL: str = "http://localhost:8000"
    BACKEND_TIMEOUT_SECONDS: int = 15

    # ---- Internal security ----
    INTERNAL_API_KEY: str = ""

    # ---- Logging ----
    LOG_LEVEL: str = "INFO"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() in ("development", "dev", "local")

    @property
    def teams_credentials_configured(self) -> bool:
        return bool(self.MICROSOFT_APP_ID and self.MICROSOFT_APP_PASSWORD)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_agent_auth_configuration():
  
    from microsoft_agents.hosting.core import AgentAuthConfiguration, AuthTypes

    settings = get_settings()

    return AgentAuthConfiguration(
        auth_type=AuthTypes.client_secret,
        client_id=settings.MICROSOFT_APP_ID or None,
        client_secret=settings.MICROSOFT_APP_PASSWORD or None,
        tenant_id=settings.MICROSOFT_TENANT_ID or None,
        connection_name="SERVICE_CONNECTION",
        anonymous_allowed=settings.is_development
        and not settings.teams_credentials_configured,
    )


def get_connection_manager():
    """
    Builds the MSAL-based ConnectionManager used by the CloudAdapter to
    acquire tokens for outbound (proactive) messages to Microsoft Teams.
    """
    from microsoft_agents.authentication.msal import MsalConnectionManager

    return MsalConnectionManager(
        connections_configurations={"SERVICE_CONNECTION": get_agent_auth_configuration()},
    )
