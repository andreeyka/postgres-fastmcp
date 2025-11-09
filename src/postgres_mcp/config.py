"""Application configuration."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from postgres_mcp.mcp_types import AccessMode, TransportConfig


class DatabaseConfig(BaseModel):
    """Database server configuration."""

    database_uri: SecretStr = Field(description="Database connection URL")
    endpoint: bool = Field(default=False, description="Mount the server as an endpoint (ignored if transport='stdio')")
    streamable: bool = Field(
        default=False,
        description=(
            "Use streamable-http transport for this server (only for HTTP transport). "
            "All tool mode servers must have the same streamable value."
        ),
    )
    extra_kwargs: dict[str, str] = Field(default_factory=dict, description="Extra keyword arguments")
    access_mode: AccessMode = Field(
        default=AccessMode.USER_RO,
        description=(
            "Access mode for the server. "
            "Available modes: USER_RO (only public schema, read-only, basic tools), "
            "USER_RW (only public schema, read-write, basic tools), "
            "ADMIN_RO (all schemas, read-only, all tools), "
            "ADMIN_RW (all schemas, full access, all tools)."
        ),
    )
    # Connection pool settings
    pool_min_size: int = Field(default=1, description="Minimum number of connections in the pool")
    pool_max_size: int = Field(default=5, description="Maximum number of connections in the pool")
    safe_sql_timeout: int = Field(
        default=30, description="Timeout in seconds for SafeSqlDriver (for non-ADMIN_RW modes)"
    )


class Settings(BaseSettings):
    """Application settings.

    Automatically loads configuration from:
    - Environment variables
    - .env file (if exists)
    - Default values

    Example environment variables:
        TRANSPORT=http
        HOST=127.0.0.1
        PORT=8000
        DATABASES__POSTGRES__DATABASE_URI=postgresql://user:pass@localhost:5432/dbname
        DATABASES__POSTGRES__ENDPOINT=true
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )
    name: str = Field(default="postgres-fastmcp", description="Server name")
    endpoint: str = Field(default="mcp", description="Default endpoint path")
    mask_error_details: bool = Field(default=True, description="Mask error details")
    transport: TransportConfig = Field(
        default=TransportConfig.HTTP, description="Global transport type: 'http' or 'stdio'"
    )
    databases: dict[str, DatabaseConfig] = Field(..., description="Databases configuration")
    mount_with_prefix: bool = Field(default=True, description="Mount databases with prefix (server name). ")
    host: str = Field(default="127.0.0.1", description="Host to bind the server to")
    port: int = Field(default=8000, description="Port to bind the server to")
    workers: int = Field(default=1, description="Number of workers to run")
    deprecation_warnings: bool = Field(default=True, description="Suppress deprecation warnings")

    @model_validator(mode="after")
    def validate_transport_and_endpoint(self) -> Settings:
        """Validate transport and endpoint compatibility for all servers.

        Rules:
        - If transport='stdio', endpoint parameter is ignored (all servers work in tool mode)
        - If transport='http', all tool mode servers (endpoint=False) should have the same streamable value
        """
        # If transport='http', check that all tool mode servers have the same streamable value
        # If values differ, issue a warning and set streamable=False for all
        if self.transport == TransportConfig.HTTP:
            tool_mode_servers = [server for server in self.databases.values() if not server.endpoint]
            if tool_mode_servers:
                first_streamable = tool_mode_servers[0].streamable
                has_different_values = any(
                    not server.endpoint and server.streamable != first_streamable for server in self.databases.values()
                )

                if has_different_values:
                    warnings.warn(
                        "Tool mode servers have different streamable values. "
                        "All tool mode servers will use streamable=False.",
                        UserWarning,
                        stacklevel=2,
                    )
                    # Set streamable=False for all tool mode servers
                    for server in self.databases.values():
                        if not server.endpoint:
                            server.streamable = False

        return self

    @property
    def stdio(self) -> bool:
        """Check if server should run in stdio mode.

        Returns:
            True if transport='stdio', False otherwise.
        """
        return self.transport == TransportConfig.STDIO

    @property
    def tool_mode_servers(self) -> dict[str, DatabaseConfig]:
        """Get servers in tool mode.

        Returns:
            Dictionary with tool mode server configurations.
            When transport='stdio', all servers are considered in tool mode regardless of endpoint.
        """
        if self.transport == TransportConfig.STDIO:
            return self.databases
        return {name: config for name, config in self.databases.items() if not config.endpoint}

    @property
    def endpoint_mode_servers(self) -> dict[str, DatabaseConfig]:
        """Get servers in endpoint mode.

        Returns:
            Dictionary with endpoint mode server configurations.
            Returns empty dictionary when transport='stdio'.
        """
        if self.transport == TransportConfig.STDIO:
            return {}
        return {name: config for name, config in self.databases.items() if config.endpoint}

    @property
    def tool_mode_streamable(self) -> bool:
        """Get streamable value for tool mode servers.

        Returns:
            Streamable value for tool mode servers.
            All tool mode servers have the same streamable value (validated).
            Returns False if there are no tool mode servers.
        """
        tool_mode_servers = list(self.tool_mode_servers.values())
        if not tool_mode_servers:
            return False
        return tool_mode_servers[0].streamable

    @property
    def has_endpoint_servers(self) -> bool:
        """Check if there are any servers in endpoint mode.

        Returns:
            True if there are endpoint mode servers, False otherwise.
        """
        return len(self.endpoint_mode_servers) > 0

    @property
    def server_names(self) -> list[str]:
        """Get list of all server names.

        Returns:
            List of all server names.
        """
        return list(self.databases.keys())

    @property
    def should_mount_with_prefix(self) -> bool:
        """Determine if servers should be mounted with prefix.

        Returns:
            True if servers should be mounted with prefix, False to mount directly on main server.
            Returns False if there's only one server and mount_with_prefix=False.
        """
        return not (len(self.databases) == 1 and not self.mount_with_prefix)


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
        >>> test_settings = get_settings(transport="stdio", port=9000)
    """
    # Try to find config.json in current directory
    # Check maybe in other directories like config/config.json or config/postgres_mcp/config.json
    possible_paths = [
        Path("config.json"),
    ]
    json_config = None
    for json_path in possible_paths:
        json_config = _load_json_config(json_path)
        if json_config is not None:
            break

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
