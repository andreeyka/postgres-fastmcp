"""HTTP server implementation."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount

from postgres_mcp.config import Settings, settings
from postgres_mcp.enums import TransportConfig, TransportHttpApp
from postgres_mcp.logger import get_logger
from postgres_mcp.server.base import BaseServerBuilder


if TYPE_CHECKING:
    from postgres_mcp.config import Settings


logger = get_logger(__name__)


class HttpServerBuilder(BaseServerBuilder):
    """HTTP server builder for FastMCP.

    Simplified version: all servers are mounted into main_mcp with prefixes (Server Composition).
    All tools are available through a single endpoint with prefixes (native FastMCP behavior).
    """

    def __init__(self, config: Settings) -> None:
        """Initialize HTTP server builder.

        Args:
            config: Application configuration.
        """
        super().__init__(config)

    @cached_property
    def _mounted_server_names(self) -> list[str]:
        """List of server names after mounting.

        - Single server: tools registered directly on main_mcp (no prefix)
        - Multiple servers: each server mounted with prefix (Server Composition)

        Returns:
            List of server names that were mounted.
        """
        return self.register_tool_mode_servers(transport_type=TransportConfig.HTTP)

    def build(self) -> Starlette:
        """Build and configure HTTP application.

        - Single server: tools available directly at /{endpoint}
        - Multiple servers: tools available at /{endpoint} with server name prefixes

        Returns:
            Configured Starlette application ready to run.
        """
        # All servers are mounted into main_mcp with prefixes
        # Property will be called automatically on first access
        servers_list = ", ".join(self._mounted_server_names)
        streamable = self.config.tool_mode_streamable
        transport_type = TransportHttpApp.STREAMABLE_HTTP if streamable else TransportHttpApp.HTTP

        is_single = len(self._mounted_server_names) == 1
        prefix_info = "no prefix" if is_single else "with prefixes"
        logger.info(
            "Endpoint /%s created for servers: %s (transport: %s, %s)",
            self.config.endpoint,
            servers_list,
            transport_type.value,
            prefix_info,
        )

        # Create a single ASGI app from main_mcp
        # Single server: tools at /{endpoint} directly
        # Multiple servers: tools at /{endpoint} with server name prefixes
        transport = TransportHttpApp.STREAMABLE_HTTP if streamable else TransportHttpApp.HTTP
        mcp_app = self.main_mcp.http_app(path=f"/{self.config.endpoint}", transport=transport.value)

        # Create simple Starlette application with one endpoint
        # Use lifespan from mcp_app (as per FastMCP documentation)
        return Starlette(
            routes=[Mount("/", app=mcp_app)],
            lifespan=mcp_app.lifespan,
        )

    async def run(self) -> None:
        """Run HTTP server.

        Implementation of abstract method from BaseServerBuilder.
        """
        server = self.build()

        if not isinstance(server, Starlette):
            error_msg = "Expected Starlette application for HTTP mode"
            raise TypeError(error_msg)

        # Run HTTP application via uvicorn
        # FastMCP automatically calls lifespan through Starlette lifespan, which will:
        # 1. Create ToolManager instances
        # 2. Register them on server(s)
        # 3. Manage their lifecycle
        uvicorn_config = uvicorn.Config(
            server,
            host=self.config.host,
            port=self.config.port,
            log_config=None,
            workers=self.config.workers,
        )
        uvicorn_server = uvicorn.Server(uvicorn_config)
        await uvicorn_server.serve()


async def run_http(config: Settings | None = None) -> None:
    """Run server in HTTP mode with lifecycle management via FastMCP lifespan.

    - Single server: tools available directly at /{endpoint}
    - Multiple servers: tools available at /{endpoint} with server name prefixes

    Args:
        config: Application configuration. If not provided, uses global settings.
    """
    runtime_settings = config if config is not None else settings

    logger.info(
        "Starting MCP server: %s, transport: HTTP, host: %s, port: %d, endpoint: /%s",
        runtime_settings.name,
        runtime_settings.host,
        runtime_settings.port,
        runtime_settings.endpoint,
    )

    try:
        # Always use HttpServerBuilder (similar to stdio mode)
        # All servers are mounted into main_mcp with prefixes
        builder = HttpServerBuilder(runtime_settings)
        await builder.run()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")
        raise
