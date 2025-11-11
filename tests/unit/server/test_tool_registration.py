"""Tests for tool registration with prefixes in stdio and HTTP modes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from postgres_mcp.config import get_settings
from postgres_mcp.enums import TransportConfig
from postgres_mcp.models import DatabaseConfig
from postgres_mcp.server.base import BaseServerBuilder
from postgres_mcp.server.http import HttpServerBuilder
from postgres_mcp.server.stdio import StdioServerBuilder


class TestToolRegistrationSingleServer:
    """Test cases for single server tool registration (no prefix)."""

    def test_single_server_stdio_no_prefix(self):
        """Test that single server in stdio mode registers tools without prefix."""
        settings = get_settings(
            transport="stdio",
            databases={"db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1"))},
        )

        builder = StdioServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Register tools
        mounted = builder.register_tool_mode_servers(TransportConfig.STDIO)

        # Verify: single server should be registered without prefix
        assert len(mounted) == 1
        assert "db1" in mounted
        # Verify register_tools was called with prefix=None
        mock_tools.register_tools.assert_called_once()
        call_args = mock_tools.register_tools.call_args
        assert call_args[0][0] == builder.main_mcp  # First arg is mcp
        assert call_args[1]["prefix"] is None  # prefix should be None

    def test_single_server_http_no_prefix(self):
        """Test that single server in HTTP mode registers tools without prefix."""
        settings = get_settings(
            transport="http",
            databases={"db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1"))},
        )

        builder = HttpServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Register tools
        mounted = builder.register_tool_mode_servers(TransportConfig.HTTP)

        # Verify: single server should be registered without prefix
        assert len(mounted) == 1
        assert "db1" in mounted
        # Verify register_tools was called with prefix=None
        mock_tools.register_tools.assert_called_once()
        call_args = mock_tools.register_tools.call_args
        assert call_args[0][0] == builder.main_mcp  # First arg is mcp
        assert call_args[1]["prefix"] is None  # prefix should be None

    def test_single_server_via_cli_no_prefix(self):
        """Test that single server via CLI registers tools without prefix."""
        # Simulate CLI mode: single server with --database-uri
        settings = get_settings(
            transport="stdio",
            databases={"default": DatabaseConfig(database_uri=SecretStr("postgresql://test"))},
        )

        builder = StdioServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Register tools
        mounted = builder.register_tool_mode_servers(TransportConfig.STDIO)

        # Verify: single server should be registered without prefix
        assert len(mounted) == 1
        assert "default" in mounted
        # Verify register_tools was called with prefix=None
        mock_tools.register_tools.assert_called_once()
        call_args = mock_tools.register_tools.call_args
        assert call_args[1]["prefix"] is None  # prefix should be None

    def test_single_server_via_config_json_no_prefix(self):
        """Test that single server via config.json registers tools without prefix."""
        # Simulate config.json with single server
        settings = get_settings(
            transport="http",
            databases={"app1": DatabaseConfig(database_uri=SecretStr("postgresql://test"))},
        )

        builder = HttpServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Register tools
        mounted = builder.register_tool_mode_servers(TransportConfig.HTTP)

        # Verify: single server should be registered without prefix
        assert len(mounted) == 1
        assert "app1" in mounted
        # Verify register_tools was called with prefix=None
        mock_tools.register_tools.assert_called_once()
        call_args = mock_tools.register_tools.call_args
        assert call_args[1]["prefix"] is None  # prefix should be None


class TestToolRegistrationMultipleServers:
    """Test cases for multiple servers tool registration (with prefixes)."""

    def test_multiple_servers_stdio_with_prefixes(self):
        """Test that multiple servers in stdio mode register tools with prefixes."""
        settings = get_settings(
            transport="stdio",
            databases={
                "db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1")),
                "db2": DatabaseConfig(database_uri=SecretStr("postgresql://test2")),
            },
        )

        builder = StdioServerBuilder(settings)
        # Mock ToolManager for each server
        mock_tools1 = MagicMock()
        mock_tools2 = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(side_effect=[mock_tools1, mock_tools2])

        # Register tools
        mounted = builder.register_tool_mode_servers(TransportConfig.STDIO)

        # Verify: both servers should be registered
        assert len(mounted) == 2
        assert "db1" in mounted
        assert "db2" in mounted

        # Verify: each server registered with its prefix
        assert mock_tools1.register_tools.call_count == 1
        assert mock_tools2.register_tools.call_count == 1

        # Check first server: should be registered with prefix="db1"
        call1 = mock_tools1.register_tools.call_args
        # First server creates sub_server, so mcp is sub_server, not main_mcp
        assert call1[1]["prefix"] == "db1"

        # Check second server: should be registered with prefix="db2"
        call2 = mock_tools2.register_tools.call_args
        assert call2[1]["prefix"] == "db2"

    def test_multiple_servers_http_with_prefixes(self):
        """Test that multiple servers in HTTP mode register tools with prefixes."""
        settings = get_settings(
            transport="http",
            databases={
                "db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1")),
                "db2": DatabaseConfig(database_uri=SecretStr("postgresql://test2")),
            },
        )

        builder = HttpServerBuilder(settings)
        # Mock ToolManager for each server
        mock_tools1 = MagicMock()
        mock_tools2 = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(side_effect=[mock_tools1, mock_tools2])

        # Register tools
        mounted = builder.register_tool_mode_servers(TransportConfig.HTTP)

        # Verify: both servers should be registered
        assert len(mounted) == 2
        assert "db1" in mounted
        assert "db2" in mounted

        # Verify: each server registered with its prefix
        assert mock_tools1.register_tools.call_count == 1
        assert mock_tools2.register_tools.call_count == 1

        # Check first server: should be registered with prefix="db1"
        call1 = mock_tools1.register_tools.call_args
        assert call1[1]["prefix"] == "db1"

        # Check second server: should be registered with prefix="db2"
        call2 = mock_tools2.register_tools.call_args
        assert call2[1]["prefix"] == "db2"

    def test_three_servers_stdio_with_prefixes(self):
        """Test that three servers in stdio mode register tools with prefixes."""
        settings = get_settings(
            transport="stdio",
            databases={
                "db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1")),
                "db2": DatabaseConfig(database_uri=SecretStr("postgresql://test2")),
                "db3": DatabaseConfig(database_uri=SecretStr("postgresql://test3")),
            },
        )

        builder = StdioServerBuilder(settings)
        # Mock ToolManager for each server
        mock_tools1 = MagicMock()
        mock_tools2 = MagicMock()
        mock_tools3 = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(side_effect=[mock_tools1, mock_tools2, mock_tools3])

        # Register tools
        mounted = builder.register_tool_mode_servers(TransportConfig.STDIO)

        # Verify: all three servers should be registered
        assert len(mounted) == 3
        assert "db1" in mounted
        assert "db2" in mounted
        assert "db3" in mounted

        # Verify: each server registered with its prefix
        assert mock_tools1.register_tools.call_count == 1
        assert mock_tools2.register_tools.call_count == 1
        assert mock_tools3.register_tools.call_count == 1

        # Check prefixes
        assert mock_tools1.register_tools.call_args[1]["prefix"] == "db1"
        assert mock_tools2.register_tools.call_args[1]["prefix"] == "db2"
        assert mock_tools3.register_tools.call_args[1]["prefix"] == "db3"


class TestToolRegistrationConsistency:
    """Test cases to ensure consistency between HTTP and stdio modes."""

    def test_single_server_consistency_between_http_and_stdio(self):
        """Test that single server registration is consistent between HTTP and stdio."""
        settings = get_settings(
            databases={"db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1"))},
        )

        # Test stdio
        stdio_settings = get_settings(transport="stdio", databases=settings.databases)
        stdio_builder = StdioServerBuilder(stdio_settings)
        mock_tools_stdio = MagicMock()
        stdio_builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools_stdio)
        stdio_builder.register_tool_mode_servers(TransportConfig.STDIO)

        # Test HTTP
        http_settings = get_settings(transport="http", databases=settings.databases)
        http_builder = HttpServerBuilder(http_settings)
        mock_tools_http = MagicMock()
        http_builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools_http)
        http_builder.register_tool_mode_servers(TransportConfig.HTTP)

        # Verify: both should use prefix=None
        assert mock_tools_stdio.register_tools.call_args[1]["prefix"] is None
        assert mock_tools_http.register_tools.call_args[1]["prefix"] is None

    def test_multiple_servers_consistency_between_http_and_stdio(self):
        """Test that multiple servers registration is consistent between HTTP and stdio."""
        databases = {
            "db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1")),
            "db2": DatabaseConfig(database_uri=SecretStr("postgresql://test2")),
        }

        # Test stdio
        stdio_settings = get_settings(transport="stdio", databases=databases)
        stdio_builder = StdioServerBuilder(stdio_settings)
        mock_tools1_stdio = MagicMock()
        mock_tools2_stdio = MagicMock()
        stdio_builder.lifespan_manager.get_tools = MagicMock(side_effect=[mock_tools1_stdio, mock_tools2_stdio])
        stdio_builder.register_tool_mode_servers(TransportConfig.STDIO)

        # Test HTTP
        http_settings = get_settings(transport="http", databases=databases)
        http_builder = HttpServerBuilder(http_settings)
        mock_tools1_http = MagicMock()
        mock_tools2_http = MagicMock()
        http_builder.lifespan_manager.get_tools = MagicMock(side_effect=[mock_tools1_http, mock_tools2_http])
        http_builder.register_tool_mode_servers(TransportConfig.HTTP)

        # Verify: both should use prefixes
        assert mock_tools1_stdio.register_tools.call_args[1]["prefix"] == "db1"
        assert mock_tools2_stdio.register_tools.call_args[1]["prefix"] == "db2"
        assert mock_tools1_http.register_tools.call_args[1]["prefix"] == "db1"
        assert mock_tools2_http.register_tools.call_args[1]["prefix"] == "db2"


class TestStdioEndpointWarning:
    """Test cases for endpoint parameter warning in stdio mode."""

    def test_stdio_warns_when_endpoint_true(self):
        """Test that stdio mode warns when servers have endpoint=True."""
        settings = get_settings(
            transport="stdio",
            databases={
                "db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1"), endpoint=True),
                "db2": DatabaseConfig(database_uri=SecretStr("postgresql://test2"), endpoint=False),
            },
        )

        builder = StdioServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Register tools and check for warning
        with patch("postgres_mcp.server.base.logger") as mock_logger:
            mounted = builder.register_tool_mode_servers(TransportConfig.STDIO)

            # Verify: all servers should be registered (endpoint is ignored)
            assert len(mounted) == 2
            assert "db1" in mounted
            assert "db2" in mounted

            # Verify: warning should be called with db1 (endpoint=True)
            assert mock_logger.warning.called
            warning_call = mock_logger.warning.call_args
            warning_msg = warning_call[0][0]  # First positional argument is the message
            assert "stdio mode" in warning_msg.lower()
            assert "endpoint" in warning_msg.lower()
            # The formatted string should contain db1
            warning_formatted = warning_msg % warning_call[0][1:]  # Format with remaining args
            assert "db1" in warning_formatted

    def test_stdio_no_warning_when_endpoint_false(self):
        """Test that stdio mode doesn't warn when all servers have endpoint=False."""
        settings = get_settings(
            transport="stdio",
            databases={
                "db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1"), endpoint=False),
                "db2": DatabaseConfig(database_uri=SecretStr("postgresql://test2"), endpoint=False),
            },
        )

        builder = StdioServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Register tools and check for no warning
        with patch("postgres_mcp.server.base.logger") as mock_logger:
            mounted = builder.register_tool_mode_servers(TransportConfig.STDIO)

            # Verify: all servers should be registered
            assert len(mounted) == 2

            # Verify: warning should NOT be called
            assert not mock_logger.warning.called

    def test_http_filters_endpoint_true_servers(self):
        """Test that HTTP mode filters out servers with endpoint=True."""
        settings = get_settings(
            transport="http",
            databases={
                "db1": DatabaseConfig(database_uri=SecretStr("postgresql://test1"), endpoint=True),
                "db2": DatabaseConfig(database_uri=SecretStr("postgresql://test2"), endpoint=False),
            },
        )

        builder = HttpServerBuilder(settings)
        # Mock ToolManager
        mock_tools = MagicMock()
        builder.lifespan_manager.get_tools = MagicMock(return_value=mock_tools)

        # Register tools
        mounted = builder.register_tool_mode_servers(TransportConfig.HTTP)

        # Verify: only db2 should be registered (db1 has endpoint=True)
        assert len(mounted) == 1
        assert "db2" in mounted
        assert "db1" not in mounted

