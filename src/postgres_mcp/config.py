from typing import Any

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from postgres_mcp.mcp_types import AccessMode, MountMode, TransportConfig


# Error messages for validation
_STDIO_ALL_MUST_BE_STDIO_MSG = (
    "If at least one server uses transport='stdio', all servers must use transport='stdio' and mount_mode='tool'."
)

_STDIO_ALL_MUST_BE_TOOL_MSG = (
    "If at least one server uses transport='stdio', "
    "all servers must be in mount_mode='tool' mode and transport='stdio'. "
)


class DatabaseConfig(BaseModel):
    """MCP server configuration."""

    database_uri: SecretStr = Field(description="Database connection URL")
    transport: TransportConfig = Field(default="http", description="Transport for the server")
    mount_mode: MountMode = Field(default="tool", description="Mount the server as a tool or an endpoint")
    extra_kwargs: dict[str, str] = Field(default_factory=dict, description="Extra keyword arguments")
    access_mode: AccessMode = Field(default=AccessMode.RESTRICTED, description="Access mode for the server")
    # Connection pool settings
    pool_min_size: int = Field(default=1, description="Minimum number of connections in the pool")
    pool_max_size: int = Field(default=5, description="Maximum number of connections in the pool")
    safe_sql_timeout: int = Field(default=30, description="Timeout in seconds for SafeSqlDriver (RESTRICTED mode)")


class AppSettings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )
    name: str = Field(default="postgres-fastmcp", description="Server name")
    mount_point: str = Field(default="mcp", description="Default mount point")
    mask_error_details: bool = Field(default=True, description="Mask error details")
    servers: dict[str, DatabaseConfig] = Field(..., description="Servers configuration")
    host: str = Field(default="127.0.0.1", description="Host to bind the server to")
    port: int = Field(default=8000, description="Port to bind the server to")
    workers: int = Field(default=1, description="Number of workers to run")
    suppress_deprecation_warnings: bool = Field(
        default=True, description="Suppress deprecation warnings from websockets and other dependencies"
    )

    @model_validator(mode="after")
    def validate_transport_and_mount_mode(self) -> "AppSettings":
        """Validate compatibility of transport and mount_mode for all servers.

        Rules:
        - If at least one server uses transport='stdio',
          all servers must use transport='stdio' and mount_mode='tool'
        """
        has_stdio = any(server.transport == "stdio" for server in self.servers.values())

        # If there is stdio, all must be stdio and tool
        if has_stdio:
            for server_name, server in self.servers.items():
                if server.transport != "stdio" or server.mount_mode != "tool":
                    error_msg = f"Server '{server_name}': {_STDIO_ALL_MUST_BE_STDIO_MSG}"
                    raise ValueError(error_msg)

        return self

    @property
    def stdio(self) -> bool:
        """Indicate whether to run the server in stdio mode.

        Returns:
            True if at least one server uses transport='stdio'.
            After validation, if at least one is stdio, then all servers use stdio.
        """
        # After validation, if there is stdio, then all are stdio, so we can check the first server
        if not self.servers:
            return False
        first_server = next(iter(self.servers.values()))
        return first_server.transport == "stdio"


# Usage example:
# Important: if at least one server uses transport='stdio',
# all servers must use transport='stdio' and mount_mode='tool'
config_dict: dict[str, Any] = {
    "name": "postgres-fastmcp",
    "mask_error_details": True,
    "mount_point": "mcp",
    "servers": {
        "postgres": {
            "database_uri": "postgresql://user:pass@localhost:5432/dbname",
            "transport": "stdio",
            "mount_mode": "tool",
        },
        "analytics": {
            "database_uri": "postgresql://user:pass@analytics:5432/analytics",
            "transport": "stdio",  # Must be stdio if postgres uses stdio
            "mount_mode": "tool",  # Must be tool if postgres uses stdio
        },
        "statistics": {
            "database_uri": "postgresql://user:pass@analytics:5432/analytics",
            "transport": "stdio",  # Must be stdio if postgres uses stdio
            "mount_mode": "tool",  # Must be tool if postgres uses stdio
        },
    },
}

app_settings = AppSettings(**config_dict)
