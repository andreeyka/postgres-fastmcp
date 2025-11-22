"""Application configuration and settings."""

from __future__ import annotations

import contextlib
import json
import warnings
from pathlib import Path
from typing import Any, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from postgres_fastmcp.config.database import DatabaseConfig
from postgres_fastmcp.config.fastmcp import FastMCPSettings
from postgres_fastmcp.config.keycloak import KeycloakConfig
from postgres_fastmcp.config.redis import RedisConfig
from postgres_fastmcp.config.server import ServerSettings
from postgres_fastmcp.enums import TransportConfig, TransportHttpApp


# Re-export for convenience
__all__ = ["DatabaseConfig", "KeycloakConfig", "Settings", "get_settings", "settings"]


class Settings(BaseSettings):
    """Application settings.

    Automatically loads configuration from:
    - Environment variables
    - .env file (if exists)
    - config.json file (if exists)
    - Default values

    Example environment variables:
        MCP_SERVER_HOST=0.0.0.0
        MCP_SERVER_PORT=8000
        MCP_SERVER_TRANSPORT=http
        MCP_FASTMCP_SERVER_NAME=postgres-fastmcp
        MCP_DATABASES__POSTGRES__DATABASE_URI=postgresql://user:pass@localhost:5432/dbname
        MCP_DATABASES__POSTGRES__ENDPOINT=true
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="MCP_",
        env_nested_delimiter="__",
    )

    # Server settings
    server: ServerSettings = Field(default_factory=ServerSettings)
    # FastMCP settings
    fastmcp: FastMCPSettings = Field(default_factory=FastMCPSettings)
    # Keycloak authentication
    keycloak: KeycloakConfig | None = Field(
        default=None,
        description="Keycloak authentication configuration.",
    )
    # Redis configuration
    redis: RedisConfig = Field(default_factory=RedisConfig)
    # Databases configuration
    databases: dict[str, DatabaseConfig] = Field(..., description="Databases configuration")

    @model_validator(mode="after")
    def validate_keycloak_config(self) -> Self:
        """Create KeycloakConfig from environment variables if not already set.

        Attempts to create KeycloakConfig from environment variables.
        If environment variables are missing, leaves keycloak as None.
        """
        # Only create KeycloakConfig if not already set
        if self.keycloak is None:
            with contextlib.suppress(Exception):
                self.keycloak = KeycloakConfig()
        return self

    @model_validator(mode="after")
    def validate_transport_and_streamable(self) -> Self:
        """Validate transport compatibility for all servers.

        Rules:
        - If transport='stdio', server transport parameter is ignored
        - If transport='http' and endpoint=True, server transport must be 'http', 'streamable-http', or None
        - If endpoint=False, server transport is ignored
        """
        # Validate server transport values only for servers with endpoint=True
        if self.server.transport == TransportConfig.HTTP and self.databases:
            valid_transports = {TransportHttpApp.HTTP.value, TransportHttpApp.STREAMABLE_HTTP.value, None}
            for server_name, server_config in self.databases.items():
                # Only validate transport if endpoint=True
                if server_config.endpoint and server_config.transport not in valid_transports:
                    warnings.warn(
                        f"Server '{server_name}' has invalid transport '{server_config.transport}'. "
                        f"Must be 'http' or 'streamable-http'. Using global transport as default.",
                        UserWarning,
                        stacklevel=2,
                    )
                    server_config.transport = None

        return self

    @property
    def name(self) -> str:
        """Get server name from fastmcp settings.

        Returns:
            Server name.
        """
        return self.fastmcp.server_name

    @property
    def endpoint(self) -> str:
        """Get endpoint path from server settings.

        Returns:
            Endpoint path.
        """
        return self.server.endpoint

    @property
    def mask_error_details(self) -> bool:
        """Get mask_error_details from fastmcp settings.

        Returns:
            Mask error details flag.
        """
        return self.fastmcp.mask_error_details

    @property
    def transport(self) -> TransportConfig:
        """Get transport from server settings.

        Returns:
            Transport configuration.
        """
        return self.server.transport

    @property
    def host(self) -> str:
        """Get host from server settings.

        Returns:
            Host address.
        """
        return self.server.host

    @property
    def port(self) -> int:
        """Get port from server settings.

        Returns:
            Port number.
        """
        return self.server.port

    @property
    def workers(self) -> int:
        """Get workers from server settings.

        Returns:
            Number of workers.
        """
        return self.server.workers

    @property
    def stdio(self) -> bool:
        """Check if server should run in stdio mode.

        Returns:
            True if transport='stdio', False otherwise.
        """
        return self.server.transport == TransportConfig.STDIO

    @property
    def tool_mode_servers(self) -> dict[str, DatabaseConfig]:
        """Get all servers (all servers are in tool mode now).

        Returns:
            Dictionary with all server configurations.
            When transport='stdio', all servers are considered in tool mode.
        """
        return self.databases

    @property
    def tool_mode_streamable(self) -> bool:
        """Get streamable value for main endpoint servers.

        Returns:
            True if main endpoint servers use streamable-http, False otherwise.
            Returns False if there are no servers or if transport is stdio.
        """
        if not self.databases or self.server.transport == TransportConfig.STDIO:
            return False
        # Check servers with endpoint=False (mounted in main endpoint)
        main_endpoint_servers = [s for s in self.databases.values() if not s.endpoint]
        if not main_endpoint_servers:
            return False
        # Use first server's transport (all should be the same for main endpoint)
        # If transport is None, default to non-streamable (http)
        first_server_transport = main_endpoint_servers[0].transport
        if first_server_transport is None:
            return False
        return first_server_transport == TransportHttpApp.STREAMABLE_HTTP.value

    @property
    def server_names(self) -> list[str]:
        """Get list of all server names.

        Returns:
            List of all server names.
        """
        return list(self.databases.keys())


def _load_json_config(json_path: Path) -> dict[str, Any] | None:
    """Load configuration from JSON file.

    Args:
        json_path: Path to JSON file.

    Returns:
        Configuration dictionary or None if file not found.
    """
    if not json_path.exists():
        return None

    try:
        with json_path.open(encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
            return data
    except (json.JSONDecodeError, OSError):
        return None


def get_settings(**overrides: Any) -> Settings:
    """Factory function to create settings instance.

    Loads configuration in the following priority order:
    1. **overrides parameters (highest priority)
    2. config.json file (if exists)
    3. Environment variables
    4. .env file (if exists)
    5. Default values from class

    Args:
        **overrides: Parameters to override default values.

    Returns:
        Settings instance with loaded configuration.

    Examples:
        >>> settings = get_settings()
        >>> test_settings = get_settings(server={"host": "127.0.0.1", "port": 9000})
    """
    # Try to find config.json in current directory
    json_config = _load_json_config(Path("config.json"))

    # If overrides provided, use them (highest priority)
    if overrides:
        if json_config:
            # Merge JSON config with overrides (overrides take priority)
            merged_config = {**json_config, **overrides}
            return Settings(**merged_config)
        return Settings(**overrides)

    # If JSON config exists, use it
    if json_config:
        return Settings(**json_config)

    # Otherwise use standard BaseSettings loading (env, .env, defaults)
    return Settings()


settings = get_settings()
