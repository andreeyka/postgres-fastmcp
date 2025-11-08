"""Main entry point for the MCP server."""

from __future__ import annotations

import asyncio
import warnings

import click

# Suppress deprecation warnings early, before importing modules that might trigger them
# This must be done before importing postgres_mcp modules that import uvicorn/websockets
from postgres_mcp.config import app_settings


if app_settings.suppress_deprecation_warnings:
    warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*websockets.*")
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets")
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="websockets.legacy")
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="uvicorn.protocols.websockets")
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, module="uvicorn.protocols.websockets.websockets_impl"
    )

from postgres_mcp import __version__
from postgres_mcp.logger import get_logger
from postgres_mcp.server import run_http, run_stdio


logger = get_logger(__name__)


@click.command()
@click.option("--version", is_flag=True, default=False, help="Show version and exit")
def main(*, version: bool = False) -> None:
    """Main function to start the server."""
    if version:
        click.echo(f"postgres-mcp version {__version__}")
        return

    # Run the appropriate server based on configuration
    if app_settings.stdio:
        asyncio.run(run_stdio())
    else:
        asyncio.run(run_http())


if __name__ == "__main__":
    main()
