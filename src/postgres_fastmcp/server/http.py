"""HTTP server implementation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from functools import cached_property
from typing import TYPE_CHECKING, Any

import uvicorn
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from postgres_fastmcp.config import Settings, settings
from postgres_fastmcp.enums import TransportConfig, TransportHttpApp
from postgres_fastmcp.logger import get_logger
from postgres_fastmcp.server.auth import build_keycloak_auth
from postgres_fastmcp.server.base import BaseServerBuilder
from postgres_fastmcp.server.middleware import MiddlewareManager


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette.requests import Request

    from postgres_fastmcp.config import Settings


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
        main_endpoint_servers = {name: config for name, config in self.config.databases.items() if not config.endpoint}
        separate_endpoint_servers = {name: config for name, config in self.config.databases.items() if config.endpoint}

        streamable = self.config.tool_mode_streamable
        transport_type = TransportHttpApp.STREAMABLE_HTTP if streamable else TransportHttpApp.HTTP

        routes: list[Mount | Route] = []
        sub_apps: list[tuple[str, Starlette]] = []

        # Register health endpoint at root level if enabled
        if self.config.server.health_endpoint_enabled:
            auth = build_keycloak_auth(self.config, server_name=self.config.name)
            mcp_requires_auth = auth is not None

            async def health_check(_request: Request) -> JSONResponse:
                """Health check endpoint for monitoring server health.

                Args:
                    _request: HTTP request (not used, but required for signature).

                Returns:
                    JSON response with service status.
                """
                return JSONResponse(
                    {
                        "status": "healthy",
                        "service": self.config.name,
                        "auth_enabled": mcp_requires_auth,
                    }
                )

            routes.append(Route("/health", health_check, methods=["GET"]))
            logger.info("Health endpoint registered at root level: GET /health (no authorization required)")

        # Create separate endpoints for servers with endpoint=True
        self._create_separate_endpoints(separate_endpoint_servers, routes, sub_apps)

        # Register servers with endpoint=False in main endpoint
        main_app = self._create_main_endpoint(main_endpoint_servers, transport_type, routes)

        # Create combined lifespan for all applications
        combined_lifespan = self._create_combined_lifespan(sub_apps, main_app)

        # Create Starlette application with all routes
        return Starlette(routes=routes, lifespan=combined_lifespan)

    def _create_separate_endpoints(
        self,
        separate_endpoint_servers: dict[str, Any],
        routes: list[Mount | Route],
        sub_apps: list[tuple[str, Starlette]],
    ) -> None:
        """Create separate endpoints for servers with endpoint=True.

        Args:
            separate_endpoint_servers: Dictionary of servers with endpoint=True.
            routes: List to append routes to.
            sub_apps: List to append sub applications to.
        """
        for server_name, server_config in separate_endpoint_servers.items():
            tools = self.lifespan_manager.get_tools(server_name)
            if tools is None:
                error_msg = f"ToolManager instance not found for server {server_name}"
                raise RuntimeError(error_msg)

            # Create separate FastMCP server for this endpoint
            auth = build_keycloak_auth(self.config, server_name=server_name)
            sub_mcp = FastMCP(name=server_name, auth=auth)
            sub_middleware_manager = MiddlewareManager(sub_mcp, self.config, auth)
            sub_middleware_manager.setup_all()
            tools.register_tools(sub_mcp, prefix=server_name)

            # Determine transport for this server
            database_server_transport = server_config.transport
            if database_server_transport is None:
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
            sub_app = sub_mcp.http_app(
                path="/mcp",
                transport=database_server_transport_type.value,
                stateless_http=not is_streamable,
            )
            sub_apps.append((server_name, sub_app))
            routes.append(Mount(f"/{server_name}", app=sub_app))

            logger.info(
                "Separate endpoint /%s/mcp created for server: %s (transport: %s, source: %s)",
                server_name,
                server_name,
                database_server_transport_type.value,
                transport_source,
            )

    def _create_main_endpoint(
        self,
        main_endpoint_servers: dict[str, Any],
        transport_type: TransportHttpApp,
        routes: list[Mount | Route],
    ) -> Starlette:
        """Create main endpoint for servers with endpoint=False.

        Args:
            main_endpoint_servers: Dictionary of servers with endpoint=False.
            transport_type: Transport type for main endpoint.
            routes: List to append routes to.

        Returns:
            Main Starlette application.
        """
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

        # Create ASGI app from main_mcp
        main_app = self.main_mcp.http_app(path=f"/{self.config.endpoint}", transport=transport_type.value)
        routes.append(Mount("/", app=main_app))
        return main_app

    def _create_combined_lifespan(
        self,
        sub_apps: list[tuple[str, Starlette]],
        main_app: Starlette,
    ) -> Any:  # noqa: ANN401
        """Create combined lifespan for all applications.

        Args:
            sub_apps: List of sub applications.
            main_app: Main application.

        Returns:
            Combined lifespan context manager.
        """

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
                for _server_name, sub_app in sub_apps:
                    if hasattr(sub_app, "lifespan") and sub_app.lifespan:
                        await stack.enter_async_context(sub_app.lifespan(_app))

                # Enter lifespan of main application
                if hasattr(main_app, "lifespan") and main_app.lifespan:
                    await stack.enter_async_context(main_app.lifespan(_app))

                yield {}

        return combined_lifespan

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
