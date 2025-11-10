"""Main entry point for the MCP server."""

from __future__ import annotations

import asyncio
import sys
import warnings

import click
from pydantic import SecretStr

from postgres_mcp import __version__
from postgres_mcp.config import DatabaseConfig, get_settings
from postgres_mcp.logger import get_logger
from postgres_mcp.server import run_http, run_stdio

from .logger import configure_logging


configure_logging(
    level="INFO",
    omit_repeated_times=False,  # Disable time grouping
)

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
    "--streamable",
    is_flag=True,
    default=False,
    help="Use streamable-http transport (only for HTTP transport)",
)
@click.option(
    "--transport",
    type=click.Choice(["http", "stdio"], case_sensitive=False),
    default="http",
    help="Transport type: 'http' or 'stdio'",
)
@click.option("--host", type=str, default="127.0.0.1", help="Host to bind the server to")
@click.option("--port", type=int, default=8000, help="Port to bind the server to")
@click.option("--workers", type=int, default=1, help="Number of workers to run")
def main(  # noqa: PLR0913
    *,
    version: bool = False,
    database_uri: str | None = None,
    server_name: str = "default",
    endpoint: bool = False,
    streamable: bool = False,
    transport: str = "http",
    host: str = "127.0.0.1",
    port: int = 8000,
    workers: int = 1,
) -> None:
    """Main function to start the server.

    Uvicorn and FastMCP have built-in signal handling (SIGINT, SIGTERM).
    Lifespan manager automatically closes resources via AsyncExitStack.

    If --database-uri is specified, runs single server mode with CLI parameters,
    ignoring config.json and other configuration sources.
    """
    if version:
        click.echo(f"postgres-mcp version {__version__}")
        return

    # If database_uri specified, create single server configuration
    if database_uri:
        database_config = DatabaseConfig(
            database_uri=SecretStr(database_uri),
            endpoint=endpoint,
            streamable=streamable,
        )
        # Always use Server Composition with prefixes (default behavior)
        app_settings = get_settings(
            transport=transport,
            databases={server_name: database_config},
            host=host,
            port=port,
            workers=workers,
        )
    else:
        # Use standard configuration from config.json/env
        app_settings = get_settings()

    # Suppress deprecation warnings from websockets (used by uvicorn) if configured
    if app_settings.deprecation_warnings:
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
