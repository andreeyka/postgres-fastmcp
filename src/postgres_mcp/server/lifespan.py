"""Lifespan management for FastMCP server."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, Any

from postgres_mcp.logger import get_logger
from postgres_mcp.sql import obfuscate_password
from postgres_mcp.tool import ToolManager


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastmcp import FastMCP

    from postgres_mcp.config import Settings


logger = get_logger(__name__)


class LifespanManager:
    """Lifespan manager for FastMCP server.

    Manages creation and lifecycle of ToolManager instances and database connections.
    """

    def __init__(self, config: Settings) -> None:
        """Initialize lifespan manager.

        Creates ToolManager instances according to configuration.

        Args:
            config: Application configuration with server settings.
        """
        self.config = config
        self.tools_instances: dict[str, ToolManager] = {}
        for server_name, server_config in config.databases.items():
            tools = ToolManager(config=server_config)
            self.tools_instances[server_name] = tools
            logger.debug("Created ToolManager instance for server: %s", server_name)

    def create_lifespan(self) -> Any:  # noqa: ANN401
        """Create lifespan context manager for FastMCP server.

        Returns:
            Lifespan context manager that can be passed to FastMCP constructor.
        """

        @asynccontextmanager
        async def lifespan(_server: FastMCP[Any]) -> AsyncIterator[dict[str, Any]]:
            """Lifespan context manager for ToolManager instances lifecycle.

            Initializes database connections on startup and closes them on shutdown.

            Args:
                _server: FastMCP server instance (unused but required by signature).

            Yields:
                Empty dictionary.
            """
            async with AsyncExitStack() as stack:
                # Enter context of all ToolManager instances for proper cleanup
                for tools_instance in self.tools_instances.values():
                    await stack.enter_async_context(tools_instance)

                # Initialize database connections for all ToolManager instances in parallel
                logger.info("Initializing database connections...")

                async def connect_server(server_name: str, tools_instance: ToolManager) -> tuple[str, bool, str | None]:
                    """Connect to database for one server.

                    Args:
                        server_name: Server name.
                        tools_instance: ToolManager instance to connect.

                    Returns:
                        Tuple (server_name, success, error_message).
                    """
                    try:
                        await tools_instance.db_connection.pool_connect()
                        logger.info("Successfully connected to database for server: %s", server_name)
                    except Exception as e:
                        error_msg = obfuscate_password(str(e))
                        logger.warning(
                            "Could not connect to database for server '%s': %s. "
                            "The server will start but database operations will fail "
                            "until a valid connection is established.",
                            server_name,
                            error_msg,
                        )
                        return (server_name, False, error_msg)
                    else:
                        return (server_name, True, None)

                # Start all connections in parallel
                results = await asyncio.gather(
                    *[
                        connect_server(server_name, tools_instance)
                        for server_name, tools_instance in self.tools_instances.items()
                    ],
                    return_exceptions=False,
                )

                # Analyze connection results
                successful: list[str] = []
                failed: list[tuple[str, str | None]] = []

                for server_name, success, error_msg in results:
                    if success:
                        successful.append(server_name)
                    else:
                        failed.append((server_name, error_msg))

                # Output final statistics
                total = len(self.tools_instances)
                success_count = len(successful)
                failed_count = len(failed)

                if failed_count == 0:
                    logger.info(
                        "Server started successfully. All %d database connection(s) initialized.",
                        success_count,
                    )
                elif success_count == 0:
                    logger.error(
                        "Server started, but ALL %d database connection(s) failed to initialize. "
                        "Database operations will not work until connections are established. "
                        "Failed servers: %s",
                        failed_count,
                        ", ".join(server_name for server_name, _ in failed),
                    )
                else:
                    logger.warning(
                        "Server started with partial database connectivity. "
                        "%d of %d connection(s) succeeded, %d failed. "
                        "Failed servers: %s",
                        success_count,
                        total,
                        failed_count,
                        ", ".join(server_name for server_name, _ in failed),
                    )
                yield {}

        return lifespan

    def get_tools(self, server_name: str) -> ToolManager | None:
        """Get ToolManager instance by server name.

        Args:
            server_name: Server name.

        Returns:
            ToolManager instance or None if not found.
        """
        return self.tools_instances.get(server_name)
