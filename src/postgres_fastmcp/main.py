"""Main entry point for the MCP server."""

from __future__ import annotations

import asyncio
import sys
import warnings
from typing import Any

import click
from pydantic import SecretStr

from postgres_fastmcp import __version__
from postgres_fastmcp.config import DatabaseConfig, get_settings
from postgres_fastmcp.enums import AccessMode, UserRole
from postgres_fastmcp.logger import get_logger
from postgres_fastmcp.server import run_http, run_stdio

from .logger import configure_logging


# Configure logging based on transport mode
# For stdio mode, completely disable logging to avoid interfering with MCP protocol
# For HTTP mode, use INFO level for normal logging
def _configure_logging_for_transport(transport: str | None) -> None:
    """Configure logging based on transport mode.

    Args:
        transport: Transport type ('stdio' or 'http') or None (will be determined from config).
    """
    if transport == "stdio":
        # In stdio mode, completely disable logging to avoid interfering with MCP protocol
        # All log output goes to stderr, which is used for stdio communication
        configure_logging(disable=True)


logger = get_logger(__name__)


@click.command()
@click.option("--version", is_flag=True, default=False, help="Show version and exit")
@click.option(
    "--database-uri",
    type=str,
    help="Database connection URI (if specified, runs single server mode ignoring config.json)",
)
@click.option(
    "--server-name",
    type=str,
    default="default",
    help="Server name (used only with --database-uri)",
)
@click.option(
    "--endpoint",
    is_flag=True,
    default=False,
    help="Mount the server as an endpoint (only for HTTP transport)",
)
@click.option(
    "--transport",
    type=click.Choice(["http", "stdio"], case_sensitive=False),
    default=None,
    help="Transport type: 'http' or 'stdio'. If not specified, uses config.json or environment variables.",
)
@click.option("--host", type=str, default="127.0.0.1", help="Host to bind the server to")
@click.option("--port", type=int, default=8000, help="Port to bind the server to")
@click.option("--workers", type=int, default=1, help="Number of workers to run")
@click.option(
    "--access-mode",
    type=click.Choice(["restricted", "unrestricted"], case_sensitive=False),
    default=None,
    help="SQL access mode: 'restricted' (read-only, SELECT only) or 'unrestricted' (read-write, DML/DDL). "
    "Used only with --database-uri. Default: 'restricted'.",
)
@click.option(
    "--role",
    type=click.Choice(["user", "full"], case_sensitive=False),
    default=None,
    help="User role: 'user' (basic role, only public schema, 4 tools) or 'full' (all schemas, 9 tools). "
    "Used only with --database-uri. Default: 'user'.",
)
@click.option(
    "--name",
    type=str,
    default=None,
    help="Tool prefix name. If specified, all tools will be prefixed with this name (e.g., 'myprefix_list_objects'). "
    "Used only with --database-uri. Works in both HTTP and stdio modes.",
)
def main(  # noqa: PLR0913
    *,
    version: bool = False,
    database_uri: str | None = None,
    server_name: str = "default",
    endpoint: bool = False,
    transport: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    workers: int = 1,
    access_mode: str | None = None,
    role: str | None = None,
    name: str | None = None,
) -> None:
    """Main function to start the server.

    Uvicorn and FastMCP have built-in signal handling (SIGINT, SIGTERM).
    Lifespan manager automatically closes resources via AsyncExitStack.

    If --database-uri is specified, runs single server mode with CLI parameters,
    ignoring config.json and other configuration sources.
    """
    # Initial logging configuration (will be adjusted in main() if needed)
    configure_logging(
        level="INFO",
        omit_repeated_times=False,  # Disable time grouping
    )

    if version:
        click.echo(f"postgres-fastmcp version {__version__}")
        return

    # If database_uri specified, create single server configuration
    if database_uri:
        # Parse access_mode and role from CLI
        access_mode_enum = AccessMode(access_mode) if access_mode else AccessMode.RESTRICTED
        role_enum = UserRole(role) if role else UserRole.USER

        database_config = DatabaseConfig(
            database_uri=SecretStr(database_uri),
            endpoint=endpoint,
            access_mode=access_mode_enum,
            role=role_enum,
            tool_prefix=name,
        )
        # Build overrides dict only with provided CLI parameters
        # Use new nested structure: server.host, server.port, server.transport
        server_overrides: dict[str, Any] = {
            "host": host,
            "port": port,
            "workers": workers,
        }
        # Only add transport if explicitly provided via CLI
        if transport is not None:
            server_overrides["transport"] = transport

        overrides: dict[str, Any] = {
            "databases": {server_name: database_config},
            "server": server_overrides,
        }
        # Always use Server Composition with prefixes (default behavior)
        app_settings = get_settings(**overrides)
    elif transport is not None:
        # Use standard configuration from config.json/env with transport override
        app_settings = get_settings(server={"transport": transport})
    else:
        # Use standard configuration from config.json/env
        app_settings = get_settings()

    # Reconfigure logging based on actual transport mode (from settings or CLI)
    # This ensures stdio mode has minimal logging to avoid interfering with MCP protocol
    actual_transport = transport if transport is not None else app_settings.transport.value
    _configure_logging_for_transport(actual_transport)

    # Suppress deprecation warnings from websockets (used by uvicorn) if configured
    if app_settings.server.deprecation_warnings:
        warnings.filterwarnings(
            "ignore",
            category=DeprecationWarning,
            module="websockets",
        )
        warnings.filterwarnings(
            "ignore",
            category=DeprecationWarning,
            module="uvicorn.protocols.websockets",
        )

    # Start server - asyncio.run() and uvicorn/FastMCP handle signals automatically
    try:
        if app_settings.stdio:
            asyncio.run(run_stdio(app_settings))
        else:
            asyncio.run(run_http(app_settings))
    except KeyboardInterrupt:
        # KeyboardInterrupt is handled by asyncio.run() and passed to servers
        # Just log and exit here
        logger.info("Application interrupted by user")
        sys.exit(0)
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
