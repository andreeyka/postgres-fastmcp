"""Main server for combining multiple MCP servers."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING

import uvicorn
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount

from postgres_mcp.config import app_settings
from postgres_mcp.logger import get_logger
from postgres_mcp.tool import Tools


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from postgres_mcp.mcp_types import TransportHttpApp


logger = get_logger(__name__)


def _create_tools_and_register_servers(
    main_mcp: FastMCP,
) -> tuple[list[Tools], list[str], list[tuple[str, FastMCP, str]]]:
    """Create Tools instances and register them with sub-servers.

    Args:
        main_mcp: Main FastMCP server instance.

    Returns:
        Tuple of (tools_instances, tool_mode_servers, endpoint_servers).
    """
    tools_instances: list[Tools] = []
    tool_mode_servers: list[str] = []
    endpoint_servers: list[tuple[str, FastMCP, str]] = []

    for server_name, server_config in app_settings.servers.items():
        mount_mode = server_config.mount_mode
        transport_config = server_config.transport
        sub_server = FastMCP(name=server_name)

        # Create Tools instance - will be entered as context manager in lifespan
        tools = Tools(config=server_config)
        tools_instances.append(tools)
        # Register all tools with the sub-server
        tools.register_tools(sub_server)

        if mount_mode == "tool":
            # Mount with prefix - tools will be available as {server_name}_{tool_name}
            main_mcp.mount(sub_server, prefix=server_name)
            tool_mode_servers.append(server_name)
            logger.info(
                "Server %s: tool mode (prefix: %s) -> /%s (transport: %s)",
                server_name,
                server_name,
                app_settings.mount_point,
                transport_config,
            )
        elif mount_mode == "endpoint":
            # Save for creating a separate endpoint /{server_name}/mcp
            endpoint_servers.append((server_name, sub_server, transport_config))
            logger.info(
                "Server %s: endpoint mode -> /%s/%s (transport: %s)",
                server_name,
                server_name,
                app_settings.mount_point,
                transport_config,
            )

    return tools_instances, tool_mode_servers, endpoint_servers


@asynccontextmanager
async def _create_lifespan_with_tools(tools_instances: list[Tools]) -> AsyncIterator[None]:
    """Create lifespan context manager for Tools instances.

    Args:
        tools_instances: List of Tools instances to manage.

    Yields:
        None
    """
    async with AsyncExitStack() as stack:
        # Enter all Tools instances as context managers for proper cleanup
        for tools_instance in tools_instances:
            await stack.enter_async_context(tools_instance)

        # Database connections are created lazily on first use
        logger.info("Server started, database connections will be created on first use")
        yield
        # Cleanup happens automatically via AsyncExitStack


async def create_stdio_server() -> FastMCP:
    """Create and configure stdio MCP server.

    Returns:
        Configured FastMCP server for stdio mode.
    """
    main_mcp = FastMCP(name=app_settings.name)
    tools_instances, tool_mode_servers, _ = _create_tools_and_register_servers(main_mcp)

    for server_name in tool_mode_servers:
        logger.info(
            "Server %s: tool mode (prefix: %s) -> stdio",
            server_name,
            server_name,
        )

    # Store tools_instances for later use in main()
    main_mcp._tools_instances = tools_instances  # type: ignore[attr-defined]
    return main_mcp


async def create_http_server() -> Starlette:
    """Create and configure HTTP MCP server.

    Returns:
        Configured Starlette application for HTTP mode.
    """
    main_mcp = FastMCP(name=app_settings.name)
    tools_instances, tool_mode_servers, endpoint_servers = _create_tools_and_register_servers(main_mcp)

    # If there are servers in endpoint mode, create Starlette application with endpoints
    if endpoint_servers:
        return _create_http_server_with_endpoints(main_mcp, tools_instances, tool_mode_servers, endpoint_servers)

    # If all servers are in tool mode, return ASGI application directly
    return _create_http_server_tool_mode(main_mcp, tools_instances, tool_mode_servers)


def _create_http_server_with_endpoints(
    main_mcp: FastMCP,
    tools_instances: list[Tools],
    tool_mode_servers: list[str],
    endpoint_servers: list[tuple[str, FastMCP, str]],
) -> Starlette:
    """Create HTTP server with separate endpoints for each server.

    Args:
        main_mcp: Main FastMCP server instance.
        tools_instances: List of Tools instances.
        tool_mode_servers: List of server names in tool mode.
        endpoint_servers: List of (server_name, sub_server, transport_config) tuples.

    Returns:
        Configured Starlette application.
    """
    routes = []
    apps: list[Starlette] = []

    # Separate endpoints /{server_name}/mcp with original names
    for server_name, sub_server, transport_config_value in endpoint_servers:
        transport: TransportHttpApp = "streamable-http" if transport_config_value == "http_streamable" else "http"
        endpoint_app = sub_server.http_app(path=f"/{app_settings.mount_point}/", transport=transport)
        routes.append(Mount(f"/{server_name}", app=endpoint_app))
        apps.append(endpoint_app)
        logger.info(
            "Endpoint /%s/%s created for server %s (transport: %s)",
            server_name,
            app_settings.mount_point,
            server_name,
            transport_config_value,
        )

    # Common endpoint /mcp with all tools with prefixes
    main_app = main_mcp.http_app(path="/")
    routes.append(Mount(f"/{app_settings.mount_point}", app=main_app))
    apps.append(main_app)
    servers_list = ", ".join(tool_mode_servers)
    logger.info(
        "Root endpoint /%s created for servers: %s",
        app_settings.mount_point,
        servers_list,
    )

    # Combine lifespans of all applications
    @asynccontextmanager
    async def combined_lifespan(app: Starlette) -> AsyncIterator[None]:
        """Combine lifespans of all MCP applications and manage database connections."""
        async with AsyncExitStack() as stack:
            # Enter all MCP application lifespans
            for mcp_app in apps:
                if hasattr(mcp_app, "lifespan"):
                    await stack.enter_async_context(mcp_app.lifespan(app))

            # Enter all Tools instances as context managers
            for tools_instance in tools_instances:
                await stack.enter_async_context(tools_instance)

            logger.info("Server started, database connections will be created on first use")
            yield

    return Starlette(routes=routes, lifespan=combined_lifespan)


def _create_http_server_tool_mode(
    main_mcp: FastMCP,
    tools_instances: list[Tools],
    tool_mode_servers: list[str],
) -> Starlette:
    """Create HTTP server with all servers in tool mode.

    Args:
        main_mcp: Main FastMCP server instance.
        tools_instances: List of Tools instances.
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

    @asynccontextmanager
    async def lifespan(_app: Starlette) -> AsyncIterator[None]:
        """Manage database connections lifecycle."""
        async with _create_lifespan_with_tools(tools_instances):
            yield

    http_app = main_mcp.http_app(path=f"/{app_settings.mount_point}/")

    if isinstance(http_app, Starlette):
        return Starlette(
            routes=http_app.routes,
            lifespan=lifespan,
        )

    return http_app


