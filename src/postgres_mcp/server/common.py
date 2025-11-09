"""Base class for server creation and registration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from fastmcp import FastMCP

from postgres_mcp.logger import get_logger
from postgres_mcp.mcp_types import TransportConfig
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

        Args:
            transport_type: Transport type for logging.

        Returns:
            List of registered server names.

        Raises:
            RuntimeError: If ToolManager is not found for a server.
        """
        mounted_servers: list[str] = []
        use_prefix = self.config.should_mount_with_prefix

        # For stdio all servers are in tool mode, for http - only those not in endpoint mode
        tool_mode_servers = self.config.tool_mode_servers

        for server_name in tool_mode_servers:
            tools = self.lifespan_manager.get_tools(server_name)
            if tools is None:
                error_msg = f"ToolManager instance not found for server {server_name}"
                raise RuntimeError(error_msg)

            if use_prefix:
                # Mount with prefix (server name)
                sub_server = FastMCP(name=server_name)
                tools.register_tools(sub_server)
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
            else:
                # Mount directly on main server without prefix
                tools.register_tools(self.main_mcp)
                if transport_type == TransportConfig.STDIO:
                    logger.info(
                        "Server %s: Mounted directly on main server (no prefix) -> stdio",
                        server_name,
                    )
                else:
                    logger.info(
                        "Server %s: Mounted directly on main server (no prefix) -> /%s",
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
