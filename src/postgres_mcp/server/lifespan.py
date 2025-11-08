"""Lifespan management for FastMCP server."""

from __future__ import annotations

from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, Any

from devtools import debug
from fastmcp import FastMCP

from postgres_mcp.config import app_settings
from postgres_mcp.logger import get_logger
from postgres_mcp.tool import Tools


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


logger = get_logger(__name__)

# Storage for Tools instances and sub-servers (used in HTTP endpoint mode)
# Keyed by server name to allow multiple server instances
# Value is dict mapping server names to (Tools instance, sub_server) tuples
_tools_instances_storage: dict[str, dict[str, tuple[Tools, FastMCP]]] = {}


def register_tools_with_servers() -> dict[str, tuple[Tools, FastMCP]]:
    """Create Tools instances and register them with sub-servers.

    This function only creates Tools instances and registers tools on sub-servers.
    It does NOT mount servers - mounting logic is in http.py and stdio.py.

    Returns:
        Dictionary mapping server names to (Tools instance, sub_server) tuples.
    """
    tools_instances: dict[str, tuple[Tools, FastMCP]] = {}

    for server_name, server_config in app_settings.servers.items():
        # Create Tools instance for this server
        tools = Tools(config=server_config)
        logger.debug("Created Tools instance for server: %s", server_name)

        # Create sub-server and register tools on it
        sub_server = FastMCP(name=server_name)
        tools_count = tools.register_tools(sub_server)

        tools_instances[server_name] = (tools, sub_server)
        logger.debug("Registered %d tools on sub-server: %s", tools_count, server_name)

    return tools_instances


def get_tools_and_server(server_name: str, tools_server_name: str) -> tuple[Tools, FastMCP] | None:
    """Get Tools instance and sub-server for a specific server.

    Args:
        server_name: Name of the FastMCP server instance.
        tools_server_name: Name of the tools server (from config).

    Returns:
        Tuple of (Tools instance, sub_server), or None if not found.
    """
    tools_instances = _tools_instances_storage.get(server_name)
    if tools_instances is None:
        return None
    return tools_instances.get(tools_server_name)


@asynccontextmanager
async def fastmcp_lifespan(
    server: FastMCP[Any],
) -> AsyncIterator[dict[str, Any]]:
    """Create lifespan context manager that creates and manages Tools instances.

    This lifespan is designed to be passed to FastMCP server constructor.
    FastMCP will automatically manage the lifecycle of this lifespan.

    The lifespan also registers tools on the server after creating Tools instances.

    Args:
        server: FastMCP server instance (required by FastMCP lifespan signature).

    Yields:
        Empty dictionary (Tools instances are managed via AsyncExitStack, not through lifespan result).
    """
    # Create Tools instances and register them with servers
    # Check if Tools instances were already created (e.g., in http.py for endpoint mode)
    # If they were, reuse them; otherwise, create new ones
    debug(server.name)
    yield {}
    tools_instances = _tools_instances_storage.get(server.name)
    if tools_instances is None:
        # Tools instances not created yet, create them now
        tools_instances = register_tools_with_servers()
        # Store Tools instances for HTTP endpoint mode (so http.py can use them)
        _tools_instances_storage[server.name] = tools_instances
    else:
        # Tools instances already created (e.g., in http.py), reuse them
        # This happens when http.py calls register_tools_with_servers before creating http_app()
        logger.debug("Reusing existing Tools instances for server: %s", server.name)

    async with AsyncExitStack() as stack:
        # Enter all Tools instances as context managers for proper cleanup
        for tools_instance, _sub_server in tools_instances.values():
            await stack.enter_async_context(tools_instance)
        # Database connections are created lazily on first use
        logger.info("Server started, database connections will be created on first use")
        # Yield empty dict - Tools instances are managed via AsyncExitStack
        # Result is not used anywhere, so we don't need to return tools_instances
        yield {}
        # Cleanup happens automatically via AsyncExitStack
        # Clear Tools instances storage for this server
        _tools_instances_storage.pop(server.name, None)
