"""HTTP server implementation."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import uvicorn
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount

from postgres_mcp.config import Settings, settings
from postgres_mcp.logger import get_logger
from postgres_mcp.mcp_types import TransportConfig, TransportHttpApp
from postgres_mcp.server.base import BaseServerBuilder


if TYPE_CHECKING:
    from postgres_mcp.config import Settings


logger = get_logger(__name__)


class HttpServerBuilder(BaseServerBuilder):
    """HTTP server builder for FastMCP.

    Encapsulates HTTP application creation and configuration logic with support
    for different server mounting modes (tool mode and endpoint mode).
    """

    def __init__(self, config: Settings) -> None:
        """Initialize HTTP server builder.

        Args:
            config: Application configuration.
        """
        super().__init__(config)

    @cached_property
    def _mounted_tool_mode_server_names(self) -> list[str]:
        """List of tool mode server names after mounting.

        Mounts tool mode servers on the main FastMCP server on first access.

        Returns:
            List of server names that were mounted.
        """
        return self.register_tool_mode_servers(transport_type=TransportConfig.HTTP)

    @cached_property
    def _created_endpoint_servers(self) -> list[tuple[str, FastMCP, bool]]:
        """List of created endpoint servers for individual endpoints.

        Creates endpoint servers on first access.

        Returns:
            List of tuples (server_name, sub_server, streamable).
        """
        endpoint_servers: list[tuple[str, FastMCP, bool]] = []
        for server_name, server_config in self.config.endpoint_mode_servers.items():
            tools_instance = self.lifespan_manager.get_tools(server_name)
            if tools_instance is None:
                error_msg = f"Tools instance not found for server {server_name}"
                raise RuntimeError(error_msg)
            sub_server = FastMCP(name=server_name)
            tools_instance.register_tools(sub_server)
            streamable = server_config.streamable
            endpoint_servers.append((server_name, sub_server, streamable))
            logger.info(
                "Server %s: Endpoint mode -> /%s/%s (streamable: %s)",
                server_name,
                server_name,
                self.config.endpoint,
                streamable,
            )
        return endpoint_servers

    @cached_property
    def _main_app(self) -> Starlette:
        """Main FastMCP HTTP application.

        Returns:
            Main Starlette application with lifespan.
        """
        # Use streamable transport for tool mode servers if configured
        streamable = self.config.tool_mode_streamable
        transport = TransportHttpApp.STREAMABLE_HTTP if streamable else TransportHttpApp.HTTP
        return self.main_mcp.http_app(path="/", transport=transport.value)

    def _build_app_with_endpoints(self) -> Starlette:
        """Build HTTP application with separate endpoints for each server.

        Returns:
            Configured Starlette application with all routes.
        """
        routes = []
        use_prefix = self.config.should_mount_with_prefix

        # Separate endpoints for endpoint mode servers
        for server_name, sub_server, streamable in self._created_endpoint_servers:
            transport = TransportHttpApp.STREAMABLE_HTTP if streamable else TransportHttpApp.HTTP
            endpoint_app = sub_server.http_app(path=f"/{self.config.endpoint}", transport=transport.value)

            if use_prefix:
                # Mount with server name prefix: /{server_name}/mcp
                routes.append(Mount(f"/{server_name}", app=endpoint_app))
                logger.info(
                    "Endpoint /%s/%s created for server %s (streamable: %s)",
                    server_name,
                    self.config.endpoint,
                    server_name,
                    streamable,
                )
            else:
                # Mount directly to /mcp without prefix
                routes.append(Mount(f"/{self.config.endpoint}", app=endpoint_app))
                logger.info(
                    "Endpoint /%s created for server %s (streamable: %s, no prefix)",
                    self.config.endpoint,
                    server_name,
                    streamable,
                )

        # Common endpoint /mcp with all tool mode servers (if any)
        if self._mounted_tool_mode_server_names:
            streamable = self.config.tool_mode_streamable
            transport_type = TransportHttpApp.STREAMABLE_HTTP if streamable else TransportHttpApp.HTTP
            routes.append(Mount(f"/{self.config.endpoint}", app=self._main_app))
            servers_list = ", ".join(self._mounted_tool_mode_server_names)
            logger.info(
                "Root endpoint /%s created for tool mode servers: %s (transport: %s)",
                self.config.endpoint,
                servers_list,
                transport_type.value,
            )

        # Use shared lifespan for parent Starlette application
        # Required for proper FastMCP StreamableHTTPSessionManager operation
        return Starlette(routes=routes, lifespan=self.lifespan)

    def _build_app_tool_mode(self) -> Starlette:
        """Build HTTP application with all servers in tool mode.

        Returns:
            Configured Starlette application.
        """
        servers_list = ", ".join(self._mounted_tool_mode_server_names)
        streamable = self.config.tool_mode_streamable
        transport_type = TransportHttpApp.STREAMABLE_HTTP if streamable else TransportHttpApp.HTTP
        logger.info(
            "Root endpoint /%s created for tool mode servers: %s (transport: %s)",
            self.config.endpoint,
            servers_list,
            transport_type.value,
        )

        # FastMCP already manages lifespan through http_app()
        transport = TransportHttpApp.STREAMABLE_HTTP if streamable else TransportHttpApp.HTTP
        return self.main_mcp.http_app(path=f"/{self.config.endpoint}", transport=transport.value)

    def build(self) -> Starlette:
        """Build and configure HTTP application.

        Returns:
            Configured Starlette application ready to run.
        """
        # Check if there are servers in endpoint mode
        if self.config.endpoint_mode_servers:
            # Mixed mode: servers in endpoint mode
            # Properties will be called automatically when used in _build_app_with_endpoints
            return self._build_app_with_endpoints()

        # All servers in tool mode
        # Property will be called automatically when used in _build_app_tool_mode
        return self._build_app_tool_mode()

    async def run(self) -> None:
        """Запустить HTTP сервер.

        Реализация абстрактного метода из BaseServerBuilder.
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
            log_config=None,  # Disable default logging configuration
            workers=self.config.workers,
        )
        uvicorn_server = uvicorn.Server(uvicorn_config)
        await uvicorn_server.serve()


