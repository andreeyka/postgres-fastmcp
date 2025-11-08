"""STDIO server implementation."""

from __future__ import annotations

from devtools import debug
from fastmcp import FastMCP

from postgres_mcp.config import app_settings
from postgres_mcp.logger import get_logger
from postgres_mcp.server.lifespan import fastmcp_lifespan
from postgres_mcp.tool import Tools


logger = get_logger(__name__)


async def run_stdio() -> None:
    """Run server in stdio mode with lifecycle management via FastMCP lifespan.

    FastMCP will automatically call the lifespan when run_stdio_async() is called,
    which will create Tools instances and register them on the server.
    """
    try:
        # Create FastMCP server with lifespan that manages Tools instances
        main_mcp = FastMCP(name=app_settings.name, lifespan=fastmcp_lifespan)

        # Create Tools instances and sub-servers before running
        # They will be stored in _tools_instances_storage and managed by lifespan's AsyncExitStack

        # Mount all servers to main_mcp with prefixes
        for server_name, server_config in app_settings.servers.items():
            tools = Tools(server_config)
            sub_server = FastMCP(server_name, lifespan=fastmcp_lifespan)
            tools.register_tools(sub_server)
            debug(await sub_server.get_tools())
            main_mcp.mount(sub_server, prefix=server_name)
            logger.info(
                "Server %s: Mounted with prefix %s -> stdio (transport: %s)",
                server_name,
                server_name,
                server_config.transport,
            )

        # Run FastMCP server in stdio mode
        # FastMCP will automatically call lifespan, which will:
        # 1. Reuse already created Tools instances
        # 2. Manage their lifecycle through AsyncExitStack
        print("qqqq")
        await main_mcp.run_stdio_async(show_banner=False)
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")
        raise
