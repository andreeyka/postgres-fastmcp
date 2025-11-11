"""Base class for server creation and registration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from fastmcp import FastMCP

from postgres_mcp.enums import TransportConfig
from postgres_mcp.logger import get_logger
from postgres_mcp.server.lifespan import LifespanManager


if TYPE_CHECKING:
    from postgres_mcp.config import Settings

logger = get_logger(__name__)


class BaseServerBuilder(ABC):
    """Base class for building servers of different transport types.

    Encapsulates common logic for creating FastMCP server, managing lifecycle,
    and registering tool mode servers.
    """

    def __init__(self, config: Settings) -> None:
        """Initialize base server builder.

        Args:
            config: Application configuration.
        """
        self.config = config
        self.lifespan_manager = LifespanManager(config)
        self.lifespan = self.lifespan_manager.create_lifespan()
        self.main_mcp = FastMCP(name=config.name, lifespan=self.lifespan)

    def register_tool_mode_servers(self, transport_type: TransportConfig) -> list[str]:
        """Register tool mode servers on the main FastMCP server.

        For stdio mode: registers ALL servers (endpoint parameter is ignored).
        For HTTP mode: only registers servers with endpoint=False (mounted in main endpoint via Server Composition).
        Servers with endpoint=True are handled separately as individual HTTP endpoints.

        - Single server: tools are registered directly on main_mcp (no prefix)
        - Multiple servers: each server is mounted with its name as prefix (Server Composition)

        Args:
            transport_type: Transport type for logging.

        Returns:
            List of registered server names.

        Raises:
            RuntimeError: If ToolManager is not found for a server.
        """
        mounted_servers: list[str] = []

        # For stdio mode, register ALL servers (endpoint parameter is ignored)
        # For HTTP mode, only register servers with endpoint=False
        if transport_type == TransportConfig.STDIO:
            tool_mode_servers = self.config.tool_mode_servers
            # Warn if any servers have endpoint=True (this parameter is ignored in stdio mode)
            servers_with_endpoint = [name for name, config in tool_mode_servers.items() if config.endpoint]
            if servers_with_endpoint:
                logger.warning(
                    "In stdio mode, the 'endpoint' parameter is ignored. "
                    "All servers will be registered. "
                    "Servers with endpoint=true: %s",
                    ", ".join(servers_with_endpoint),
                )
        else:
            # Filter servers with endpoint=False (mounted in main endpoint)
            tool_mode_servers = {
                name: config for name, config in self.config.tool_mode_servers.items() if not config.endpoint
            }
        is_single_server = len(tool_mode_servers) == 1

        for server_name in tool_mode_servers:
            tools = self.lifespan_manager.get_tools(server_name)
            if tools is None:
                error_msg = f"ToolManager instance not found for server {server_name}"
                raise RuntimeError(error_msg)

            # Get tool prefix from config if specified, otherwise use default behavior
            server_config = tool_mode_servers[server_name]
            tool_prefix: str | None = (
                server_config.tool_prefix if server_config.tool_prefix else (None if is_single_server else server_name)
            )

            if is_single_server:
                # Single server: mount directly on main server
                tools.register_tools(self.main_mcp, prefix=tool_prefix)
                if transport_type == TransportConfig.STDIO:
                    if tool_prefix:
                        logger.info(
                            "Server %s: Mounted directly on main server with prefix '%s' -> stdio",
                            server_name,
                            tool_prefix,
                        )
                    else:
                        logger.info(
                            "Server %s: Mounted directly on main server (no prefix) -> stdio",
                            server_name,
                        )
                elif tool_prefix:
                    logger.info(
                        "Server %s: Mounted directly on main server with prefix '%s' -> /%s",
                        server_name,
                        tool_prefix,
                        self.config.endpoint,
                    )
                else:
                    logger.info(
                        "Server %s: Mounted directly on main server (no prefix) -> /%s",
                        server_name,
                        self.config.endpoint,
                    )
            else:
                # Multiple servers: mount with prefix using Server Composition
                sub_server = FastMCP(name=server_name)
                tools.register_tools(sub_server, prefix=tool_prefix)
                self.main_mcp.mount(sub_server, prefix=server_name)
                if transport_type == TransportConfig.STDIO:
                    logger.info(
                        "Server %s: Mounted with prefix %s -> stdio",
                        server_name,
                        server_name,
                    )
                else:
                    logger.info(
                        "Server %s: Mounted with prefix %s -> /%s",
                        server_name,
                        server_name,
                        self.config.endpoint,
                    )
            mounted_servers.append(server_name)

        return mounted_servers

    @abstractmethod
    async def run(self) -> None:
        """Run the server.

        Must be implemented in subclasses for specific transport types.
        """
        raise NotImplementedError
