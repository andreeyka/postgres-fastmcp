"""Keycloak authentication configuration."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KeycloakConfig(BaseSettings):
    """Keycloak authentication configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="MCP_KEYCLOAK_",
    )

    enabled: bool = Field(default=False, description="Enable Keycloak OAuth2 authentication")
    realm: str = Field(..., description="Keycloak realm name")
    server_url: str = Field(
        ..., description="Keycloak server URL (set via MCP_KEYCLOAK_SERVER_URL environment variable)"
    )
    client_id: str = Field(..., description="Keycloak client ID (required if enabled)")
    audience: str | None = Field(default=None, description="Keycloak audience")
    required_scopes: list[str] = Field(
        default_factory=list, description="Required OAuth scopes (optional, validates if provided)"
    )
