"""HTTP server implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import uvicorn
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount

from postgres_mcp.config import app_settings
from postgres_mcp.logger import get_logger
from postgres_mcp.server.lifespan import fastmcp_lifespan, get_tools_and_server, register_tools_with_servers


if TYPE_CHECKING:
    from postgres_mcp.mcp_types import TransportHttpApp


logger = get_logger(__name__)


def _build_app_with_endpoints(
    main_app: Starlette,
    main_mcp: FastMCP,
    tool_mode_servers: list[str],
    endpoint_servers: list[tuple[str, FastMCP, str]],
) -> Starlette:
    """Build HTTP application with separate endpoints for each server.

    Args:
        main_app: Main FastMCP HTTP application (already created with lifespan).
        main_mcp: Main FastMCP server instance (to get lifespan from).
        tool_mode_servers: List of server names in tool mode.
        endpoint_servers: List of (server_name, sub_server, transport_config) tuples.

    Returns:
        Configured Starlette application with all routes.
    """
    routes = []

    # Separate endpoints /{server_name}/mcp with original names
    for server_name, sub_server, transport_config_value in endpoint_servers:
        transport: TransportHttpApp = "streamable-http" if transport_config_value == "http_streamable" else "http"
        endpoint_app = sub_server.http_app(path=f"/{app_settings.mount_point}", transport=transport)
        routes.append(Mount(f"/{server_name}", app=endpoint_app))
        logger.info(
            "Endpoint /%s/%s created for server %s (transport: %s)",
            server_name,
            app_settings.mount_point,
            server_name,
            transport_config_value,
        )

    # Common endpoint /mcp with all tools with prefixes
    routes.append(Mount(f"/{app_settings.mount_point}", app=main_app))
    servers_list = ", ".join(tool_mode_servers)
    logger.info(
        "Root endpoint /%s created for servers: %s",
        app_settings.mount_point,
        servers_list,
    )

    # Get lifespan from main_app and pass it to parent Starlette application
    # This is required for FastMCP's StreamableHTTPSessionManager to work correctly
    # According to FastMCP docs, we should use mcp_app.lifespan from the application
    # returned by http_app(). The lifespan is stored in the router.
    lifespan = getattr(main_app.router, "lifespan", None)
    if lifespan is None:
        # Fallback: try to get from main_mcp (though this shouldn't be needed)
        lifespan = getattr(main_mcp, "_lifespan", None)
    return Starlette(routes=routes, lifespan=lifespan)


def _build_app_tool_mode(main_mcp: FastMCP, tool_mode_servers: list[str]) -> Starlette:
    """Build HTTP application with all servers in tool mode.

    Args:
        main_mcp: Main FastMCP server instance (with tools already registered via lifespan).
        tool_mode_servers: List of server names in tool mode.

    Returns:
        Configured Starlette application.
    """
    servers_list = ", ".join(tool_mode_servers)
    logger.info(
        "Root endpoint /%s created for servers: %s",
        app_settings.mount_point,
        servers_list,
    )

    # FastMCP already manages lifespan through http_app()
    http_app = main_mcp.http_app(path=f"/{app_settings.mount_point}")

    if isinstance(http_app, Starlette):
        return http_app

    return http_app


async def run_http() -> None:
    """Run server in HTTP mode with lifecycle management via FastMCP lifespan.

    FastMCP will automatically call the lifespan when http_app() is created and used,
    which will create Tools instances and register them on the server.
    """
    try:
        # Create FastMCP server with lifespan that manages Tools instances
        # The lifespan will automatically register tools on the server
        main_mcp = FastMCP(name=app_settings.name, lifespan=fastmcp_lifespan)

        # Create Tools instances and sub-servers before creating http_app()
        # because lifespan executes only when the app starts, but we need Tools instances now
        # They will be stored in _tools_instances_storage and managed by lifespan's AsyncExitStack
        tools_and_servers = register_tools_with_servers()

        # Check if we need endpoint mode by checking if any servers are in endpoint mode
        has_endpoints = any(server_config.mount_mode == "endpoint" for server_config in app_settings.servers.values())

        if has_endpoints:
            # Mount tool mode servers to main_mcp with prefixes
            for server_name, server_config in app_settings.servers.items():
                if server_config.mount_mode == "tool":
                    _tools, sub_server = tools_and_servers[server_name]
                    main_mcp.mount(sub_server, prefix=server_name)
                    logger.info(
                        "Server %s: Mounted with prefix %s -> /%s (transport: %s)",
                        server_name,
                        server_name,
                        app_settings.mount_point,
                        server_config.transport,
                    )

            # Now create http_app() - lifespan will use already created Tools instances
            main_app = main_mcp.http_app(path="/")
            if not isinstance(main_app, Starlette):
                error_msg = "Expected Starlette application from main_mcp.http_app()"
                raise TypeError(error_msg)

            # Create endpoint servers based on config
            # Get Tools instances and sub-servers from storage
            # Tools instances are already created and will be managed through lifespan's AsyncExitStack
            endpoint_servers: list[tuple[str, FastMCP, str]] = []
            for server_name, server_config in app_settings.servers.items():
                if server_config.mount_mode == "endpoint":
                    # Get Tools instance and sub-server from storage
                    result = get_tools_and_server(main_mcp.name, server_name)
                    if result is None:
                        error_msg = f"Tools instance and sub-server not found for server {server_name}"
                        raise RuntimeError(error_msg)
                    _tools, sub_server = result
                    endpoint_servers.append((server_name, sub_server, server_config.transport))
                    logger.info(
                        "Server %s: Endpoint mode -> /%s/%s (transport: %s)",
                        server_name,
                        server_name,
                        app_settings.mount_point,
                        server_config.transport,
                    )

            # Get tool mode servers (servers not in endpoint mode)
            tool_mode_servers = [
                name for name, config in app_settings.servers.items() if config.mount_mode != "endpoint"
            ]

            server = _build_app_with_endpoints(main_app, main_mcp, tool_mode_servers, endpoint_servers)
        else:
            # All servers in tool mode - mount them to main_mcp with prefixes
            for server_name, server_config in app_settings.servers.items():
                _tools, sub_server = tools_and_servers[server_name]
                main_mcp.mount(sub_server, prefix=server_name)
                logger.info(
                    "Server %s: Mounted with prefix %s -> /%s (transport: %s)",
                    server_name,
                    server_name,
                    app_settings.mount_point,
                    server_config.transport,
                )

            tool_mode_servers = list(app_settings.servers.keys())
            server = _build_app_tool_mode(main_mcp, tool_mode_servers)

        if not isinstance(server, Starlette):
            error_msg = "Expected Starlette application for HTTP mode"
            raise TypeError(error_msg)

        # Run HTTP application via uvicorn
        # FastMCP will automatically call lifespan through Starlette lifespan, which will:
        # 1. Create Tools instances
        # 2. Register them on the server(s)
        # 3. Manage their lifecycle
        config = uvicorn.Config(
            server,
            host=app_settings.host,
            port=app_settings.port,
            log_config=None,  # Disable default logging configuration
            workers=app_settings.workers,
        )
        uvicorn_server = uvicorn.Server(config)
        await uvicorn_server.serve()
    except KeyboardInterrupt:
        logger.info("Received KeyboardInterrupt, shutting down...")
        raise
