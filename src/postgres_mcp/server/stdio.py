"""STDIO server implementation."""

from __future__ import annotations

from postgres_mcp.config import Settings, settings
from postgres_mcp.enums import TransportConfig
from postgres_mcp.logger import get_logger
from postgres_mcp.server.base import BaseServerBuilder


logger = get_logger(__name__)


class StdioServerBuilder(BaseServerBuilder):
    """STDIO server builder for FastMCP.

    Encapsulates STDIO server creation and configuration logic.
    """

    async def run(self) -> None:
        """Run STDIO server.

        Implementation of abstract method from BaseServerBuilder.
        """
        # Register tool mode servers
        self.register_tool_mode_servers(transport_type=TransportConfig.STDIO)

        # Run FastMCP server in stdio mode
        # Disable banner and set log_level to CRITICAL to suppress all FastMCP logging
        # (including startup messages) to avoid interfering with MCP protocol
        await self.main_mcp.run_stdio_async(show_banner=False, log_level="CRITICAL")


async def run_stdio(config: Settings | None = None) -> None:
    """Run server in stdio mode with lifecycle management.

    Creates ToolManager instances according to config, initializes database connections
    and registers tools.

    Args:
        config: Application configuration. If not provided, uses global settings.
    """
    runtime_settings = config if config is not None else settings

    try:
        builder = StdioServerBuilder(runtime_settings)
        await builder.run()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")
        raise
