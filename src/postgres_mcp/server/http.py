"""HTTP server implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from functools import cached_property
from typing import TYPE_CHECKING, Any

import uvicorn
from fastmcp import FastMCP
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

    Supports two mounting modes:
    - Servers with endpoint=False: mounted in main endpoint via FastMCP mount() (Server Composition)
    - Servers with endpoint=True: mounted as separate HTTP endpoints at /{server_name}/mcp

    Tools are automatically prefixed with server name to prevent conflicts.
    """

    def __init__(self, config: Settings) -> None:
        """Initialize HTTP server builder.

        Args:
            config: Application configuration.
        """
        super().__init__(config)

    @cached_property
    def _mounted_server_names(self) -> list[str]:
        """List of server names after mounting in main endpoint.

        Only includes servers with endpoint=False (mounted via Server Composition).
        Servers with endpoint=True are handled separately as individual HTTP endpoints.

        Returns:
            List of server names that were mounted in main endpoint.
        """
        return self.register_tool_mode_servers(transport_type=TransportConfig.HTTP)

    def build(self) -> Starlette:
        """Build and configure HTTP application.

        Supports two modes:
        - Servers with endpoint=False: mounted in main endpoint via FastMCP mount() (Server Composition)
        - Servers with endpoint=True: mounted as separate HTTP endpoints at /{server_name}/mcp

        Returns:
            Configured Starlette application ready to run.
        """
        # Separate servers into two groups
        main_endpoint_servers = {
            name: config
            for name, config in self.config.databases.items()
            if not config.endpoint
        }
        separate_endpoint_servers = {
            name: config
            for name, config in self.config.databases.items()
            if config.endpoint
        }

        streamable = self.config.tool_mode_streamable
        transport_type = TransportHttpApp.STREAMABLE_HTTP if streamable else TransportHttpApp.HTTP

        routes: list[Mount] = []
        sub_apps: list[tuple[str, Starlette]] = []

        # Create separate endpoints for servers with endpoint=True
        # IMPORTANT: These must be mounted BEFORE the main endpoint (Mount("/", ...))
        # to avoid the main endpoint catching all requests
        for server_name, server_config in separate_endpoint_servers.items():
            tools = self.lifespan_manager.get_tools(server_name)
            if tools is None:
                error_msg = f"ToolManager instance not found for server {server_name}"
                raise RuntimeError(error_msg)

            # Create separate FastMCP server for this endpoint
            sub_mcp = FastMCP(name=server_name)
            # Always use prefix for tools in separate endpoints
            tools.register_tools(sub_mcp, prefix=server_name)

            # Use transport setting from this specific database server
            # If not specified, use global transport (default: "http")
            database_server_transport = server_config.transport
            if database_server_transport is None:
                # Use global transport (always "http" for HTTP mode)
                database_server_transport = TransportHttpApp.HTTP.value
                transport_source = "global (default)"
            else:
                transport_source = "explicit"

            database_server_transport_type = (
                TransportHttpApp.STREAMABLE_HTTP
                if database_server_transport == TransportHttpApp.STREAMABLE_HTTP.value
                else TransportHttpApp.HTTP
            )
            is_streamable = database_server_transport == TransportHttpApp.STREAMABLE_HTTP.value

            # Create ASGI app for this server
            # For non-streamable, use stateless_http=True to avoid session management
            sub_app = sub_mcp.http_app(
                path="/mcp",
                transport=database_server_transport_type.value,
                stateless_http=not is_streamable,
            )
            sub_apps.append((server_name, sub_app))

            # Mount as separate endpoint (BEFORE main endpoint to avoid route conflicts)
            routes.append(Mount(f"/{server_name}", app=sub_app))
            logger.info(
                "Separate endpoint /%s/mcp created for server: %s (transport: %s, source: %s)",
                server_name,
                server_name,
                database_server_transport_type.value,
                transport_source,
            )

        # Register servers with endpoint=False in main endpoint
        # This must be mounted AFTER separate endpoints to avoid route conflicts
        if main_endpoint_servers:
            servers_list = ", ".join(self._mounted_server_names)
            is_single = len(main_endpoint_servers) == 1
            prefix_info = "no prefix" if is_single else "with prefixes"
            logger.info(
                "Main endpoint /%s created for servers: %s (transport: %s, %s)",
                self.config.endpoint,
                servers_list,
                transport_type.value,
                prefix_info,
            )

            # Create ASGI app from main_mcp for servers with endpoint=False
            main_app = self.main_mcp.http_app(
                path=f"/{self.config.endpoint}", transport=transport_type.value
            )
            routes.append(Mount("/", app=main_app))
        else:
            # No main endpoint servers, but we still need a main_app for lifespan
            main_app = self.main_mcp.http_app(
                path=f"/{self.config.endpoint}", transport=transport_type.value
            )
            routes.append(Mount("/", app=main_app))

        # Create combined lifespan for all applications
        @asynccontextmanager
        async def combined_lifespan(_app: Starlette) -> AsyncIterator[dict[str, Any]]:
            """Combined lifespan for all FastMCP applications and ToolManager."""
            async with AsyncExitStack() as stack:
                # Enter context of all ToolManager instances
                for tools_instance in self.lifespan_manager.tools_instances.values():
                    await stack.enter_async_context(tools_instance)

                # Initialize database connections
                logger.info("Initializing database connections...")
                for server_name, tools_instance in self.lifespan_manager.tools_instances.items():
                    try:
                        await tools_instance.db_connection.pool_connect()
                        logger.info("Successfully connected to database for server: %s", server_name)
                    except Exception as e:
                        logger.warning(
                            "Could not connect to database for server '%s': %s",
                            server_name,
                            str(e),
                        )

                # Enter lifespan of all sub applications
                for server_name, sub_app in sub_apps:
                    if hasattr(sub_app, "lifespan") and sub_app.lifespan:
                        await stack.enter_async_context(sub_app.lifespan(_app))

                # Enter lifespan of main application
                if hasattr(main_app, "lifespan") and main_app.lifespan:
                    await stack.enter_async_context(main_app.lifespan(_app))

                yield {}

        # Create Starlette application with all routes
        return Starlette(routes=routes, lifespan=combined_lifespan)

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

    Supports two mounting modes:
    - Servers with endpoint=False: tools available at /{endpoint} (with prefixes for multiple servers)
    - Servers with endpoint=True: tools available at /{server_name}/mcp (always with prefixes)

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