async def run_http(config: Settings | None = None) -> None:
    """Run server in HTTP mode with lifecycle management via FastMCP lifespan.

    For single server without endpoint mode, uses FastMCP's direct HTTP server.
    For multiple servers or endpoint mode, uses HttpServerBuilder with Starlette.

    Args:
        config: Application configuration. If not provided, uses global settings.
    """
    runtime_settings = config if config is not None else settings

    # Check if we can use simplified single-server mode
    is_single_server = len(runtime_settings.databases) == 1
    has_endpoint_mode = bool(runtime_settings.endpoint_mode_servers)

    logger.info(
        "Starting MCP server: %s, transport: HTTP, host: %s, port: %d",
        runtime_settings.name,
        runtime_settings.host,
        runtime_settings.port,
    )

    try:
        # Simplified path for single server without endpoint mode
        if is_single_server and not has_endpoint_mode:
            # Create builder and register tools
            builder = HttpServerBuilder(runtime_settings)
            builder.register_tool_mode_servers(transport_type=TransportConfig.HTTP)

            # Determine transport type
            streamable = runtime_settings.tool_mode_streamable
            transport = TransportHttpApp.STREAMABLE_HTTP if streamable else TransportHttpApp.HTTP

            # Run directly via FastMCP (similar to stdio)
            await builder.main_mcp.run_http_async(
                transport=transport.value,
                host=runtime_settings.host,
                port=runtime_settings.port,
                path=f"/{runtime_settings.endpoint}",
                show_banner=False,
            )
        else:
            # Complex path: multiple servers or endpoint mode - use HttpServerBuilder
            builder = HttpServerBuilder(runtime_settings)
            await builder.run()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")
        raise
