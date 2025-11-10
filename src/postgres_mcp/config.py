"""Application configuration."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from postgres_mcp.enums import AccessMode, TransportConfig


class DatabaseConfig(BaseModel):
    """Database server configuration."""

    database_uri: SecretStr = Field(description="Database connection URL")
    endpoint: bool = Field(
        default=False,
        description=(
            "DEPRECATED: Endpoint mode removed. All servers are mounted with prefixes. "
            "This parameter is ignored and kept for backward compatibility."
        ),
    )
    streamable: bool = Field(
        default=False,
        description=(
            "Use streamable-http transport for this server (only for HTTP transport). "
            "All servers must have the same streamable value."
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
    table_prefix: str | None = Field(
        default=None,
        description=(
            "Optional table name prefix for user_* modes. "
            "If set, only tables/views/sequences with names starting with this prefix are accessible. "
            "Works only for USER_RO and USER_RW access modes. "
            "Ignored for admin modes."
        ),
    )
    tool_name_prefix: bool = Field(
        default=True,
        description=(
            "If True, adds prefix to tool names based on database server name. "
            "This prevents tool name conflicts when multiple MCP servers are connected to the same agent. "
            "For example, if server name is 'app1', tool 'list_schemas' becomes 'app1_list_schemas'. "
            "If False, tools keep their original names."
        ),
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
    host: str = Field(default="127.0.0.1", description="Host to bind the server to")
    port: int = Field(default=8000, description="Port to bind the server to")
    workers: int = Field(default=1, description="Number of workers to run")
    deprecation_warnings: bool = Field(default=True, description="Suppress deprecation warnings")

    @model_validator(mode="after")
    def validate_transport_and_streamable(self) -> Settings:
        """Validate transport and streamable compatibility for all servers.

        Rules:
        - If transport='stdio', streamable parameter is ignored
        - If transport='http', all servers should have the same streamable value
        """
        # If transport='http', check that all servers have the same streamable value
        # If values differ, issue a warning and set streamable=False for all
        if self.transport == TransportConfig.HTTP and self.databases:
            first_streamable = next(iter(self.databases.values())).streamable
            has_different_values = any(server.streamable != first_streamable for server in self.databases.values())

            if has_different_values:
                warnings.warn(
                    "Servers have different streamable values. All servers will use streamable=False.",
                    UserWarning,
                    stacklevel=2,
                )
                # Set streamable=False for all servers
                for server in self.databases.values():
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
        """Get all servers (all servers are in tool mode now).

        Returns:
            Dictionary with all server configurations.
            When transport='stdio', all servers are considered in tool mode.
        """
        return self.databases

    @property
    def tool_mode_streamable(self) -> bool:
        """Get streamable value for all servers.

        Returns:
            Streamable value for servers.
            All servers have the same streamable value (validated).
            Returns False if there are no servers.
        """
        if not self.databases:
            return False
        return next(iter(self.databases.values())).streamable

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
        >>> test_settings = get_settings(transport="stdio", port=9000)
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
