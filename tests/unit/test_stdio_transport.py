"""Tests for stdio transport mode."""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock, patch

import pytest

from postgres_fastmcp.config import get_settings
from postgres_fastmcp.enums import TransportConfig
from postgres_fastmcp.config import DatabaseConfig
from pydantic import SecretStr


class TestStdioTransport:
    """Test cases for stdio transport mode."""

    def test_transport_stdio_via_cli(self):
        """Test that transport='stdio' via CLI sets stdio mode correctly."""
        settings = get_settings(
            server={"transport": "stdio"},
            databases={"test": DatabaseConfig(database_uri=SecretStr("postgresql://test"))},
        )

        assert settings.transport == TransportConfig.STDIO
        assert settings.stdio is True

    def test_transport_http_via_cli(self):
        """Test that transport='http' via CLI sets http mode correctly."""
        settings = get_settings(
            server={"transport": "http"},
            databases={"test": DatabaseConfig(database_uri=SecretStr("postgresql://test"))},
        )

        assert settings.transport == TransportConfig.HTTP
        assert settings.stdio is False

    def test_transport_default_when_not_specified(self):
        """Test that default transport is HTTP when not specified."""
        settings = get_settings(
            databases={"test": DatabaseConfig(database_uri=SecretStr("postgresql://test"))},
        )

        assert settings.transport == TransportConfig.HTTP
        assert settings.stdio is False

    def test_main_calls_run_stdio_when_transport_stdio(self):
        """Test that main() calls run_stdio when --transport stdio is specified."""
        from postgres_fastmcp.main import main

        original_argv = sys.argv
        original_run = asyncio.run

        try:
            sys.argv = [
                "postgres_fastmcp",
                "--database-uri",
                "postgresql://user:pass@localhost/db",
                "--transport",
                "stdio",
            ]
            asyncio.run = MagicMock()

            with (
                patch("postgres_fastmcp.main.run_stdio", MagicMock()) as mock_stdio,
                patch("postgres_fastmcp.main.run_http", MagicMock()) as mock_http,
            ):
                try:
                    main()
                except SystemExit:
                    pass

            # Verify run_stdio was called, not run_http
            assert mock_stdio.called is True
            assert mock_http.called is False

        finally:
            sys.argv = original_argv
            asyncio.run = original_run

    def test_main_calls_run_http_when_transport_http(self):
        """Test that main() calls run_http when --transport http is specified."""
        from postgres_fastmcp.main import main

        original_argv = sys.argv
        original_run = asyncio.run

        try:
            sys.argv = [
                "postgres_fastmcp",
                "--database-uri",
                "postgresql://user:pass@localhost/db",
                "--transport",
                "http",
            ]
            asyncio.run = MagicMock()

            with (
                patch("postgres_fastmcp.main.run_stdio", MagicMock()) as mock_stdio,
                patch("postgres_fastmcp.main.run_http", MagicMock()) as mock_http,
            ):
                try:
                    main()
                except SystemExit:
                    pass

            # Verify run_http was called, not run_stdio
            assert mock_stdio.called is False
            assert mock_http.called is True

        finally:
            sys.argv = original_argv
            asyncio.run = original_run

    def test_main_calls_run_http_when_transport_not_specified(self):
        """Test that main() calls run_http when --transport is not specified (default)."""
        from postgres_fastmcp.main import main

        original_argv = sys.argv
        original_run = asyncio.run

        try:
            sys.argv = [
                "postgres_fastmcp",
                "--database-uri",
                "postgresql://user:pass@localhost/db",
                # No --transport specified
            ]
            asyncio.run = MagicMock()

            with (
                patch("postgres_fastmcp.main.run_stdio", MagicMock()) as mock_stdio,
                patch("postgres_fastmcp.main.run_http", MagicMock()) as mock_http,
            ):
                try:
                    main()
                except SystemExit:
                    pass

            # Verify run_http was called (default), not run_stdio
            assert mock_stdio.called is False
            assert mock_http.called is True

        finally:
            sys.argv = original_argv
            asyncio.run = original_run