async def create_combined_server_async() -> Starlette | FastMCP:
    """Create a combined MCP server according to configuration.

    Returns:
        FastMCP server (if stdio is used) or Starlette ASGI application (if HTTP is used).
    """
    if app_settings.stdio:
        return await create_stdio_server()
    return await create_http_server()


async def main() -> None:
    """Main function to start the server."""
    if app_settings.stdio:
        await _run_stdio_server()
    else:
        await _run_http_server()


async def _run_stdio_server() -> None:
    """Run server in stdio mode."""
    main_mcp = await create_stdio_server()
    tools_instances = getattr(main_mcp, "_tools_instances", [])

    # Use AsyncExitStack to manage Tools contexts
    async with AsyncExitStack() as stack:
        # Enter all Tools instances as context managers
        for tools_instance in tools_instances:
            await stack.enter_async_context(tools_instance)

        # Run FastMCP server in stdio mode
        # Tools contexts will be cleaned up when stack exits
        await main_mcp.run_stdio_async(show_banner=False)


async def _run_http_server() -> None:
    """Run server in HTTP mode."""
    server = await create_http_server()

    if not isinstance(server, Starlette):
        error_msg = "Expected Starlette application for HTTP mode"
        raise TypeError(error_msg)

    # Run HTTP application via uvicorn
    config = uvicorn.Config(
        server,
        host=app_settings.host,
        port=app_settings.port,
        log_config=None,  # Disable default logging configuration
        workers=app_settings.workers,
    )
    uvicorn_server = uvicorn.Server(config)
    await uvicorn_server.serve()


if __name__ == "__main__":
    asyncio.run(main())
