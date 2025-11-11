"""Tests for ToolManager tool creation based on role and access_mode."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from postgres_mcp.config import ADMIN_TOOLS, AVAILABLE_TOOLS, DatabaseConfig, ToolsConfig
from postgres_mcp.enums import AccessMode, ToolName, UserRole
from postgres_mcp.tool.descriptions import (
    DESC_EXECUTE_SQL_RESTRICTED,
    DESC_EXECUTE_SQL_UNRESTRICTED,
    DESC_GET_OBJECT_DETAILS_FULL,
    DESC_GET_OBJECT_DETAILS_USER,
    DESC_LIST_OBJECTS_FULL,
    DESC_LIST_OBJECTS_USER,
)
from postgres_mcp.tool.tools import ToolManager


class TestToolManagerToolCreation:
    """Test cases for ToolManager tool creation based on role and access_mode."""

    @pytest.fixture
    def mock_db_connection(self):
        """Mock database connection pool."""
        with patch("postgres_mcp.tool.tools.DbConnPool") as mock_pool:
            mock_pool_instance = MagicMock()
            mock_pool.return_value = mock_pool_instance
            yield mock_pool_instance

    def test_user_role_creates_only_basic_tools(self, mock_db_connection):  # noqa: ARG002
        """Test that user role creates only basic tools (not admin tools)."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.USER,
            access_mode=AccessMode.RESTRICTED,
        )

        manager = ToolManager(config=config)

        # Check that only basic tools are enabled
        basic_tools = {tool for tool in AVAILABLE_TOOLS if tool not in ADMIN_TOOLS}
        for tool_name in AVAILABLE_TOOLS:
            is_enabled = manager._tools[tool_name.value]["enabled"]
            expected_enabled = tool_name in basic_tools
            assert is_enabled == expected_enabled, f"Tool {tool_name.value} should be {'enabled' if expected_enabled else 'disabled'} for user role"

        # Verify specific tools
        assert manager._tools[ToolName.LIST_OBJECTS.value]["enabled"] is True
        assert manager._tools[ToolName.GET_OBJECT_DETAILS.value]["enabled"] is True
        assert manager._tools[ToolName.EXPLAIN_QUERY.value]["enabled"] is True
        assert manager._tools[ToolName.EXECUTE_SQL.value]["enabled"] is True

        # Admin tools should be disabled
        assert manager._tools[ToolName.LIST_SCHEMAS.value]["enabled"] is False
        assert manager._tools[ToolName.ANALYZE_WORKLOAD_INDEXES.value]["enabled"] is False
        assert manager._tools[ToolName.ANALYZE_QUERY_INDEXES.value]["enabled"] is False
        assert manager._tools[ToolName.ANALYZE_DB_HEALTH.value]["enabled"] is False
        assert manager._tools[ToolName.GET_TOP_QUERIES.value]["enabled"] is False

    def test_full_role_creates_all_tools(self, mock_db_connection):  # noqa: ARG002
        """Test that full role creates all tools."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.FULL,
            access_mode=AccessMode.RESTRICTED,
        )

        manager = ToolManager(config=config)

        # All tools should be enabled for full role
        for tool_name in AVAILABLE_TOOLS:
            assert manager._tools[tool_name.value]["enabled"] is True, f"Tool {tool_name.value} should be enabled for full role"

    def test_user_role_tool_descriptions(self, mock_db_connection):  # noqa: ARG002
        """Test that user role gets correct tool descriptions."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.USER,
            access_mode=AccessMode.RESTRICTED,
        )

        manager = ToolManager(config=config)

        # Check role-specific descriptions
        assert manager._tools[ToolName.LIST_OBJECTS.value]["description"] == DESC_LIST_OBJECTS_USER
        assert manager._tools[ToolName.GET_OBJECT_DETAILS.value]["description"] == DESC_GET_OBJECT_DETAILS_USER
        assert manager._tools[ToolName.EXECUTE_SQL.value]["description"] == DESC_EXECUTE_SQL_RESTRICTED

    def test_full_role_tool_descriptions(self, mock_db_connection):  # noqa: ARG002
        """Test that full role gets correct tool descriptions."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.FULL,
            access_mode=AccessMode.RESTRICTED,
        )

        manager = ToolManager(config=config)

        # Check role-specific descriptions
        assert manager._tools[ToolName.LIST_OBJECTS.value]["description"] == DESC_LIST_OBJECTS_FULL
        assert manager._tools[ToolName.GET_OBJECT_DETAILS.value]["description"] == DESC_GET_OBJECT_DETAILS_FULL
        assert manager._tools[ToolName.EXECUTE_SQL.value]["description"] == DESC_EXECUTE_SQL_RESTRICTED

    def test_execute_sql_description_unrestricted_full_role(self, mock_db_connection):  # noqa: ARG002
        """Test that execute_sql gets unrestricted description for full role with unrestricted access_mode."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.FULL,
            access_mode=AccessMode.UNRESTRICTED,
        )

        manager = ToolManager(config=config)

        assert manager._tools[ToolName.EXECUTE_SQL.value]["description"] == DESC_EXECUTE_SQL_UNRESTRICTED

    def test_execute_sql_description_restricted_full_role(self, mock_db_connection):  # noqa: ARG002
        """Test that execute_sql gets restricted description for full role with restricted access_mode."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.FULL,
            access_mode=AccessMode.RESTRICTED,
        )

        manager = ToolManager(config=config)

        assert manager._tools[ToolName.EXECUTE_SQL.value]["description"] == DESC_EXECUTE_SQL_RESTRICTED

    def test_execute_sql_description_restricted_user_role(self, mock_db_connection):  # noqa: ARG002
        """Test that execute_sql gets restricted description for user role (always restricted)."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.USER,
            access_mode=AccessMode.RESTRICTED,
        )

        manager = ToolManager(config=config)

        assert manager._tools[ToolName.EXECUTE_SQL.value]["description"] == DESC_EXECUTE_SQL_RESTRICTED

    def test_user_role_with_tools_config_enables_specific_tools(self, mock_db_connection):  # noqa: ARG002
        """Test that user role with tools config enables only specified tools."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.USER,
            access_mode=AccessMode.RESTRICTED,
            tools=ToolsConfig(
                list_objects=True,
                get_object_details=False,
                explain_query=True,
                execute_sql=False,
            ),
        )

        manager = ToolManager(config=config)

        # Only explicitly enabled tools should be enabled
        assert manager._tools[ToolName.LIST_OBJECTS.value]["enabled"] is True
        assert manager._tools[ToolName.GET_OBJECT_DETAILS.value]["enabled"] is False
        assert manager._tools[ToolName.EXPLAIN_QUERY.value]["enabled"] is True
        assert manager._tools[ToolName.EXECUTE_SQL.value]["enabled"] is False

        # Admin tools should still be disabled (user role cannot enable them)
        assert manager._tools[ToolName.LIST_SCHEMAS.value]["enabled"] is False
        assert manager._tools[ToolName.ANALYZE_WORKLOAD_INDEXES.value]["enabled"] is False

    def test_full_role_with_tools_config_enables_specific_tools(self, mock_db_connection):  # noqa: ARG002
        """Test that full role with tools config enables only specified tools."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.FULL,
            access_mode=AccessMode.RESTRICTED,
            tools=ToolsConfig(
                list_schemas=True,
                list_objects=False,
                analyze_workload_indexes=True,
                execute_sql=False,
            ),
        )

        manager = ToolManager(config=config)

        # Explicitly enabled tools should be enabled
        assert manager._tools[ToolName.LIST_SCHEMAS.value]["enabled"] is True
        assert manager._tools[ToolName.ANALYZE_WORKLOAD_INDEXES.value]["enabled"] is True

        # Explicitly disabled tools should be disabled
        assert manager._tools[ToolName.LIST_OBJECTS.value]["enabled"] is False
        assert manager._tools[ToolName.EXECUTE_SQL.value]["enabled"] is False

        # Tools not explicitly configured should use defaults (all enabled for full role)
        assert manager._tools[ToolName.GET_OBJECT_DETAILS.value]["enabled"] is True
        assert manager._tools[ToolName.EXPLAIN_QUERY.value]["enabled"] is True
        assert manager._tools[ToolName.ANALYZE_QUERY_INDEXES.value]["enabled"] is True
        assert manager._tools[ToolName.ANALYZE_DB_HEALTH.value]["enabled"] is True
        assert manager._tools[ToolName.GET_TOP_QUERIES.value]["enabled"] is True

    def test_all_tools_have_descriptions(self, mock_db_connection):  # noqa: ARG002
        """Test that all tools have descriptions regardless of role."""
        for role in [UserRole.USER, UserRole.FULL]:
            for access_mode in [AccessMode.RESTRICTED, AccessMode.UNRESTRICTED]:
                config = DatabaseConfig(
                    database_uri=SecretStr("postgresql://user:pass@localhost/db"),
                    role=role,
                    access_mode=access_mode,
                )

                manager = ToolManager(config=config)

                for tool_name in AVAILABLE_TOOLS:
                    description = manager._tools[tool_name.value]["description"]
                    assert description, f"Tool {tool_name.value} should have a description for role={role.value}, access_mode={access_mode.value}"
                    assert isinstance(description, str)
                    assert len(description) > 0

    def test_tools_structure(self, mock_db_connection):  # noqa: ARG002
        """Test that tools have correct structure (description and enabled fields)."""
        config = DatabaseConfig(
            database_uri=SecretStr("postgresql://user:pass@localhost/db"),
            role=UserRole.USER,
            access_mode=AccessMode.RESTRICTED,
        )

        manager = ToolManager(config=config)

        for tool_name in AVAILABLE_TOOLS:
            tool_config = manager._tools[tool_name.value]
            assert "description" in tool_config, f"Tool {tool_name.value} should have 'description' field"
            assert "enabled" in tool_config, f"Tool {tool_name.value} should have 'enabled' field"
            assert isinstance(tool_config["description"], str)
            assert isinstance(tool_config["enabled"], bool)

