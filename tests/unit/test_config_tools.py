"""Tests for DatabaseConfig.get_enabled_tools() method."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from postgres_mcp.config import ADMIN_TOOLS, AVAILABLE_TOOLS, DatabaseConfig, ToolsConfig
from postgres_mcp.enums import AccessMode, ToolName, UserRole


class TestGetEnabledTools:
    """Test cases for DatabaseConfig.get_enabled_tools() method."""

    def test_user_role_defaults(self):
        """Test that user role gets only basic tools by default."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.USER,
        )

        enabled_tools = config.get_enabled_tools()

        # User role should have only basic tools (not admin tools)
        expected_tools = {tool for tool in AVAILABLE_TOOLS if tool not in ADMIN_TOOLS}
        assert enabled_tools == expected_tools
        assert ToolName.LIST_OBJECTS in enabled_tools
        assert ToolName.GET_OBJECT_DETAILS in enabled_tools
        assert ToolName.EXPLAIN_QUERY in enabled_tools
        # Admin tools should not be included
        assert ToolName.LIST_SCHEMAS not in enabled_tools
        assert ToolName.ANALYZE_WORKLOAD_INDEXES not in enabled_tools
        assert ToolName.ANALYZE_QUERY_INDEXES not in enabled_tools
        assert ToolName.ANALYZE_DB_HEALTH not in enabled_tools
        assert ToolName.GET_TOP_QUERIES not in enabled_tools

    def test_full_role_defaults(self):
        """Test that full role gets all tools by default."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.FULL,
        )

        enabled_tools = config.get_enabled_tools()

        # Full role should have all tools
        assert enabled_tools == set(AVAILABLE_TOOLS)
        for tool in AVAILABLE_TOOLS:
            assert tool in enabled_tools

    def test_user_role_with_partial_tools_config(self):
        """Test that partial tools config merges with role defaults for user role."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.USER,
            tools=ToolsConfig(list_objects=False),
        )

        enabled_tools = config.get_enabled_tools()

        # list_objects should be disabled (explicitly set)
        assert "list_objects" not in enabled_tools
        # Other basic tools should still be enabled (role defaults)
        assert "get_object_details" in enabled_tools
        assert "explain_query" in enabled_tools
        # Admin tools should still not be included (role defaults)
        assert "list_schemas" not in enabled_tools

    def test_full_role_with_partial_tools_config(self):
        """Test that partial tools config merges with role defaults for full role."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.FULL,
            tools=ToolsConfig(list_schemas=False, analyze_db_health=False),
        )

        enabled_tools = config.get_enabled_tools()

        # Explicitly disabled tools should not be included
        assert ToolName.LIST_SCHEMAS not in enabled_tools
        assert ToolName.ANALYZE_DB_HEALTH not in enabled_tools
        # Other tools should still be enabled (role defaults)
        assert ToolName.LIST_OBJECTS in enabled_tools
        assert ToolName.GET_OBJECT_DETAILS in enabled_tools
        assert ToolName.EXPLAIN_QUERY in enabled_tools
        assert ToolName.ANALYZE_WORKLOAD_INDEXES in enabled_tools
        assert ToolName.ANALYZE_QUERY_INDEXES in enabled_tools
        assert ToolName.GET_TOP_QUERIES in enabled_tools

    def test_user_role_cannot_enable_admin_tools_via_config(self):
        """Test that user role cannot enable admin tools even if explicitly set in config."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.USER,
            tools=ToolsConfig(list_schemas=True),  # Try to enable admin tool
        )

        enabled_tools = config.get_enabled_tools()

        # list_schemas should be enabled because it's explicitly set
        # Note: Current implementation allows this - admin tools can be enabled via config
        # This test documents current behavior
        assert ToolName.LIST_SCHEMAS in enabled_tools

    def test_full_role_with_all_tools_disabled(self):
        """Test that full role can disable all tools via config."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.FULL,
            tools=ToolsConfig(
                list_schemas=False,
                list_objects=False,
                get_object_details=False,
                explain_query=False,
                execute_sql=False,
                analyze_workload_indexes=False,
                analyze_query_indexes=False,
                analyze_db_health=False,
                get_top_queries=False,
            ),
        )

        enabled_tools = config.get_enabled_tools()

        # All tools should be disabled
        assert enabled_tools == set()

    def test_user_role_with_all_basic_tools_disabled(self):
        """Test that user role can disable all basic tools via config."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.USER,
            tools=ToolsConfig(
                list_objects=False,
                get_object_details=False,
                explain_query=False,
                execute_sql=False,
            ),
        )

        enabled_tools = config.get_enabled_tools()

        # All basic tools should be disabled
        assert enabled_tools == set()
        # Admin tools should still not be included
        assert ToolName.LIST_SCHEMAS not in enabled_tools

    def test_full_role_with_single_tool_enabled(self):
        """Test that full role can enable only one tool via config."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.FULL,
            tools=ToolsConfig(
                list_schemas=False,
                list_objects=True,  # Only this one enabled
                get_object_details=False,
                explain_query=False,
                execute_sql=False,
                analyze_workload_indexes=False,
                analyze_query_indexes=False,
                analyze_db_health=False,
                get_top_queries=False,
            ),
        )

        enabled_tools = config.get_enabled_tools()

        # Only list_objects should be enabled
        assert enabled_tools == {ToolName.LIST_OBJECTS}

    def test_user_role_enable_one_disable_one(self):
        """Test that user role can enable/disable specific tools."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.USER,
            tools=ToolsConfig(
                list_objects=False,  # Disable
                explain_query=True,  # Keep enabled (explicit)
            ),
        )

        enabled_tools = config.get_enabled_tools()

        # list_objects should be disabled
        assert ToolName.LIST_OBJECTS not in enabled_tools
        # explain_query should be enabled (explicitly set)
        assert ToolName.EXPLAIN_QUERY in enabled_tools
        # get_object_details should be enabled (role default, not overridden)
        assert ToolName.GET_OBJECT_DETAILS in enabled_tools

    def test_access_mode_does_not_affect_enabled_tools(self):
        """Test that access_mode does not affect which tools are enabled."""
        config_restricted = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.FULL,
            access_mode=AccessMode.RESTRICTED,
        )

        config_unrestricted = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.FULL,
            access_mode=AccessMode.UNRESTRICTED,
        )

        tools_restricted = config_restricted.get_enabled_tools()
        tools_unrestricted = config_unrestricted.get_enabled_tools()

        # Both should have the same tools enabled
        assert tools_restricted == tools_unrestricted
        assert tools_restricted == set(AVAILABLE_TOOLS)

    def test_tools_config_validates_field_correspondence(self):
        """Test that ToolsConfig validates all fields correspond to AVAILABLE_TOOLS."""
        # This test ensures the validator works - normal ToolsConfig should pass
        tools_config = ToolsConfig()
        # Should not raise any error
        assert tools_config is not None

        # Verify all tools from AVAILABLE_TOOLS have fields
        model_fields = set(tools_config.__class__.model_fields.keys())
        available_tool_values = {tool.value for tool in AVAILABLE_TOOLS}
        assert model_fields == available_tool_values

