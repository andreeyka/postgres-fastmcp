# mypy: ignore-errors
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from postgres_fastmcp.enums import AccessMode, UserRole
from postgres_fastmcp.sql.safe_sql import SafeSqlDriver
from postgres_fastmcp.sql.sql_driver import DbConnPool, SqlDriver


@pytest.fixture
def mock_db_connection():
    """Mock database connection pool."""
    conn = MagicMock(spec=DbConnPool)
    conn.is_valid = True
    conn.connection_url = "postgresql://user:pass@localhost/db"
    return conn


@pytest.mark.parametrize(
    "role,access_mode,expected_driver_type",
    [
        (UserRole.FULL, AccessMode.UNRESTRICTED, SqlDriver),
        (UserRole.FULL, AccessMode.RESTRICTED, SafeSqlDriver),
        (UserRole.USER, AccessMode.UNRESTRICTED, SafeSqlDriver),
        (UserRole.USER, AccessMode.RESTRICTED, SafeSqlDriver),
    ],
)
@pytest.mark.asyncio
async def test_tool_manager_returns_correct_driver(role, access_mode, expected_driver_type, mock_db_connection):
    """Test that ToolManager returns the correct driver type based on role and access_mode."""
    from pydantic import SecretStr

    from postgres_fastmcp.config import DatabaseConfig
    from postgres_fastmcp.tool import ToolManager

    config = DatabaseConfig(
        database_uri=SecretStr("postgresql://user:pass@localhost/db"),
        role=role,
        access_mode=access_mode,
    )

    tool_manager = ToolManager(config=config)
    tool_manager.db_connection = mock_db_connection
    driver = tool_manager.sql_driver
    assert isinstance(driver, expected_driver_type)

    # When not in FULL+UNRESTRICTED mode, verify timeout is set
    if not (role == UserRole.FULL and access_mode == AccessMode.UNRESTRICTED):
        assert isinstance(driver, SafeSqlDriver)
        assert driver.timeout == 30


@pytest.mark.asyncio
async def test_tool_manager_sets_timeout_in_restricted_mode(mock_db_connection):
    """Test that ToolManager sets the timeout in restricted mode."""
    from pydantic import SecretStr

    from postgres_fastmcp.config import DatabaseConfig
    from postgres_fastmcp.tool import ToolManager

    config = DatabaseConfig(
        database_uri=SecretStr("postgresql://user:pass@localhost/db"),
        role=UserRole.FULL,
        access_mode=AccessMode.RESTRICTED,
    )

    tool_manager = ToolManager(config=config)
    tool_manager.db_connection = mock_db_connection
    driver = tool_manager.sql_driver
    assert isinstance(driver, SafeSqlDriver)
    assert driver.timeout == 30
    assert hasattr(driver, "sql_driver")


@pytest.mark.asyncio
async def test_tool_manager_in_unrestricted_mode_no_timeout(mock_db_connection):
    """Test that ToolManager in full+unrestricted mode is a regular SqlDriver."""
    from pydantic import SecretStr

    from postgres_fastmcp.config import DatabaseConfig
    from postgres_fastmcp.tool import ToolManager

    config = DatabaseConfig(
        database_uri=SecretStr("postgresql://user:pass@localhost/db"),
        role=UserRole.FULL,
        access_mode=AccessMode.UNRESTRICTED,
    )

    tool_manager = ToolManager(config=config)
    tool_manager.db_connection = mock_db_connection
    driver = tool_manager.sql_driver
    assert isinstance(driver, SqlDriver)
    assert not hasattr(driver, "timeout")


@pytest.mark.asyncio
async def test_command_line_parsing():
    """Test that command-line arguments correctly set the access mode."""
    import sys

    from postgres_fastmcp.main import main

    # Mock sys.argv and asyncio.run
    original_argv = sys.argv
    original_run = asyncio.run

    try:
        # Test with --database-uri (new way to specify database)
        sys.argv = [
            "postgres_fastmcp",
            "--database-uri",
            "postgresql://user:password@localhost/db",
            "--transport",
            "stdio",
        ]
        # Mock asyncio.run as a regular MagicMock (not AsyncMock) since it's a sync function
        asyncio.run = MagicMock()

        # Mock the server run functions as regular MagicMock (not AsyncMock)
        # since asyncio.run is mocked and won't actually await them
        with (
            patch("postgres_fastmcp.main.run_stdio", MagicMock()),
            patch("postgres_fastmcp.main.run_http", MagicMock()),
        ):
            # Run main (partially mocked to avoid actual connection)
            # Click raises SystemExit(0) on success, which we need to catch
            with pytest.raises(SystemExit) as exc_info:
                main()
            # Verify exit code is 0 (success)
            assert exc_info.value.code == 0

    finally:
        # Restore original values
        sys.argv = original_argv
        asyncio.run = original_run
